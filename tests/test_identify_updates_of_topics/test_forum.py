from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from identify_updates_of_topics._utils.forum import ForumClient, is_content_visible
from identify_updates_of_topics._utils.topics_commons import CoordType, ForumCommentItem, ForumSearchItem


class TestForumClient:
    def test_get_folder_content_bytes(self, mock_http_get):
        mock_http_get.return_value.content = Path('tests/fixtures/forum_folder_276.html').read_bytes()
        forum_search_folder_id = 276
        forum_client = ForumClient()

        folder_content = forum_client._get_folder_content(forum_search_folder_id)

        assert len(folder_content) > 0

    def test_get_folder_content(self, mock_http_get):
        mock_http_get.return_value.content = Path('tests/fixtures/forum_folder_276.html').read_bytes()
        forum_search_folder_id = 276
        forum_client = ForumClient()

        folder_content_summaries = forum_client.get_folder_searches(forum_search_folder_id)

        assert folder_content_summaries == [
            ForumSearchItem(
                title='Жив Иванов Иван, 10 лет, ЗАО, г. Москва',
                search_id=85471,
                replies_count=29,
                start_datetime=datetime(2025, 1, 13, 14, 10, 25, tzinfo=timezone.utc),
            ),
            ForumSearchItem(
                title='Пропал Петров Петр Петрович, 48 лет, ЗелАО, г. Москва - Тверская обл.',
                search_id=81634,
                replies_count=116,
                start_datetime=datetime(2024, 8, 27, 15, 40, 22, tzinfo=timezone.utc),
            ),
        ]

    def test_get_comment_data(self, mock_http_get):
        mock_http_get.return_value.content = Path('tests/fixtures/forum_comment.html').read_bytes()
        forum_client = ForumClient()

        comment_data = forum_client.get_comment_data(1, 2)

        assert comment_data == ForumCommentItem(
            search_num=1,
            comment_num=2,
            comment_url='https://lizaalert.org/forum/viewtopic.php?&t=1&start=2',
            comment_author_nickname='Инфорг',
            comment_author_link=5735,
            comment_forum_global_id=745371,
            comment_text='Дома Д. Саша ГСН Nordheim ГСН',
            ignore=False,
            inforg_comment_present=True,
        )

    def test_parse_search_profile_mock(self, mock_http_get):
        mock_http_get.return_value.content = Path('tests/fixtures/forum_topic.html').read_bytes()
        forum_client = ForumClient()

        left_text = forum_client.parse_search_profile(1)

        expected = """
        Сидорова (Иванова) Надежда Петровна, 30 лет, д. Никольская Слобода, 
        Жуковский р-он, Брянская обл. 6 октября 2024 года заблудилась в лесу. 
        Приметы: рост 156 см, худощавого телосложения, волосы рыжие, глаза голубые. 
        Была одета: темно-синяя куртка, синие спортивные штаны, разноцветые резиновые сапоги, платок. 
        С собой: желтый рюкзак. 
        Карты 
        Ориентировка на печать 
        Ориентировка на репост 
        -------------------------------------------------- 
        Найдена, жива. 
        СБОР: Координаты сбора: 
        ШТАБ Координаты штаба: 
        СНМ: Лагутин Саша Инфорги: Светлана gLA_NAs 89001234567, 89001234567 
        https://t.me/gLA_NAs Ольга Вжик 89001234567, 89001234567 
        https://t.me/Ol_Massarova Предоставлять комментарии по поиску для СМИ 
        могут только координатор или инфорг поиска, а также представители пресс-службы «ЛизаАлерт».
        Если же представитель СМИ хочет приехать на поиск, он может сообщить 
        о своем желании на горячую линию отряда 8(800)700-54-52 
        или на почту smi@lizaalert.org
        """
        assert _normallize_text(expected) == _normallize_text(left_text)

    def test_parse_search_coordinates(self, mock_http_get):
        mock_http_get.return_value.content = Path('tests/fixtures/forum_topic.html').read_bytes()
        forum_client = ForumClient()

        lat, lon, coord_type, title = forum_client.parse_coordinates_of_search(1)

        assert 'Никольская Слобода' in title
        assert lat == 53.510722
        assert lon == 33.637365
        assert coord_type == CoordType.type_3_deleted


def _normallize_text(text: str) -> str:
    return text.replace('\t', '').replace('\n', '').replace(' ', '')


def test_visibility_check():
    page_is_visible = is_content_visible(b'foo', 1)
    assert page_is_visible
