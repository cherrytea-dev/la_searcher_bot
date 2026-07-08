import datetime
import logging

from _dependencies.common.commons import ChangeType
from _dependencies.common.misc import age_writer

from .commons import SEARCH_TOPIC_TYPES, WINDOW_FOR_NOTIFICATIONS_DAYS, Comment, LineInChangeLog
from .database import DBClient


class LogRecordComposer:
    def __init__(self, db: DBClient, record_id: int | None = None) -> None:
        self.db = db
        self.record_id = record_id

    def get_line(self) -> LineInChangeLog | None:
        line = self._select_first_record_from_change_log(self.record_id)
        if not line:
            return None

        self._enrich_new_record(line)
        return line

    def _select_first_record_from_change_log(self, record_id: int | None = None) -> LineInChangeLog | None:
        """compose the New Records list of the unique New Records in Change Log: one Record = One line in Change Log"""

        one_line_in_change_log = self.db.select_first_change_log_record(self.record_id)

        if not one_line_in_change_log:
            logging.info('no new records found in PSQL')
            return None

        logging.info(f'new record is {one_line_in_change_log}')

        new_record = LineInChangeLog(
            forum_search_num=one_line_in_change_log[0],
            new_value=one_line_in_change_log[1],
            change_log_id=one_line_in_change_log[2],
            change_type=one_line_in_change_log[3],
        )

        # TODO - there was a filtering for duplication: Inforg comments vs All Comments, but after restructuring
        #  of the scrip tech solution stopped working. The new filtering solution to be developed

        logging.info(f'New Record composed from Change Log: {str(new_record)}')

        return new_record

    def _enrich_new_record(self, new_record: LineInChangeLog) -> None:
        # enrich New Records List with all the updates that should be in notifications
        self._enrich_new_record_from_searches(new_record)
        self._enrich_new_record_with_search_activities(new_record)
        self._enrich_new_record_with_managers(new_record)

        self._enrich_new_record_with_comments(new_record)
        self._enrich_new_record_with_inforg_comments(new_record)

        make_clickable_name(new_record)
        make_emoji(new_record)

    def _enrich_new_record_from_searches(self, r_line: LineInChangeLog) -> None:
        """add the additional data from Searches into New Records"""

        try:
            s_line = self.db.get_enriched_search_info(r_line.forum_search_num)

            if not s_line:
                logging.info('New Record WERE NOT enriched from Searches as there was no record in searches')
                logging.info(f'New Record is {r_line}')
                logging.exception(f'no search in searches table! forum_search_num={r_line.forum_search_num}')
                return

            r_line.status = s_line[1]
            r_line.link = f'https://lizaalert.org/forum/viewtopic.php?t={r_line.forum_search_num}'
            r_line.title = s_line[2]
            r_line.n_of_replies = s_line[3]
            r_line.name = define_family_name(r_line.title, s_line[4])  # cuz not all the records has names in S
            r_line.age = s_line[5]
            r_line.age_wording = age_writer(s_line[5])
            r_line.forum_folder = s_line[6]
            r_line.search_latitude = s_line[7]
            r_line.search_longitude = s_line[8]
            r_line.start_time = s_line[9]
            r_line.display_name = s_line[10]
            r_line.age_min = s_line[11]
            r_line.age_max = s_line[12]
            r_line.new_status = s_line[13]
            r_line.city_locations = s_line[14]
            r_line.topic_type_id = s_line[15]
            r_line.region = s_line[16]

            logging.info(f'TEMP - FORUM_FOLDER = {r_line.forum_folder}, while s_line = {str(s_line)}')
            logging.info(f'TEMP - CITY LOCS = {r_line.city_locations}')
            logging.info(f'TEMP - STATUS_OLD = {r_line.status}, STATUS_NEW = {r_line.new_status}')
            logging.info(f'TEMP - TOPIC_TYPE = {r_line.topic_type_id}')

            self._set_ignorance_mark(r_line)

            logging.info('New Record enriched from Searches')

        except Exception as e:
            logging.error('Not able to enrich New Records from Searches:')
            logging.exception(e)

    def _set_ignorance_mark(self, r_line: LineInChangeLog) -> None:
        """mark line as ignored in some cases"""

        if r_line.status != '\u0418\u0449\u0435\u043c' and r_line.change_type in {
            ChangeType.topic_new,
            ChangeType.topic_first_post_change,
        }:
            # case: when new search's status is already not "\u0418\u0449\u0435\u043c" - to be ignored
            r_line.ignore = True

        if r_line.change_type == ChangeType.topic_new:
            # we do not notify users on "new" topics appeared >=2 days ago:
            days_since_topic_start = (datetime.datetime.now() - r_line.start_time).days

            if days_since_topic_start >= 2:
                r_line.ignore = True

        # limit notification sending only for searches started 60 days ago
        # 60 days - is a compromise and can be reviewed if community votes for another setting
        latest_when_alert = r_line.start_time + datetime.timedelta(days=WINDOW_FOR_NOTIFICATIONS_DAYS)
        if latest_when_alert < datetime.datetime.now():
            FORUM_FOLDERS_OF_SAMARA = {333, 305, 334, 306, 190}
            if r_line.forum_folder not in FORUM_FOLDERS_OF_SAMARA:
                r_line.ignore = True

    def _enrich_new_record_with_search_activities(self, r_line: LineInChangeLog) -> None:
        """add the lists of current searches' activities to New Record"""

        r_line.activities = self.db.get_ongoing_activity_names(r_line.forum_search_num)

        logging.info('New Record enriched with Search Activities')

    def _enrich_new_record_with_managers(self, r_line: LineInChangeLog) -> None:
        """add the lists of current searches' managers to the New Record"""

        list_of_managers = self.db.get_all_manager_entries(r_line.forum_search_num)

        # look for matching Forum Search Numbers in New Records List & Search Managers

        for m_val in list_of_managers:
            # TODO can be multiple lines with 'managers'?
            if m_val != '[]':
                r_line.managers = m_val

        logging.info('New Record enriched with Managers')

    def _enrich_new_record_with_comments(self, r_line: LineInChangeLog) -> None:
        """add the lists of new comments comments to the New Record"""

        # look for matching Forum Search Numbers in New Record List & Comments
        if r_line.change_type not in {ChangeType.topic_inforg_comment_new, ChangeType.topic_comment_new}:
            return

        comments = self.db.get_unprocessed_comments_for_search(r_line.forum_search_num)
        r_line.comments = self._get_comments_from_query_result(list(comments))
        logging.info('New Record enriched with Comments for all')

    def _enrich_new_record_with_inforg_comments(self, r_line: LineInChangeLog) -> None:
        """add the lists of new inforg comments to the New Record"""

        # look for matching Forum Search Numbers in New Record List & Comments
        if r_line.change_type not in {ChangeType.topic_inforg_comment_new, ChangeType.topic_comment_new}:
            return

        comments = self.db.get_unprocessed_inforg_comments_for_search(r_line.forum_search_num)
        r_line.comments_inforg = self._get_comments_from_query_result(list(comments))
        logging.info('New Record enriched with Comments for inforg')

    def _get_comments_from_query_result(self, query_result: list[tuple]) -> list[Comment]:
        temp_list_of_comments: list[Comment] = []

        for c_line in query_result:
            comment = Comment(
                url=c_line[0],
                text=c_line[1],
                author_nickname=c_line[2],
                author_link=c_line[3],
                search_forum_num=c_line[4],
                num=c_line[5],
            )
            # check for empty comments
            if not comment.text or comment.text.lower().startswith('\u0440\u0435\u0437\u0435\u0440\u0432'):
                continue

                # some nicknames can be like >>\u0411\u0435\u043b\u044b\u0439<< which crashes html markup -> we delete symbols
            comment.author_nickname = comment.author_nickname.replace('>', '')
            comment.author_nickname = comment.author_nickname.replace('<', '')

            # limitation for extra long messages
            if len(comment.text) > 3500:
                comment.text = comment.text[:2000] + '...'

            temp_list_of_comments.append(comment)

        return temp_list_of_comments


