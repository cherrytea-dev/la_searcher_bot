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

        assert res.strip() == expected_output.strip()

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

        assert res.strip() == expected_output.strip()
