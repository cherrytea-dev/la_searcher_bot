import copy
import logging

import requests
from bs4 import BeautifulSoup

from _dependencies.commons import Topics, publish_to_pubsub
from identify_updates_of_topics._utils.topics_commons import block_of_profile_rough_code, get_requests_session


def define_start_time_of_search(blocks):
    """define search start time & date"""

    start_datetime_as_string = blocks.find('div', 'topic-poster responsive-hide left-box')
    start_datetime = start_datetime_as_string.time['datetime']

    return start_datetime


def visibility_check(resp: requests.Response, topic_id) -> bool:
    """check topic's visibility: if hidden or deleted"""

    check_content = resp.content.decode('utf-8')
    site_unavailable = '502 Bad Gateway' in check_content
    if site_unavailable:
        return False

    topic_deleted = 'Запрошенной темы не существует' in check_content
    topic_hidden = 'Для просмотра этого форума вы должны быть авторизованы' in check_content

    if topic_deleted or topic_hidden:
        visibility = 'deleted' if topic_deleted else 'hidden'
        publish_to_pubsub(Topics.topic_for_topic_management, {'topic_id': topic_id, 'visibility': visibility})
        # TODO can replace with direct sql query
        return False

    return True


def parse_search_profile(search_num: int) -> str | None:
    """get search activities list"""

    global block_of_profile_rough_code
    requests_session = get_requests_session()

    url_to_topic = f'https://lizaalert.org/forum/viewtopic.php?t={search_num}'

    r = requests_session.get(url_to_topic)  # noqa
    if not visibility_check(r, search_num):
        return None

    soup = BeautifulSoup(r.content, features='html.parser')

    # open the first post
    block_of_profile_rough_code = soup.find('div', 'content')

    # excluding <line-through> tags
    for deleted in block_of_profile_rough_code.findAll('span', {'style': 'text-decoration:line-through'}):
        deleted.extract()

    # add telegram links to text (to be sure next step won't cut these links)
    for a_tag in block_of_profile_rough_code.find_all('a'):
        href = a_tag.get('href')
        if href.startswith('https://telegram.im/') or href.startswith('https://t.me/'):
            a_tag.replace_with(a_tag['href'])

    left_text = block_of_profile_rough_code.text.strip()

    """DEBUG"""
    logging.info('DBG.Profile:' + left_text)

    return left_text
