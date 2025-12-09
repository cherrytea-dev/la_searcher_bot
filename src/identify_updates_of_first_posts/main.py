"""Check if the first post of the search was updated in terms of field trips and coordinates change.
Result to be recorded into Change_log and triggered another script identify_updates_of_folders."""

import ast
import copy
import datetime
import difflib
import logging
import re
from functools import lru_cache
from typing import Iterator

import requests
import sqlalchemy
from bs4 import BeautifulSoup

from _dependencies.commons import (
    ChangeLogSavedValue,
    ChangeType,
    get_forum_proxies,
    setup_logging,
    sqlalchemy_get_pool,
)
from _dependencies.content import clean_up_content_2
from _dependencies.misc import generate_random_function_id
from _dependencies.pubsub import (
    Ctx,
    notify_admin,
    process_pubsub_message,
    pubsub_compose_notifications,
    pubsub_parse_folders,
)

setup_logging(__package__)


@lru_cache
def get_requests_session() -> requests.Session:
    session = requests.Session()
    session.proxies.update(get_forum_proxies())
    return session


def sql_connect() -> sqlalchemy.engine.Engine:
    return sqlalchemy_get_pool(5, 30)


def compose_diff_message(curr_list: list[str], prev_list: list[str]) -> ChangeLogSavedValue:
    if not curr_list or not prev_list:
        return ChangeLogSavedValue.model_construct()

    diff = difflib.unified_diff(prev_list, curr_list, lineterm='')
    deletions, additions = _extract_changes(diff)
    message = _format_message(deletions, additions)

    return ChangeLogSavedValue.model_construct(
        deletions=deletions,
        additions=additions,
        message=message,
    )


def _extract_changes(diff: Iterator[str]) -> tuple[list[str], list[str]]:
    deletions: list[str] = []
    additions: list[str] = []
    for line in diff:
        if line[0] == '-':
            _append_change(deletions, line)
        elif line[0] == '+':
            _append_change(additions, line)
    return deletions, additions


def _append_change(change_list: list[str], line: str) -> None:
    change = re.sub(r'^[\s+-]+', '', line)
    if change:
        change_list.append(change)


def _format_message(deletions: list[str], additions: list[str]) -> str:
    message_parts = []
    if deletions:
        message_parts.append(_format_deletions(deletions))
    if additions:
        message_parts.append(_format_additions(additions))
    return '\n'.join(message_parts)


def _format_deletions(deletions: list[str]) -> str:
    return 'Удалено:\n<s>' + ''.join(f'{line}\n' for line in deletions) + '</s>'


def _format_additions(additions: list[str]) -> str:
    formatted_additions = []
    for line in additions:
        updated_line = re.sub(r'0?[3-8]\d\.\d{1,10}.{0,3}([2-9]\d|1\d{2})\.\d{1,10}', r'<code>\g<0></code>', line)
        formatted_additions.append(updated_line)
    return 'Добавлено:\n' + ''.join(f'{line}\n' for line in formatted_additions)


def process_first_page_comparison(
    conn: sqlalchemy.engine.Connection, search_id: int, first_page_content_prev: str, first_page_content_curr: str
) -> ChangeLogSavedValue | None:
    """compare first post content to identify any diffs"""

    # check the latest status on this search
    sql_text = sqlalchemy.text("""
        SELECT display_name, status, family_name, age, status
        FROM searches WHERE search_forum_num=:a;
                               """)

    what_is_saved_in_psql = conn.execute(sql_text, a=search_id).fetchone()

    if not what_is_saved_in_psql:
        logging.info('first page comparison failed – nothing is searches psql table')
        return None

    status = what_is_saved_in_psql[1]

    # updates are made only for non-finished searches
    if status != 'Ищем':
        return None

    prev_clean_content = clean_up_content_2(first_page_content_prev)
    curr_clean_content = clean_up_content_2(first_page_content_curr)

    message_schema = compose_diff_message(curr_clean_content, prev_clean_content)
    _notify_admin_if_no_changes(message_schema)
    return message_schema


def _notify_admin_if_no_changes(message_schema: ChangeLogSavedValue) -> None:
    # case when there is only 1 line changed and the change is in one blank space or letter – we don't notify abt it
    if len(message_schema.deletions) != 1 or len(message_schema.additions) != 1:
        return
    diff = difflib.ndiff(message_schema.deletions[0], message_schema.additions[0])
    changes = ''
    for line in diff:
        if line[0] in {'-', '+'}:
            changes += line[1:]
    changes = re.sub(r'\s', '', changes)  # changes in blank lines are irrelevant
    changes = re.sub(r'\D', '', changes, count=1)  # changes for only one letter – irrelevant (but not for digit)
    if not changes:
        notify_admin(f'[ide_posts]: IGNORED MINOR CHANGE: \ninit message:\n{message_schema}')


def save_new_record_into_change_log(
    conn: sqlalchemy.engine.Connection,
    search_id: int,
    new_value: str,
    changed_field: str,
    change_type: int,
) -> int:
    """save the coordinates change into change_log"""

    stmt = sqlalchemy.text("""
        INSERT INTO change_log (parsed_time, search_forum_num, changed_field, new_value, change_type)
        values (:a, :b, :c, :d, :e) 
        RETURNING id;
                           """)

    raw_data = conn.execute(
        stmt, a=datetime.datetime.now(), b=search_id, c=changed_field, d=new_value, e=change_type
    ).fetchone()
    change_log_id = raw_data[0]

    return change_log_id


