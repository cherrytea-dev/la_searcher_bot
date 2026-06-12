import logging

from _dependencies.commons import ChangeType

from .topics_commons import ChangeLogLine, SearchSummary


class ChangeDetector:
    """Pure functional diffing between old and new SearchSummary snapshots.

    No dependencies on DB, forum, or external APIs — easily unit-testable.
    """

    @staticmethod
    def detect(
        snapshot: SearchSummary,
        prev_search: SearchSummary,
        there_are_inforg_comments: bool,
    ) -> list[ChangeLogLine]:
        """Compare old vs new SearchSummary and produce ChangeLogLine entries.

        Detects changes in: status, title, number of replies, inforg comments.
        """
        logging.info(f'Comparing changes between new and old search info. Old: {prev_search}. New: {snapshot}')

        change_log_updates_list: list[ChangeLogLine] = []

        if snapshot.status != prev_search.status:
            change_log_updates_list.append(
                ChangeLogLine(
                    parsed_time=snapshot.parsed_time,
                    topic_id=snapshot.topic_id,
                    changed_field='status_change',
                    new_value=snapshot.status,
                    parameters='',
                    change_type=ChangeType.topic_status_change,
                )
            )

        if snapshot.title != prev_search.title:
            change_log_updates_list.append(
                ChangeLogLine(
                    parsed_time=snapshot.parsed_time,
                    topic_id=snapshot.topic_id,
                    changed_field='title_change',
                    new_value=snapshot.title,
                    parameters='',
                    change_type=ChangeType.topic_title_change,
                )
            )

        if snapshot.num_of_replies > prev_search.num_of_replies:
            change_log_updates_list.append(
                ChangeLogLine(
                    parsed_time=snapshot.parsed_time,
                    topic_id=snapshot.topic_id,
                    changed_field='replies_num_change',
                    new_value=snapshot.num_of_replies,
                    parameters='',
                    change_type=ChangeType.topic_comment_new,
                )
            )

            if there_are_inforg_comments:
                change_log_updates_list.append(
                    ChangeLogLine(
                        parsed_time=snapshot.parsed_time,
                        topic_id=snapshot.topic_id,
                        changed_field='inforg_replies',
                        new_value=snapshot.num_of_replies,
                        parameters='',
                        change_type=ChangeType.topic_inforg_comment_new,
                    )
                )

        if snapshot.folder_id != prev_search.folder_id:
            logging.info(
                (
                    f'Folder was changed for search {snapshot.topic_id}. '
                    f'Old value: {prev_search.folder_id}, new value: {snapshot.folder_id}'
                )
            )

        return change_log_updates_list
