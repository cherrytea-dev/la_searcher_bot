import copy
import logging
import re
from datetime import datetime
from functools import lru_cache
from typing import no_type_check  # no_type_check for BeautifulSoup magic

from bs4 import BeautifulSoup, SoupStrainer
from requests import Session
from retry import retry
from yarl import URL

from _dependencies.commons import get_forum_proxies
from _dependencies.content import content_is_unaccessible, is_forum_unavailable
from _dependencies.topic_management import save_visibility_for_topic

from .database import get_db_client
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
    site_unavailable = is_forum_unavailable(check_content)
    if site_unavailable:
        return False

    topic_deleted = 'Запрошенной темы не существует' in check_content
    topic_hidden = content_is_unaccessible(check_content)

    if topic_deleted or topic_hidden:
        visibility = 'deleted' if topic_deleted else 'hidden'

        with get_db_client().connect() as conn:
            save_visibility_for_topic(conn, topic_id, visibility)
        return False

    return True


@lru_cache
def get_requests_session() -> Session:
    session = Session()
    session.proxies.update(get_forum_proxies())
    return session


class ForumClient:
    _TIMEOUT = 30

    def __init__(self) -> None:
        self.session = get_requests_session()

    @no_type_check
    def get_raw_search_text(self, search_num: int) -> str | None:
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
    def parse_search(self, search_num: int) -> ForumSearchItem | None:
        content = self._get_topic_content(search_num)
        if not is_content_visible(content, search_num):
            return None

        soup = BeautifulSoup(content, features='lxml')

        # Parse title from <h2 class="topic-title"><a>...</a></h2>
        title_tag = soup.find('h2', class_='topic-title')
        title = ''
        if title_tag:
            link_tag = title_tag.find('a')
            if link_tag:
                title = re.sub(r'\s+', ' ', link_tag.get_text(strip=True))

        # Parse start_datetime from first <p class="author"> -> <time datetime="...">
        start_datetime = ''
        first_author = soup.find('p', class_='author')
        if first_author:
            time_tag = first_author.find('time')
            if time_tag and time_tag.has_attr('datetime'):
                start_datetime = datetime.fromisoformat(time_tag['datetime'])

        # Parse replies_count from pagination div (same logic as get_replies_count)
        replies_count = 0
        pagination_div = soup.find('div', class_='pagination')
        if pagination_div:
            pagination_text = pagination_div.get_text(strip=True)
            match = re.search(r'(\d+)\s*сообщения', pagination_text)
            if match:
                replies_count = int(match.group(1))

        lat, lon, coord_type, _ = self.parse_coordinates_of_search(search_num)
        # TODO merge functions

        # Parse folder_id from <h2 class="topic-title"><a href="./viewtopic.php?f=424&t=83087">...</a></h2>
        folder_id: int = 0
        if title_tag:
            link_tag = title_tag.find('a')
            if link_tag and link_tag.has_attr('href'):
                href = link_tag['href']
                match = re.search(r'[?&]f=(\d+)', href)
                if match:
                    folder_id = int(match.group(1))

        return ForumSearchItem(
            search_id=search_num,
            folder_id=folder_id,
            title=title,
            start_datetime=start_datetime,
            replies_count=replies_count,
            lat=lat,
            lon=lon,
            coord_type=coord_type,
        )

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

    @no_type_check
    def get_replies_count(self, search_num: int) -> int | None:
        """parse topic and get count of comments"""
        content = self._get_topic_content(search_num)
        if not is_content_visible(content, search_num):
            return None

        soup = BeautifulSoup(content, features='lxml')
        pagination_div = soup.find('div', class_='pagination')
        if pagination_div is None:
            return None

        pagination_text = pagination_div.get_text(strip=True)
        # pagination_text looks like: "3 сообщения•Страница1из1"
        match = re.search(r'(\d+)\s*сообщения', pagination_text)
        if match:
            return int(match.group(1))
        return None

    def _get_comment_url(self, search_num: int, comment_num: int) -> str:
        return f'https://lizaalert.org/forum/viewtopic.php?&t={search_num}&start={comment_num}'

    @retry(Exception, tries=5, delay=1, backoff=2)
    def _get_comment_content(self, search_num: int, comment_num: int) -> bytes:
        url = self._get_comment_url(search_num, comment_num)
        resp = self.session.get(url, timeout=self._TIMEOUT)
        resp.raise_for_status()
        return resp.content

    @lru_cache
    @retry(Exception, tries=5, delay=1, backoff=2)
    def _get_topic_content(self, search_num: int) -> bytes:
        """
        TODO it's better to merge all parsing functions into `parse_search`.
        But now it's important to release quick.
        So i'll just cache content to avoid multiple requests to forum.
        """
        url = self._get_topic_url(search_num)
        resp = self.session.get(url, timeout=self._TIMEOUT)
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
