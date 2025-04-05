import copy
import logging
import re
from datetime import datetime
from functools import lru_cache
from typing import Any, no_type_check  # no_type_check for BeautifulSoup magic

from bs4 import BeautifulSoup, SoupStrainer
from requests import Session
from yarl import URL

from _dependencies.commons import Topics, get_app_config, get_forum_proxies, publish_to_pubsub

from .topics_commons import CoordType, ForumCommentItem, ForumSearchItem


@no_type_check
def define_start_time_of_search(blocks):
    """define search start time & date"""

    start_datetime_as_string = blocks.find('div', 'topic-poster responsive-hide left-box')
    start_datetime = start_datetime_as_string.time['datetime']

    return datetime.fromisoformat(start_datetime)


def is_content_visible(content: bytes, topic_id: int) -> bool:
    """check topic's visibility: if hidden or deleted"""

    check_content = content.decode('utf-8')
    site_unavailable = (
        '502 Bad Gateway' in check_content
        or 'Too many connections' in check_content
        or '403 Forbidden' in check_content
    )
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


@lru_cache
def get_requests_session() -> Session:
    session = Session()
    session.proxies.update(get_forum_proxies())
    return session


class ForumClient:
    def __init__(self) -> None:
        self.session = get_requests_session()

    @no_type_check
    def parse_search_profile(self, search_num: int) -> str | None:
        """get raw search text"""
        content = self._get_topic_content(search_num)
        if not is_content_visible(content, search_num):
            return None
        soup = BeautifulSoup(content, features='html.parser')

        # open the first post
        code_blocks = soup.find('div', 'content')

        # excluding <line-through> tags
        for deleted in code_blocks.findAll('span', {'style': 'text-decoration:line-through'}):
            deleted.extract()

        # add telegram links to text (to be sure next step won't cut these links)
        for a_tag in code_blocks.find_all('a'):
            href = a_tag.get('href')
            if href.startswith('https://telegram.im/') or href.startswith('https://t.me/'):
                a_tag.replace_with(a_tag['href'])

        left_text = code_blocks.text.strip()

        """DEBUG"""
        logging.debug('DBG.Profile:' + left_text)

        return left_text

    @no_type_check
    def parse_coordinates_of_search(self, search_num: int) -> tuple[float, float, CoordType, str]:
        """finds coordinates of the search"""
        url_to_topic = self._get_topic_url(search_num)
        lat, lon, coord_type = 0.0, 0.0, CoordType.unknown
        search_code_blocks = None
        title = ''

        content = self._get_topic_content(search_num)
        if not is_content_visible(content, search_num):
            return [0.0, 0.0, CoordType.unknown, '']

        try:
            soup = BeautifulSoup(content, features='html.parser')

            # parse title
            title_code = soup.find('h2', {'class': 'topic-title'})
            title = title_code.text

            # open the first post
            search_code_blocks = soup.find('div', 'content')

            if not search_code_blocks:
                return [0, 0, CoordType.unknown, title]

            # removing <br> tags
            for e in search_code_blocks.findAll('br'):
                e.extract()

        except Exception as e:
            logging.error(f'unable to parse a specific thread with address {url_to_topic}')

        if not search_code_blocks:
            return [0, 0, CoordType.unknown, '']

        # FIRST CASE = THERE ARE COORDINATES w/ a WORD Coordinates
        try:
            coord_type = CoordType.type_1_exact
            lat, lon = _parse_coords_case_1(search_code_blocks)
        except Exception as e:
            logging.exception('Error extracting coordinates case 1')

        # SECOND CASE = THERE ARE COORDINATES w/o a WORD Coordinates
        if not lat:
            try:
                coord_type = CoordType.type_2_wo_word
                lat, lon = _parse_coords_case_2(search_code_blocks)
            except Exception as e:
                logging.exception('Error extracting coordinates case 2')

        # THIRD CASE = DELETED COORDINATES
        if not lat:
            try:
                coord_type = CoordType.type_3_deleted
                lat, lon = _parse_coords_case_3(search_code_blocks)
            except Exception as e:
                logging.exception('Error extracting coordinates case 3')

        return [lat, lon, coord_type, title]

    @no_type_check
    def get_folder_searches(self, folder_id: int) -> list[ForumSearchItem]:
        content = self._get_folder_content(folder_id)
        only_tag = SoupStrainer('div', {'class': 'forumbg'})
        soup = BeautifulSoup(content, features='lxml', parse_only=only_tag)
        search_code_blocks = soup.find_all('dl', 'row-item')
        del soup  # trying to free up memory

        summaries: list[ForumSearchItem] = []
        for i, data_block in enumerate(search_code_blocks):
            # First block is always not one we want
            if i == 0:
                continue

            # In rare cases there are aliases from other folders, which have static titles – and we're avoiding them
            if str(data_block).find('<dl class="row-item topic_moved">') > -1:
                continue

            # Current block which contains everything regarding certain search
            search_title_block = data_block.find('a', 'topictitle')
            # rare case: cleaning [size][b]...[/b][/size] tags
            search_title = re.sub(r'\[/?(b|size.{0,6}|color.{0,10})]', '', search_title_block.next_element)
            search_id = int(re.search(r'(?<=&t=)\d{2,8}', search_title_block['href']).group())
            search_replies_num = int(data_block.find('dd', 'posts').next_element)
            start_datetime = define_start_time_of_search(data_block)

            summaries.append(ForumSearchItem(search_title, search_id, search_replies_num, start_datetime))

        del search_code_blocks

        return summaries

    @no_type_check
    def get_comment_data(self, search_num: int, comment_num: int) -> ForumCommentItem | None:
        """parse all details on a specific comment in topic (by sequence number)"""
        content = self._get_comment_content(search_num, comment_num)
        if not is_content_visible(content, search_num):
            return None

        there_are_inforg_comments = False
        soup = BeautifulSoup(content, features='lxml')
        search_code_blocks = soup.find('div', 'post')

        # finding USERNAME
        comment_author_block = search_code_blocks.find('a', 'username')
        if not comment_author_block:
            comment_author_block = search_code_blocks.find('a', 'username-coloured')
        try:
            comment_author_nickname = comment_author_block.text
        except Exception as e:
            logging.exception(f'exception for search={search_num} and comment={comment_num}')
            comment_author_nickname = 'unidentified_username'

        if comment_author_nickname[:6].lower() == 'инфорг' and comment_author_nickname != 'Инфорг кинологов':
            there_are_inforg_comments = True

        # finding LINK to user profile
        try:
            comment_author_link = int(''.join(filter(str.isdigit, comment_author_block['href'][36:43])))

        except Exception as e:
            logging.info(
                'Here is an exception 9 for search '
                + str(search_num)
                + ', and comment '
                + str(comment_num)
                + ' error: '
                + repr(e)
            )
            try:
                comment_author_link = int(
                    ''.join(filter(str.isdigit, search_code_blocks.find('a', 'username-coloured')['href'][36:43]))
                )
            except Exception as e2:
                logging.info('Here is an exception 10' + repr(e2))
                comment_author_link = 'unidentified_link'

        # finding the global comment id
        comment_link = search_code_blocks.find('p', 'author').findNext('a')['href']
        url = URL(comment_link)
        comment_forum_global_id = int(url.query.get('p'))

        # finding TEXT of the comment
        comment_text_0 = search_code_blocks.find('div', 'content')
        try:
            # external_span = comment_text_0.blockquote.extract()
            comment_text_1 = comment_text_0.text
        except Exception as e:
            logging.exception(f'exception for search={search_num} and comment={comment_num}')
            comment_text_1 = comment_text_0.text
        comment_text = ' '.join(comment_text_1.split())

        # Define exclusions (comments of Inforg with "резерв" and "рассылка билайн"
        ignore = False
        if there_are_inforg_comments:
            if comment_text.lower().endswith('резерв') or comment_text.lower().endswith('рассылка билайн'):
                ignore = True

        return ForumCommentItem(
            search_num=search_num,
            comment_num=comment_num,
            comment_url=self._get_comment_url(search_num, comment_num),
            comment_author_nickname=comment_author_nickname,
            comment_author_link=comment_author_link,
            comment_forum_global_id=comment_forum_global_id,
            comment_text=comment_text,
            ignore=ignore,
            inforg_comment_present=there_are_inforg_comments,
        )

    def _get_folder_content(self, folder_id: int) -> bytes:
        url = f'https://lizaalert.org/forum/viewforum.php?f={folder_id}'
        resp = self.session.get(url, timeout=10)  # for every folder - req'd daily at night forum update # noqa
        resp.raise_for_status()
        return resp.content

    def _get_comment_url(self, search_num: int, comment_num: int) -> str:
        return f'https://lizaalert.org/forum/viewtopic.php?&t={search_num}&start={comment_num}'

    def _get_comment_content(self, search_num: int, comment_num: int) -> bytes:
        url = self._get_comment_url(search_num, comment_num)
        resp = self.session.get(url, timeout=10)  # for every folder - req'd daily at night forum update # noqa
        resp.raise_for_status()
        return resp.content

    def _get_topic_content(self, search_num: int) -> bytes:
        url = self._get_topic_url(search_num)
        resp = self.session.get(url, timeout=10)  # for every folder - req'd daily at night forum update # noqa
        resp.raise_for_status()
        return resp.content

    def _get_topic_url(self, search_num: int) -> str:
        return f'https://lizaalert.org/forum/viewtopic.php?t={search_num}'


