from _dependencies import content


def test_clean_up_content():
    data = '<span>some text</span>'

    res = content.clean_up_content(data)
    assert res == 'some text'


def test_clean_up_content_2():
    data = '<span>some text</span>'

    res = content.clean_up_content_2(data)
    assert res == ['some text']
