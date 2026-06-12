from datetime import datetime
from pathlib import Path

from identify_updates_of_topics._utils.forum import ForumClient, is_content_visible
from identify_updates_of_topics._utils.topics_commons import CoordType, ForumCommentItem


class TestForumClient:
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

    def test_get_raw_search_text(self, mock_http_get):
        mock_http_get.return_value.content = Path('tests/fixtures/forum_topic.html').read_bytes()
        forum_client = ForumClient()

        left_text = forum_client.get_raw_search_text(1)

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

    def test_get_replies_count(self, mock_http_get):
        mock_http_get.return_value.content = Path('tests/fixtures/forum_topic.html').read_bytes()
        forum_client = ForumClient()

        comments_count = forum_client.get_replies_count(1)

        assert comments_count == 2

    def test_parse_search(self, mock_http_get):
        mock_http_get.return_value.content = Path('tests/fixtures/forum_topic.html').read_bytes()
        forum_client = ForumClient()

        search_data = forum_client.parse_search(1)

        assert (
            search_data.title
            == 'Жива (Иванова) Надежда Петровна, 30 лет, д. Никольская Слобода, Жуковский р-он, Брянская обл.'
        )
        assert search_data.replies_count == 3
        assert search_data.start_datetime == datetime.fromisoformat('2024-10-06T20:52:48+00:00')
        assert search_data.lat == 53.510722
        assert search_data.lon == 33.637365
        assert search_data.coord_type == CoordType.type_3_deleted
        assert search_data.folder_id == 424


def _normallize_text(text: str) -> str:
    return text.replace('\t', '').replace('\n', '').replace(' ', '')


def test_visibility_check():
    page_is_visible = is_content_visible(b'foo', 1)
    assert page_is_visible