@no_type_check
def _parse_coords_case_1(search_code_blocks: BeautifulSoup) -> tuple[float, float]:
    # make an independent variable
    a = copy.copy(search_code_blocks)

    # remove a text with strike-through
    b = a.find_all('span', {'style': 'text-decoration:line-through'})
    for i in range(len(b)):
        b[i].decompose()

    # preparing a list of 100-character strings which starts with Coord mentioning
    e: list[str] = []
    i = 0
    f = str(a).lower()

    while i < len(f):
        if f[i:].find('коорд') > 0:
            d = i + f[i:].find('коорд')
            e.append(f[d : (d + 100)])
            if d == 0 or d == -1:
                i = len(f)
            else:
                i = d + 1
        else:
            i = len(f)

        # extract exact numbers & match if they look like coordinates
    lat, lon = 0.0, 0.0
    for c in e:
        lat, lon = _extract_coords_from_string(c)

    return lat, lon


@no_type_check
def _parse_coords_case_2(search_code_blocks: BeautifulSoup) -> tuple[float, float]:
    a = copy.copy(search_code_blocks)

    # remove a text with strike-through
    b = a.find_all('span', {'style': 'text-decoration:line-through'})
    for i in range(len(b)):
        b[i].decompose()

        # removing <span> tags
    for e in a.findAll('span'):
        e.replace_with(e.text)

        # removing <img> tags
    for e in a.findAll('img'):
        e.extract()

        # removing <a> tags
    for e in a.findAll('a'):
        e.extract()

        # removing <strong> tags
    for e in a.findAll('strong'):
        e.replace_with(e.text)

        # converting to string
    b = re.sub(r'\n\s*\n', r' ', a.get_text().strip(), flags=re.M)
    c = re.sub(r'\n', r' ', b)

    return _extract_coords_from_string(c)


