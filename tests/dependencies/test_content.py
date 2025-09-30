import pytest

from _dependencies import content
from _dependencies.commons import _move_phone_links_outside_href_tags, add_tel_link, unify_phone_format


def test_clean_up_content():
    data = '<span>some text</span>'

    res = content.clean_up_content(data)
    assert res == 'some text'


def test_clean_up_content_unaccessible():
    data = '<span>Вы не авторизованы для чтения данного форума<span>'

    res = content.clean_up_content(data)
    assert res is None


def test_clean_up_content_2():
    data = '<span>some text</span>'

    res = content.clean_up_content_2(data)
    assert res == ['some text']


class TestAddLink:
    def test_link_created(self):
        input = """<s>Координатор-консультант: Николай
        Инфорг: Арина 89001234567 Написать Арина в Telegram
        </s>"""

        expected_output = """<s>Координатор-консультант: Николай
        Инфорг: Арина  <a href="tel:+79001234567">+79001234567</a>  Написать Арина в Telegram
        </s>"""

        res = add_tel_link(input)

        assert_string_equals_without_spaces(res, expected_output)

    def test_link_replaced(self):
        input = """
        Полезный текст
        <a href="https://foo.bar">+79001234567</a>
        """

        expected_output = """
        Полезный текст
        <a href="https://foo.bar">  </a><a href="tel:+79001234567">+79001234567</a>
        """

        res = add_tel_link(input)

        assert_string_equals_without_spaces(res, expected_output)

    def test_link_simple(self):
        input = 'Николай т.: +79001234567'

        expected_output = 'Николай т.:  <a href="tel:+79001234567">+79001234567</a> '

        res = add_tel_link(input)

        assert_string_equals_without_spaces(res, expected_output)

    def test_link_simple_inside_tag(self):
        input = '<s>Николай т.: +79001234567</s>'

        expected_output = '<s>Николай т.:  <a href="tel:+79001234567">+79001234567</a> </s>'

        res = add_tel_link(input)

        assert_string_equals_without_spaces(res, expected_output)

    def test_link_different_phones(self):
        input = """
        Николай т.: +79001234567
        Николай т.: +79001234568
        """

        expected_output = """
        Николай т.:  <a href="tel:+79001234567">+79001234567</a>
        Николай т.:  <a href="tel:+79001234568">+79001234568</a>
        """

        res = add_tel_link(input)

        assert_string_equals_without_spaces(res, expected_output)

    def test_link_equal_phones(self):
        input = """
        Николай т.: +79001234567
        Николай т.: +79001234567
        """

        expected_output = """
        Николай т.:  <a href="tel:+79001234567">+79001234567</a>
        Николай т.:  <a href="tel:+79001234567">+79001234567</a>
        """

        res = add_tel_link(input)

        assert_string_equals_without_spaces(res, expected_output)

    def test_link_equal_phones_and_tag(self):
        # search: https://lizaalert.org/forum/viewtopic.php?t=96147
        input = """
        <s>Николай т.: +79001234567</s>
        Николай т.: +79001234567
        """

        expected_output = """
        <s>Николай т.:  <a href="tel:+79001234567">+79001234567</a></s>
        Николай т.:  <a href="tel:+79001234567">+79001234567</a>
        """

        res = add_tel_link(input)

        assert_string_equals_without_spaces(res, expected_output)

    def test_link_comments_inside_href(self):
        # search: https://lizaalert.org/forum/viewtopic.php?t=97113
        # input taken from message_composer
        # comment text with phone is inside <a href> tags
        input = """
<a href="comment1_url">Тест +78001234567 забирает 3, 4, 5 задачи.</a>
<a href="comment2_url">Тест забираю 3.4.5 88001234567</a>     
    """

        res = add_tel_link(input)

        assert 'tel:+78001234567"=""' not in res
        assert '"=""' not in res

    def test_move_links_outside(self):
        # nested phone links should be extracted
        input = '<a href="comment1_url">Тест <a href="tel:+78001234567 ">+78001234567</a> едет.</a>'
        expected = '<a href="comment1_url">Тест  едет.</a><a href="tel:+78001234567 ">+78001234567</a>'

        res = _move_phone_links_outside_href_tags(input)
        assert res == expected

    def test_unify_phone_format(self):
        text = ' 88001234567 +78001234567 88002222222'
        text = unify_phone_format(text)
        assert text == ' +78001234567 +78001234567 +78002222222'


def assert_string_equals_without_spaces(str1: str, str2: str):
    assert str1.replace(' ', '').replace('\n', '') == str2.replace(' ', '').replace('\n', '')


@pytest.mark.parametrize(
    'post_content',
    [
        '502 bad gateway',
        '503 service temporarily unavailable',
        'sql error [ mysqli ]',
        '429 too many requests',
        'too many connections',
        '403 forbidden',
        'general error ..... return to index page',
    ],
)
def test_forum_unavailable(post_content):
    assert content.is_forum_unavailable(post_content)


@pytest.mark.parametrize(
    'post_content',
    [
        'foo',
        '',
        'sql error',
    ],
)
def test_forum_available(post_content):
    assert not content.is_forum_unavailable(post_content)