def make_emoji(line: LineInChangeLog) -> None:
    """add specific emoji based on topic (search) type"""

    topic_type_id = line.topic_type_id
    topic_type_dict = {
        0: '',  # search regular
        1: '\U0001f3e0',  # search reverse
        2: '\U0001f6a3',  # search patrol
        3: '\U0001f393',  # search training
        4: '\u2139\ufe0f',  # search info support
        5: '\U0001f6a8',  # search resonance
        10: '\U0001f4dd',  # event
    }
    line.topic_emoji = topic_type_dict.get(topic_type_id, '')


def make_clickable_name(line: LineInChangeLog) -> None:
    """add clickable name to the record"""

    link_text = ''
    if line.topic_type_id in SEARCH_TOPIC_TYPES:  # if it's search
        if line.display_name:
            link_text = line.display_name
        else:
            name = line.name if line.name else '\u0411\u0412\u041f'
            age_info = f'{line.age_wording}' if (name[0].isupper() and line.age) else ''
            link_text = f'{name} {age_info}'.strip()
    else:  # if it's event or something else
        link_text = line.title

    line.clickable_name = f'<a href="{line.link}">{link_text}</a>'


def define_family_name(title_string: str, predefined_fam_name: str | None) -> str:
    """define family name if it's not available as A SEPARATE FIELD in Searches table"""

    # if family name is already defined
    if predefined_fam_name:
        return predefined_fam_name

    try:
        # if family name needs to be defined
        string_by_word = title_string.split()
        # exception case: when Family Name is third word
        # it happens when first two either \u041d\u0430\u0439\u0434\u0435\u043d \u0416\u0438\u0432 or \u041d\u0430\u0439\u0434\u0435\u043d \u041f\u043e\u0433\u0438\u0431 with different word forms
        if string_by_word[0].lower().startswith('\u043d\u0430\u0439\u0434'):
            return string_by_word[2]

        # case when "\u041f\u043e\u0438\u0441\u043a \u043f\u0440\u0438\u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d"
        elif string_by_word[1].lower().startswith('\u043f\u0440\u0438\u043e\u0441\u0442\u0430\u043d'):
            return string_by_word[2]

        # case when "\u041f\u043e\u0438\u0441\u043a \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d"
        elif string_by_word[1].lower().startswith('\u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b'):
            return string_by_word[2]

        # all the other cases
        else:
            return string_by_word[1]
    except:
        return title_string
