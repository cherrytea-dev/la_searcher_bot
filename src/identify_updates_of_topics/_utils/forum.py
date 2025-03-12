import copy
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import requests
from bs4 import BeautifulSoup, SoupStrainer
from requests import Session

from _dependencies.commons import Topics, publish_to_pubsub
from identify_updates_of_topics._utils.topics_commons import block_of_profile_rough_code


def define_start_time_of_search(blocks):
    """define search start time & date"""

    start_datetime_as_string = blocks.find('div', 'topic-poster responsive-hide left-box')
    start_datetime = start_datetime_as_string.time['datetime']

    return start_datetime


def visibility_check(resp: requests.Response, topic_id) -> bool:
    """check topic's visibility: if hidden or deleted"""

    return visibility_check_content(resp.content, topic_id)


def visibility_check_content(content: bytes, topic_id) -> bool:
    """check topic's visibility: if hidden or deleted"""

    check_content = content.decode('utf-8')
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


@dataclass
class ForumSearchItem:
    title: str
    search_id: int
    replies_count: int
    start_datetime: str


@dataclass
class ForumCommentItem:
    search_num: int
    comment_num: int
    comment_url: str
    comment_author_nickname: str
    comment_author_link: str
    comment_forum_global_id: int
    comment_text: str
    ignore: bool
    inforg_comment_present: bool


@lru_cache
def get_requests_session() -> Session:
    return Session()


class ForumClient:
    def __init__(self):
        self.session = get_requests_session()

    def _get_folder_content(self, folder_id: int) -> bytes:
        url = f'https://lizaalert.org/forum/viewforum.php?f={folder_id}'
        resp = self.session.get(url, timeout=10)  # for every folder - req'd daily at night forum update # noqa
        resp.raise_for_status()
        return resp.content

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

    def _get_comment_url(self, search_num: int, comment_num: int) -> str:
        return f'https://lizaalert.org/forum/viewtopic.php?&t={search_num}&start={comment_num}'

    def _get_comment_content(self, search_num: int, comment_num: int) -> bytes:
        url = self._get_comment_url(search_num, comment_num)
        resp = self.session.get(url, timeout=10)  # for every folder - req'd daily at night forum update # noqa
        resp.raise_for_status()
        return resp.content

    def get_comment_data(self, search_num: int, comment_num: int) -> ForumCommentItem | None:
        content = self._get_comment_content(search_num, comment_num)
        if not visibility_check_content(content, search_num):
            return None

        soup = BeautifulSoup(content, features='lxml')
        search_code_blocks = soup.find('div', 'post')

        # finding USERNAME
        comment_author_block = search_code_blocks.find('a', 'username')
        if not comment_author_block:
            comment_author_block = search_code_blocks.find('a', 'username-coloured')
        try:
            comment_author_nickname = comment_author_block.text
        except Exception as e:
            logging.info(f'exception for search={search_num} and comment={comment_num}')
            logging.exception(e)
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
        comment_forum_global_id = int(search_code_blocks.find('p', 'author').findNext('a')['href'][-6:])

        # finding TEXT of the comment
        comment_text_0 = search_code_blocks.find('div', 'content')
        try:
            # external_span = comment_text_0.blockquote.extract()
            comment_text_1 = comment_text_0.text
        except Exception as e:
            logging.info(f'exception for search={search_num} and comment={comment_num}')
            logging.exception(e)
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

    def _get_topic_content(self, search_num: int) -> bytes:
        url = self._get_topic_url(search_num)
        resp = self.session.get(url, timeout=10)  # for every folder - req'd daily at night forum update # noqa
        resp.raise_for_status()
        return resp.content

    def _get_topic_url(self, search_num: int) -> str:
        return f'https://lizaalert.org/forum/viewtopic.php?t={search_num}'

    def parse_search_profile(self, search_num: int) -> str | None:
        """get raw search text"""
        content = self._get_topic_content(search_num)
        if not visibility_check_content(content, search_num):
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

    def parse_coordinates_of_search(self, search_num) -> tuple[float, float, str, str]:
        """finds coordinates of the search"""
        url_to_topic = self._get_topic_url(search_num)
        lat = 0
        lon = 0
        coord_type = ''
        search_code_blocks = None
        title = ''

        content = self._get_topic_content(search_num)
        if not visibility_check_content(content, search_num):
            return [0, 0, '', '']

        try:
            soup = BeautifulSoup(content, features='html.parser')

            # parse title
            title_code = soup.find('h2', {'class': 'topic-title'})
            title = title_code.text

            # open the first post
            search_code_blocks = soup.find('div', 'content')

            if not search_code_blocks:
                return [lat, lon, coord_type, title]

            # removing <br> tags
            for e in search_code_blocks.findAll('br'):
                e.extract()

        except Exception as e:
            logging.error(f'unable to parse a specific thread with address {url_to_topic} error is {repr(e)}')

        if not search_code_blocks:
            return [0, 0, '', '']

        # FIRST CASE = THERE ARE COORDINATES w/ a WORD Coordinates
        lat, lon, coord_type = _parse_coords_case_1(search_code_blocks)

        # SECOND CASE = THERE ARE COORDINATES w/o a WORD Coordinates
        if lat == 0:
            # make an independent variable
            lat, lon, coord_type = _parse_coords_case_2(search_code_blocks)

        # THIRD CASE = DELETED COORDINATES
        if lat == 0:
            # make an independent variable
            lat, lon, coord_type = _parse_coords_case_3(search_code_blocks)
        return [lat, lon, coord_type, title]