def parse_search_folder_num(search_num: int) -> int | None:
    """parse search's folder number"""

    folder = None

    url = 'https://lizaalert.org/forum/viewtopic.php?t=' + str(search_num)
    r = get_requests_session().get(url)  # 10 seconds – do we need it in this script?
    content = r.content.decode('utf-8')

    soup = BeautifulSoup(content, features='html.parser')
    spans = soup.find_all('span', {'class': 'crumb'})

    for line in spans:
        try:
            folder = int(line['data-forum-id'])
        except:  # noqa
            pass

    return folder


def get_compressed_first_post(initial_text: str) -> str:
    """convert the initial html text of first post into readable string (for reading in SQL)"""

    compressed_string = ''

    if initial_text:
        text_to_soup = BeautifulSoup(initial_text, features='html.parser')

        basic_text_string = text_to_soup.text
        basic_text_string = basic_text_string.replace('\n', ' ')

        # width of text block in symbols
        block_width = 50

        list_from_string = [
            basic_text_string[i : i + block_width] for i in range(0, len(basic_text_string), block_width)
        ]

        for list_line in list_from_string:
            compressed_string += list_line + '\n'

    return compressed_string


def split_text_to_deleted_and_regular_parts(text: str) -> tuple[str, str]:
    """split text into two strings: one for deleted (line-through) text and second for regular"""

    soup = BeautifulSoup(text, features='html.parser')

    soup_without_deleted = copy.copy(soup)
    deleted_elements = soup_without_deleted.find_all('span', {'style': 'text-decoration:line-through'})
    for case in deleted_elements:
        case.decompose()
    non_deleted_text = str(soup_without_deleted)

    deleted_list = [
        item.getText(strip=False) for item in soup.find_all('span', {'style': 'text-decoration:line-through'})
    ]

    deleted_text = '\n'.join(deleted_list)

    return deleted_text, non_deleted_text


def _process_folders_with_updated_searches(
    context: Ctx,
    function_id: int,
    analytics_func_start: datetime.datetime,
    list_of_updated_searches: list[int],
    change_log_ids: list[int],
    conn: sqlalchemy.engine.Connection,
) -> None:
    # save folder number for the search that has an update
    list_of_folders_with_upd_searches = [parse_search_folder_num(search_id) for search_id in list_of_updated_searches]
    updated_searches = set((folder_num for folder_num in list_of_folders_with_upd_searches if folder_num))
    updated_searches_to_pubsub = [[folder_num, None] for folder_num in updated_searches]
    if not list_of_folders_with_upd_searches:
        return

    pubsub_parse_folders(updated_searches_to_pubsub)
    pubsub_compose_notifications(function_id, str(list_of_folders_with_upd_searches))


def _process_one_update(
    change_log_ids: list[int],
    conn: sqlalchemy.engine.Connection,
    search_id: int,
) -> None:
    # get the Current First Page Content

    first_page_content_curr, first_page_content_prev = _get_actual_and_previous_page_content(conn, search_id)
    if not first_page_content_curr or not first_page_content_prev:
        return

    try:
        # check the difference b/w first posts for current and previous version
        diff_message = process_first_page_comparison(conn, search_id, first_page_content_prev, first_page_content_curr)
        if not diff_message or not diff_message.message:
            return

        change_log_id = save_new_record_into_change_log(
            conn,
            search_id,
            diff_message.to_db_saved_value(),
            'topic_first_post_change',
            ChangeType.topic_first_post_change,
        )
        change_log_ids.append(change_log_id)

    except Exception as e:
        logging.exception('[ide_posts]: Error fired during output_dict creation.')
        notify_admin('[ide_posts]: Error fired during output_dict creation.')


def _get_actual_and_previous_page_content(conn: sqlalchemy.engine.Connection, search_id: int) -> tuple[str, str]:
    sql_text = sqlalchemy.text("""
        SELECT content, content_compact 
        FROM search_first_posts 
        WHERE search_id=:a AND actual = True;
                    """)
    raw_data = conn.execute(sql_text, a=search_id).fetchone()  # TODO result may be empty
    first_page_content_curr = raw_data[0]
    first_page_content_curr_compact = raw_data[1]

    # TODO: why we're doing it in this script but not in che_posts??
    # save compact first page content
    if not first_page_content_curr_compact:
        content_compact = get_compressed_first_post(first_page_content_curr)
        sql_text = sqlalchemy.text("""
            UPDATE search_first_posts 
            SET content_compact=:a
            WHERE search_id=:b AND actual = True;
                                        """)
        conn.execute(sql_text, a=content_compact, b=search_id)

        # get the Previous First Page Content
    sql_text = sqlalchemy.text("""
        SELECT content
        FROM search_first_posts
        WHERE search_id=:a AND actual=False
        ORDER BY timestamp DESC;
                                   """)
    first_page_content_prev = conn.execute(sql_text, a=search_id).fetchone()[0]  # TODO result may be empty

    logging.info(f'topic id {search_id} has an update of first post:')
    logging.info(f'first page content prev: {first_page_content_prev}')
    logging.info(f'first page content curr: {first_page_content_curr}')

    return first_page_content_curr, first_page_content_prev


def main(event: dict, context: Ctx) -> str:  # noqa
    """key function"""

    function_id = generate_random_function_id()
    analytics_func_start = datetime.datetime.now()

    # receive a list of searches where first post was updated
    message_from_pubsub = process_pubsub_message(event)
    list_of_updated_searches = ast.literal_eval(str(message_from_pubsub))

    if not list_of_updated_searches:
        return 'ok'

    pool = sql_connect()
    with pool.connect() as conn:
        try:
            change_log_ids: list[int] = []
            for search_id in list_of_updated_searches:
                _process_one_update(change_log_ids, conn, search_id)

            _process_folders_with_updated_searches(
                context, function_id, analytics_func_start, list_of_updated_searches, change_log_ids, conn
            )

        except Exception as e:
            logging.exception('exception in main function')

    pool.dispose()

    return 'ok'
