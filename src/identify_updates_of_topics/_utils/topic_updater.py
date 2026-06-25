import logging
from datetime import datetime

from _dependencies.common.commons import ChangeType

from .change_detector import ChangeDetector
from .coordinates import CoordinatesResolver
from .database import DBClient
from .forum import ForumClient
from .parse import (
    parse_address_from_title,
    profile_get_managers,
    profile_get_type_of_activity,
)
from .search_parser import SearchParser
from .topics_commons import (
    ChangeLogLine,
    CoordType,
    ForumSearchItem,
    SearchSummary,
)


class SearchUpdater:
    """Orchestrator that coordinates the search update pipeline.

    Delegates to:
    - SearchParser for title recognition + SearchSummary creation
    - ChangeDetector for diffing old vs new snapshots
    - CoordinatesResolver for geocoding addresses
    """

    def __init__(
        self,
        db_client: DBClient,
        forum_client: ForumClient,
        search_parser: SearchParser | None = None,
        change_detector: ChangeDetector | None = None,
        coordinates_resolver: CoordinatesResolver | None = None,
    ) -> None:
        self.forum = forum_client
        self.db = db_client
        self.folders_with_events = set(self.db.get_folders_with_events_only())
        self.search_parser = search_parser or SearchParser(CoordinatesResolver(db_client))
        self.change_detector = change_detector or ChangeDetector()
        self.coordinates_resolver = coordinates_resolver or CoordinatesResolver(db_client)

    def update_search(self, search_id: int) -> list[int]:
        """process one forum search: check for updates, upload them into cloud sql"""

        change_log_ids = []

        item = self.forum.parse_search(search_id)
        if not item:
            return []

        if item.folder_id in self.db.get_the_list_of_ignored_folders():
            # TODO parse folder_id
            return []

        now_ = datetime.now()
        summary = self.search_parser.parse(now_, item, self.folders_with_events)
        if not summary:
            return []

        change_log_ids = self._update_change_log_and_search(summary, item)

        return change_log_ids

    def _update_change_log_and_search(self, search_summary: SearchSummary, item: ForumSearchItem) -> list[int]:
        """update of SQL tables 'searches' and 'change_log' on the changes vs previous parse"""
        self.db.rewrite_snapshot_in_sql(search_summary)
        current_snapshot = self.db.get_current_snapshot(search_summary.topic_id)
        # TODO maybe we dont need snapshots at all. new_folder_summary is enough.

        prev_search = self.db.get_search_by_id(search_summary.topic_id)

        change_log_ids = self._write_updated_search_to_changelog(current_snapshot, prev_search)
        new_change_log_ids = self._write_new_search_to_changelog(current_snapshot, prev_search, item)
        change_log_ids.extend(new_change_log_ids)

        self._update_changed_searches(current_snapshot, prev_search)
        self._update_coordinates_of_search(search_summary, item)

        return change_log_ids

    def _update_changed_searches(self, snapshot: SearchSummary | None, search: SearchSummary | None) -> None:
        if not snapshot or not search:
            return

        if (
            snapshot.status != search.status
            or snapshot.title != search.title
            or snapshot.num_of_replies != search.num_of_replies
        ):
            self.db.delete_search(search.topic_id)
            self.db.write_search(snapshot)

    def _write_new_search_to_changelog(
        self, new_search_summary: SearchSummary | None, prev_search: SearchSummary | None, item: ForumSearchItem
    ) -> list[int]:
        if prev_search or not new_search_summary:
            return []

        change_log_ids: list[int] = []

        search_num = new_search_summary.topic_id
        parsed_profile_text = item.raw_search_text or ''
        search_activities = profile_get_type_of_activity(parsed_profile_text)
        managers = profile_get_managers(parsed_profile_text)

        self.db.write_search(new_search_summary)
        self.db.update_search_activities(search_num, search_activities)
        self.db.update_search_managers(search_num, managers)

        line = ChangeLogLine(
            parsed_time=new_search_summary.parsed_time,
            topic_id=new_search_summary.topic_id,
            changed_field='new_search',
            new_value=new_search_summary.title,
            parameters='',
            change_type=ChangeType.topic_new,
        )
        # TODO can we collect all ChangeLogLine creation on one place?

        change_log_id = self.db.write_change_log(line)
        change_log_ids.append(change_log_id)

        return change_log_ids

    def _write_updated_search_to_changelog(
        self, snapshot: SearchSummary | None, prev_search: SearchSummary | None
    ) -> list[int]:
        if not prev_search or not snapshot:
            return []

        change_log_ids: list[int] = []

        there_are_inforg_comments = self._parse_comments_and_detect_inforg_comments(snapshot, prev_search)
        changes = self.change_detector.detect(snapshot, prev_search, there_are_inforg_comments)

        for line in changes:
            change_log_id = self.db.write_change_log(line)
            change_log_ids.append(change_log_id)

        return change_log_ids

    def _parse_comments_and_detect_inforg_comments(
        self, snapshot_line: SearchSummary, searches_line: SearchSummary
    ) -> bool:
        logging.info(f'parsing comments for search {searches_line.topic_id}. {snapshot_line=}, {searches_line=}')
        if snapshot_line.num_of_replies <= searches_line.num_of_replies:
            return False

        there_are_inforg_comments = False
        for comment_number in range(searches_line.num_of_replies + 1, snapshot_line.num_of_replies + 1):
            logging.info(f'parsing comment {comment_number}')
            comment_data = self.forum.get_comment_data(snapshot_line.topic_id, comment_number)
            if not comment_data:
                continue

            logging.info(f'Parsed comment: {comment_data=}')
            self.db.write_comment(comment_data)

            there_are_inforg_comments = there_are_inforg_comments or comment_data.inforg_comment_present

        return there_are_inforg_comments

    def _update_coordinates_of_search(self, search: SearchSummary, item: ForumSearchItem) -> None:
        """Record search coordinates to PSQL"""
        search_id = search.topic_id
        search_status = search.new_status

        if search_status not in {'Ищем', 'СТОП'}:
            return

        logging.info(f'search coordinates should be saved for {search_id=}')
        coords = self._parse_coordinates_of_search(search_id, item)

        self.db.update_coordinates_in_db(search_id, coords[0], coords[1], coords[2])

    def _parse_coordinates_of_search(self, search_num: int, item: ForumSearchItem) -> tuple[float, float, CoordType]:
        """finds coordinates of the search"""

        # DEBUG - function execution time counter
        func_start = datetime.now()

        lat, lon, coord_type = item.lat or 0.0, item.lon or 0.0, item.coord_type or CoordType.unknown

        # FOURTH CASE = COORDINATES FROM ADDRESS
        if not lat:
            try:
                address = parse_address_from_title(item.title)
                if address:
                    self.db.save_place_in_psql(address, search_num)
                    resolved_lat, resolved_lon = self.coordinates_resolver.resolve(address)
                    lat = resolved_lat or 0.0
                    lon = resolved_lon or 0.0
                    if lat and lon:
                        coord_type = CoordType.type_4_from_title
                else:
                    logging.info(f'No address was found for search {search_num}, title {item.title}')
            except Exception:
                logging.exception('DBG.P.42.EXC')

        # DEBUG - function execution time counter
        func_finish = datetime.now()
        func_execution_time_ms = func_finish - func_start
        logging.info(f'the coordinates for {search_num=} are defined as {lat}, {lon}, {coord_type}')
        logging.debug(f'DBG.P.5.parse_coordinates() exec time: {func_execution_time_ms}')

        return lat, lon, coord_type