@no_type_check
def _parse_coords_case_3(search_code_blocks: BeautifulSoup) -> tuple[float, float]:
    lat, lon = 0.0, 0.0

    a = copy.copy(search_code_blocks)

    # get a text with strike-through
    a = a.find_all('span', {'style': 'text-decoration:line-through'})
    for line in a:
        b = re.sub(r'\n\s*\n', r' ', line.get_text().strip(), flags=re.M)
        c = re.sub(r'\n', r' ', b)
        lat, lon = _extract_coords_from_string(c)

    return lat, lon


def _extract_coords_from_string(search_str: str) -> tuple[float, float]:
    groups = [float(s) for s in re.findall(r'-?\d+\.?\d*', search_str)]
    if len(groups) < 2:
        return 0.0, 0.0

    lat, lon = 0.0, 0.0
    for i in range(len(groups) - 1):
        first, second = groups[i], groups[i + 1]
        if _check_if_coordinates(first, second):
            lat, lon = first, second
    return lat, lon


def _check_if_coordinates(first: float, second: float) -> bool:
    # Majority of coords in RU: lat in [40-80], long in [20-180], expected min format = XX.XXX
    if (3 < (first // 10) < 8 and len(str(first)) > 5) and (1 < (second // 10) < 19 and len(str(second)) > 5):
        return True
    return False
