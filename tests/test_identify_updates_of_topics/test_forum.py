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

    def test_parse_search(self, mock_http_get):
        mock_http_get.return_value.content = Path('tests/fixtures/forum_topic.html').read_bytes()
        forum_client = ForumClient()

        search_data = forum_client.parse_search(1)

        assert (
            search_data.title
            == 'Жива (Иванова) Надежда Петровна, 30 лет, д. Никольская Слобода, Жуковский р-он, Брянская обл.'
        )
        assert search_data.replies_count == 2
        assert search_data.start_datetime == datetime.fromisoformat('2024-10-06T20:52:48+00:00')
        assert search_data.lat == 53.510722
        assert search_data.lon == 33.637365
        assert search_data.coord_type == CoordType.type_3_deleted
        assert search_data.folder_id == 424

        # Verify raw_search_text is populated correctly
        assert search_data.raw_search_text is not None
        assert 'Сидорова (Иванова) Надежда Петровна' in search_data.raw_search_text
        assert 'Найдена, жива' in search_data.raw_search_text
        # Telegram links should be preserved as plain text
        assert 'https://t.me/gLA_NAs' in search_data.raw_search_text
        assert 'https://t.me/Ol_Massarova' in search_data.raw_search_text


def test_visibility_check():
    page_is_visible = is_content_visible(b'foo', 1)
    assert page_is_visible
