import hashlib
import logging
import re
from dataclasses import dataclass

import requests

from _dependencies.commons import Topics, publish_to_pubsub
from _dependencies.misc import make_api_call
from _dependencies.recognition_schema import RecognitionResult


@dataclass
class FirstPostData:
    hash_num: str | None
    content: str
    forum_unavailable: bool
    not_found: bool
    topic_visibility: str | None


def define_topic_visibility_by_content(content: str) -> str:
    """define visibility for the topic's content: regular, hidden or deleted"""

    if content.find('Запрошенной темы не существует.') > -1:
        visibility = 'deleted'
    elif content.find('Для просмотра этого форума вы должны быть авторизованы') > -1:
        visibility = 'hidden'
    else:
        visibility = 'regular'

    return visibility


def parse_search(search_num: int) -> tuple[str, bool]:
    """parse the whole search page"""

    requests_session = requests.Session()

    try:
        url = f'https://lizaalert.org/forum/viewtopic.php?t={search_num}'
        r = requests_session.get(url, timeout=10)  # seconds – not sure if it is efficient in this case
        content = r.content.decode('utf-8')
        content = None if content.find('502 Bad Gateway') > 0 else content
        site_unavailable = False if content else True

    except requests.exceptions.RequestException as e:
        logging.info(f'[che_posts]: site unavailable: {e.__class__.__name__}')
        content = None
        site_unavailable = True

    return content, site_unavailable


def _recognize_status_with_title_recognize(title: str) -> str | None:
    data = {'title': title, 'reco_type': 'status_only'}
    title_reco_response = make_api_call('title_recognize', data)

    if title_reco_response and 'status' in title_reco_response.keys() and title_reco_response['status'] == 'ok':
        title_reco_dict = RecognitionResult.model_validate(title_reco_response['recognition'])
        return title_reco_dict.status
        # TODO validate whole response
    return None


def change_topic_status(topic_id: int, act_content: str) -> None:
    """block to check if Status of the search has changed – if so send a pub/sub to topic_management"""

    # get the Title out of page content (intentionally avoid BS4 to make pack slimmer)
    title = _parse_title(act_content)

    if not title:
        return

    # language=regexp
    status = _parse_status_from_title(title)

    if not status:
        status = _recognize_status_with_title_recognize(title)

    if not status or status == 'Ищем':
        return

    publish_to_pubsub(Topics.topic_for_topic_management, {'topic_id': topic_id, 'status': status})


def _parse_status_from_title(title: str) -> str | None:
    patterns = [[r'(?i)(^\W{0,2}|(?<=\W))(пропал[аи]?\W{1,3})', 'Ищем']]

    for pattern in patterns:
        if re.search(pattern[0], title):
            return pattern[1]
    return None


def _parse_title(act_content: str) -> str | None:
    pre_title = re.search(r'<h2 class="topic-title"><a href=.{1,500}</a>', act_content)
    pre_title = pre_title.group() if pre_title else None
    pre_title = re.search(r'">.{1,500}</a>', pre_title[32:]) if pre_title else None
    title = pre_title.group()[2:-4] if pre_title else None
    return title


def prettify_content(content: str) -> str:
    """remove the irrelevant code from the first page content"""

    # TODO - seems can be much simplified with regex
    # cut the wording of the first post
    start = content.find('<div class="content">')
    content = content[(start + 21) :]

    # find the next block and limit the content till this block
    next_block = content.find('<div class="back2top">')
    content = content[: (next_block - 12)]

    # cut out div closure
    fin_div = content.rfind('</div>')
    content = content[:fin_div]

    # cut blank symbols in the end of code
    finish = content.rfind('>')
    content = content[: (finish + 1)]

    # exclude dynamic info – views of the pictures
    patterns = re.findall(r'\) \d+ просмотр(?:а|ов)?', content)
    if patterns:
        for word in patterns:
            content = content.replace(word, ')')

    # exclude dynamic info - token / creation time / sid / etc / footer
    patterns_list = [
        r'value="\S{10}"',
        r'value="\S{32}"',
        r'value="\S{40}"',
        r'sid=\S{32}&amp;',
        r'всего редактировалось \d+ раз.',  # AK:issue#9
        r'<span class="footer-info"><span title="SQL time:.{120,130}</span></span>',
    ]

    patterns = []
    for pat in patterns_list:
        patterns += re.findall(pat, content)

    for word in patterns:
        content = content.replace(word, '')

    return content


def get_first_post(search_num: int) -> FirstPostData:
    """parse the first post of search"""

    cont, forum_unavailable = parse_search(search_num)
    not_found = True if cont and re.search(r'Запрошенной темы не существует', cont) else False

    if forum_unavailable or not_found:
        return FirstPostData(
            hash_num=None,
            content=cont,
            forum_unavailable=forum_unavailable,
            not_found=not_found,
            topic_visibility=None,
        )

    # FIXME – deactivated on Feb 6 2023 because seems it's not correct that this script should check status
    # FIXME – activated on Feb 7 2023 –af far as there were 2 searches w/o status updated
    change_topic_status(search_num, cont)
    topic_visibility = define_topic_visibility_by_content(cont)

    cont = prettify_content(cont)

    # craft a hash for this content
    hash_num = hashlib.md5(cont.encode()).hexdigest()

    return FirstPostData(
        hash_num=hash_num,
        content=cont,
        forum_unavailable=forum_unavailable,
        not_found=not_found,
        topic_visibility=topic_visibility,
    )


def define_topic_visibility_by_topic_id(search_num: int) -> tuple[bool, str]:
    """check is the existing search was deleted or hidden"""

    content, site_unavailable = parse_search(search_num)

    if site_unavailable:
        return None, None

    topic_visibility = define_topic_visibility_by_content(content)

    logging.info(f'visibility for search {search_num} is defined as {topic_visibility}')

    return site_unavailable, topic_visibility