def _parse_coords_case_1(search_code_blocks: BeautifulSoup) -> tuple[float, float, str]:
    lat, lon, coord_type = 0, 0, ''
    try:
        # make an independent variable
        a = copy.copy(search_code_blocks)

        # remove a text with strike-through
        b = a.find_all('span', {'style': 'text-decoration:line-through'})
        for i in range(len(b)):
            b[i].decompose()

            # preparing a list of 100-character strings which starts with Coord mentioning
        e = []
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
        for i in range(len(e)):
            g = [float(s) for s in re.findall(r'-?\d+\.?\d*', e[i])]
            if len(g) > 1:
                for j in range(len(g) - 1):
                    try:
                        # Majority of coords in RU: lat in [40-80], long in [20-180], expected min format = XX.XXX
                        if (
                            3 < (g[j] // 10) < 8
                            and len(str(g[j])) > 5
                            and 1 < (g[j + 1] // 10) < 19
                            and len(str(g[j + 1])) > 5
                        ):
                            lat = g[j]
                            lon = g[j + 1]
                            coord_type = '1. coordinates w/ word coord'
                    except Exception as e2:
                        logging.exception('DBG.P.36.EXC. Coords-1:')

    except Exception as e:
        logging.exception('Can`t get coorditates from search_code_blocks')
    return lat, lon, coord_type


def _parse_coords_case_2(search_code_blocks: BeautifulSoup) -> tuple[float, float, str]:
    lat, lon, coord_type = 0, 0, ''
    a = copy.copy(search_code_blocks)

    try:
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
        g = [float(s) for s in re.findall(r'-?\d+\.?\d*', c)]
        if len(g) > 1:
            for j in range(len(g) - 1):
                try:
                    # Majority of coords in RU: lat in [40-80], long in [20-180], expected min format = XX.XXX
                    if (
                        3 < (g[j] // 10) < 8
                        and len(str(g[j])) > 5
                        and 1 < (g[j + 1] // 10) < 19
                        and len(str(g[j + 1])) > 5
                    ):
                        lat = g[j]
                        lon = g[j + 1]
                        coord_type = '2. coordinates w/o word coord'
                except Exception as e2:
                    logging.exception('DBG.P.36.EXC. Coords-2:')
    except Exception as e:
        logging.info('Exception 2')
        logging.exception(e)
        pass
    return lat, lon, coord_type


def _parse_coords_case_3(search_code_blocks: BeautifulSoup) -> tuple[float, float, str]:
    lat, lon, coord_type = 0, 0, ''

    a = copy.copy(search_code_blocks)

    try:
        # get a text with strike-through
        a = a.find_all('span', {'style': 'text-decoration:line-through'})
        if a:
            for line in a:
                b = re.sub(r'\n\s*\n', r' ', line.get_text().strip(), flags=re.M)
                c = re.sub(r'\n', r' ', b)
                g = [float(s) for s in re.findall(r'-?\d+\.?\d*', c)]
                if len(g) > 1:
                    for j in range(len(g) - 1):
                        try:
                            # Majority of coords in RU: lat in [40-80], long in [20-180],
                            # expected minimal format = XX.XXX
                            if (
                                3 < (g[j] // 10) < 8
                                and len(str(g[j])) > 5
                                and 1 < (g[j + 1] // 10) < 19
                                and len(str(g[j + 1])) > 5
                            ):
                                lat = g[j]
                                lon = g[j + 1]
                                coord_type = '3. deleted coord'
                        except Exception as e2:
                            logging.info('DBG.P.36.EXC. Coords-1:')
                            logging.exception(e2)
    except Exception as e:
        logging.info('exception:')
        logging.exception(e)
        pass
    return lat, lon, coord_type
