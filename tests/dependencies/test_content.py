from _dependencies import content
from _dependencies.commons import add_tel_link


def test_clean_up_content():
    data = '<span>some text</span>'

    res = content.clean_up_content(data)
    assert res == 'some text'


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


def assert_string_equals_without_spaces(str1: str, str2: str):
    assert str1.replace(' ', '').replace('\n', '') == str2.replace(' ', '').replace('\n', '')
