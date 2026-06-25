import copy
import logging
import re
from datetime import datetime
from functools import lru_cache
from typing import no_type_check  # no_type_check for BeautifulSoup magic

from bs4 import BeautifulSoup
from requests import Session
from retry import retry
from yarl import URL

from _dependencies.common.commons import get_forum_proxies
from _dependencies.forum.content import content_is_unaccessible, is_forum_unavailable
from _dependencies.forum.topic_management import save_visibility_for_topic

from .database import get_db_client
from .topics_commons import CoordType, ForumCommentItem, ForumSearchItem


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

    @classmethod
    @no_type_check
    def _parse_title(cls, soup: BeautifulSoup) -> str:
        """Extract topic title from <h2 class="topic-title"><a>...</a></h2>"""
        title_tag = soup.find('h2', class_='topic-title')
        if not title_tag:
            return ''
        link_tag = title_tag.find('a')
        if not link_tag:
            return ''
        return re.sub(r'\s+', ' ', link_tag.get_text(strip=True))

    @classmethod
    @no_type_check
    def _parse_start_datetime(cls, soup: BeautifulSoup) -> datetime | str:
        """Extract start datetime from first <p class="author"> -> <time datetime="...">"""
        first_author = soup.find('p', class_='author')
        if not first_author:
            return ''
        time_tag = first_author.find('time')
        if time_tag and time_tag.has_attr('datetime'):
            return datetime.fromisoformat(time_tag['datetime'])
        return ''

    @classmethod
    @no_type_check
    def _parse_replies_count(cls, soup: BeautifulSoup) -> int:
        """Extract replies count from pagination div text (e.g. '123 сообщения')"""
        pagination_div = soup.find('div', class_='pagination')
        if not pagination_div:
            return 0
        pagination_text = pagination_div.get_text(strip=True)
        match = re.search(r'(\d+)\s*сообщени', pagination_text)
        if not match:
            return 0
        replies_count = int(match.group(1))
        return replies_count - 1  # first message is topic itself, and following are replies

    @classmethod
    @no_type_check
    def _parse_folder_id(cls, soup: BeautifulSoup) -> int:
        """Extract folder ID from jumpbox-return link href (e.g. '...?f=42')"""
        folder_tag = soup.find('p', class_='jumpbox-return')
        if not folder_tag:
            return 0
        link_tag = folder_tag.find('a')
        if not link_tag or not link_tag.has_attr('href'):
            return 0
        match = re.search(r'[?&]f=(\d+)', link_tag['href'])
        if not match:
            return 0
        return int(match.group(1))

    @classmethod
    @no_type_check
    def _parse_content_section(cls, soup: BeautifulSoup) -> tuple[float, float, CoordType, str | None]:
        """Parse coordinates and raw_search_text from the first post content div.

        These are kept together because coordinate parsing mutates the soup
        (removing <br> tags), which raw_search_text must account for by using a copy.
        """
        content_div = soup.find('div', 'content')
        if not content_div:
            return 0.0, 0.0, CoordType.unknown, None

        # Remove <br> tags (needed for coordinate parsing)
        for br in content_div.find_all('br'):
            br.extract()

        # --- Coordinates (3 cases) ---
        lat, lon, coord_type = 0.0, 0.0, CoordType.unknown
        for case_func, case_type in [
            (_parse_coords_case_1, CoordType.type_1_exact),
            (_parse_coords_case_2, CoordType.type_2_wo_word),
            (_parse_coords_case_3, CoordType.type_3_deleted),
        ]:
            if not lat:
                try:
                    coord_type = case_type
                    lat, lon = case_func(content_div)
                except Exception:
                    logging.exception(f'Error extracting coordinates {case_type}')

        # --- Raw search text (needs a copy to avoid mutating the soup used above) ---
        text_soup = copy.copy(content_div)
        for deleted in text_soup.find_all('span', {'style': 'text-decoration:line-through'}):
            deleted.extract()
        for a_tag in text_soup.find_all('a'):
            href = a_tag.get('href')
            if href and (href.startswith('https://telegram.im/') or href.startswith('https://t.me/')):
                a_tag.replace_with(a_tag['href'])
        raw_search_text = text_soup.text.strip()
        logging.debug('DBG.Profile:' + raw_search_text)

        return lat, lon, coord_type, raw_search_text or None

    @no_type_check
    def parse_search(self, search_num: int) -> ForumSearchItem | None:
        """Parse a forum topic page and return all extracted data in one pass.

        Extracts: title, folder_id, start_datetime, replies_count,
        coordinates (lat/lon/coord_type), and raw_search_text from the first post.
        """
        content = self._get_topic_content(search_num)
        if not is_content_visible(content, search_num):
            return None

        soup = BeautifulSoup(content, features='lxml')

        lat, lon, coord_type, raw_search_text = self._parse_content_section(soup)

        return ForumSearchItem(
            search_id=search_num,
            folder_id=self._parse_folder_id(soup),
            title=self._parse_title(soup),
            start_datetime=self._parse_start_datetime(soup),
            replies_count=self._parse_replies_count(soup),
            lat=lat,
            lon=lon,
            coord_type=coord_type,
            raw_search_text=raw_search_text,
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
        comment_link = search_code_blocks.find('p', 'author').find_next('a')['href']
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
    def get_replies_count(self, search_num: int) -> int:
        """parse topic and get count of comments"""
        content = self._get_topic_content(search_num)
        if not is_content_visible(content, search_num):
            return 0

        soup = BeautifulSoup(content, features='lxml')
        pagination_div = soup.find('div', class_='pagination')
        if pagination_div is None:
            return 0

        pagination_text = pagination_div.get_text(strip=True)
        # pagination_text looks like: "3 сообщения•Страница1из1"
        match = re.search(r'(\d+)\s*сообщени', pagination_text)
        if match:
            return int(match.group(1))
        return 0

    def _get_comment_url(self, search_num: int, comment_num: int) -> str:
        return f'https://lizaalert.org/forum/viewtopic.php?&t={search_num}&start={comment_num}'

    @retry(Exception, tries=5, delay=1, backoff=2)
    def _get_comment_content(self, search_num: int, comment_num: int) -> bytes:
        url = self._get_comment_url(search_num, comment_num)
        resp = self.session.get(url, timeout=self._TIMEOUT)
        resp.raise_for_status()
        return resp.content

    @retry(Exception, tries=5, delay=1, backoff=2)
    def _get_topic_content(self, search_num: int) -> bytes:
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
    for e in a.find_all('span'):
        e.replace_with(e.text)

        # removing <img> tags
    for e in a.find_all('img'):
        e.extract()

        # removing <a> tags
    for e in a.find_all('a'):
        e.extract()

        # removing <strong> tags
    for e in a.find_all('strong'):
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
