from datetime import datetime

import pytest
from polyfactory.factories import DataclassFactory

from _dependencies.common.commons import ChangeLogSavedValue, ChangeType, TopicType
from compose_notifications._utils.commons import Comment, LineInChangeLog, User
from compose_notifications._utils.log_record_composer import make_clickable_name, make_emoji
from compose_notifications._utils.message_composer import MessageComposer
from tests.test_compose_notifications.factories import UserFactory


class LineInChageFactory(DataclassFactory[LineInChangeLog]):
    message = None
    clickable_name = ''
    topic_emoji = ''
    search_latitude = '56.1234'
    search_longitude = '60.1234'


def test_topic_emoji():
    record = LineInChageFactory.build(
        topic_type_id=TopicType.search_reverse,
    )
    assert not record.topic_emoji
    make_emoji(record)
    assert record.topic_emoji


class TestCommonMessageComposerClickableName:
    def test_clickable_name_topic_search_with_display_name(self):
        record = LineInChageFactory.build(
            topic_type_id=TopicType.search_reverse,
        )
        assert not record.clickable_name
        make_clickable_name(record)
        assert record.display_name in record.clickable_name

    def test_clickable_name_topic_search_without_display_name(self):
        record = LineInChageFactory.build(
            topic_type_id=TopicType.search_reverse,
            display_name='',
        )
        assert not record.clickable_name
        make_clickable_name(record)
        assert record.name in record.clickable_name

    def test_clickable_name_topic_not_search(self):
        record = LineInChageFactory.build(
            topic_type_id=TopicType.info,
        )
        assert not record.clickable_name
        make_clickable_name(record)
        assert record.title in record.clickable_name

    def test_clickable_name_escapes_html(self):
        """Raw < > & in forum title/display_name must not break Telegram HTML."""
        record = LineInChageFactory.build(
            topic_type_id=TopicType.info,
            title='Поиск <b>Иванов</b> & Ко ><',
        )
        make_clickable_name(record)
        assert '&lt;b&gt;' in record.clickable_name
        assert '&amp;' in record.clickable_name
        assert '&gt;&lt;' in record.clickable_name
        assert '<b>' not in record.clickable_name
        assert record.clickable_name.count('<a ') == record.clickable_name.count('</a>')


@pytest.fixture
def user() -> User:
    return UserFactory.build()


class TestMessageComposer:
    @pytest.mark.parametrize(
        'change_type',
        [
            change_type
            for change_type in ChangeType
            if change_type
            not in (
                ChangeType.topic_new,
                ChangeType.topic_status_change,
                ChangeType.topic_title_change,
                ChangeType.topic_comment_new,
                ChangeType.topic_inforg_comment_new,
                ChangeType.topic_first_post_change,
            )
        ],
    )
    def test_message_not_composed(self, change_type: ChangeType, user: User):
        # these change_types should not produce a message
        record = LineInChageFactory.build(
            topic_type_id=TopicType.search_reverse,
            change_type=change_type,
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert not message

    def test_topic_new_search(self, user: User):
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_new,
            start_time=datetime.now(),
            topic_type_id=TopicType.search_regular,
            managers='["manager1","manager2 +79001234567"]',  # TODO check phone link in separate test
            activities=['some activity'],
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert message
        assert 'Новый поиск' in message
        assert 'some activity' in message
        assert 'manager2  <a href="tel:+79001234567"> ☎️+79001234567</a>' in message

    def test_topic_new_event(self, user: User):
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_new,
            start_time=datetime.now(),
            topic_type_id=TopicType.event,
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert message
        assert 'Новое мероприятие' in message
        assert record.clickable_name in message

    def test_topic_status_change(self, user: User):
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_status_change,
            topic_type_id=TopicType.search_info_support,
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert 'изменение статуса по' in message
        assert record.clickable_name in message

    def test_topic_status_change_escapes_html(self, user: User):
        """Raw < > & in status text must not break Telegram HTML."""
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_status_change,
            topic_type_id=TopicType.search_info_support,
            status='Найден <b>&</b>',
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert '&lt;b&gt;&amp;&lt;/b&gt;' in message
        assert '<b>' not in message

    def test_topic_title_change(self, user: User):
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_title_change,
            topic_type_id=TopicType.event,
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert 'обновление заголовка мероприятия по' in message
        assert record.clickable_name in message

    def test_topic_title_change_escapes_html(self, user: User):
        """Raw < > & in forum title must not break Telegram HTML."""
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_title_change,
            topic_type_id=TopicType.event,
            title='Заголовок с <i>тегом</i> & символом',
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert '&lt;i&gt;тегом&lt;/i&gt;' in message
        assert '&amp;' in message
        assert '<i>тегом' not in message

    def test_topic_comment_new(self, user: User):
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_comment_new,
            topic_type_id=TopicType.search_regular,
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert 'Новые комментарии по поиску' in message
        assert record.clickable_name in message

    def test_topic_comment_new_escapes_html(self, user: User):
        """Raw < > & in forum comment text must not break Telegram HTML."""
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_comment_new,
            topic_type_id=TopicType.search_regular,
            comments=[
                Comment(
                    url='https://lizaalert.org/forum/viewtopic.php?&t=371693&start=31',
                    text='Сойка выехала домой <i>срочно & ждём "всех"',
                    author_nickname='SOIKA LA',
                    author_link='101319',
                ),
                Comment(
                    url='https://lizaalert.org/forum/viewtopic.php?&t=371693&start=32',
                    text='обычный текст',
                    author_nickname='Ник ><',
                    author_link='101320',
                ),
            ],
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert '&lt;i&gt;' in message
        assert '&amp;' in message
        assert '&quot;' in message
        assert '&gt;&lt;' in message
        assert '<i>срочно' not in message
        assert message.count('<i>') == message.count('</i>')
        assert message.count('<a ') == message.count('</a>')

    def test_topic_inforg_comment_new(self, user: User):
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_inforg_comment_new,
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert 'Сообщение от ' in message
        assert record.clickable_name in message

    def test_topic_inforg_comment_new_escapes_html(self, user: User):
        """Raw < > & in inforg comment text must not break Telegram HTML."""
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_inforg_comment_new,
            comments_inforg=[
                Comment(
                    url='https://lizaalert.org/forum/viewtopic.php?&t=371693&start=1',
                    text='Штаб свернут <b>резерв</b> & всё',
                    author_nickname='Инфорг поста',
                    author_link='101319',
                )
            ],
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert '&lt;b&gt;' in message
        assert '&amp;' in message
        assert '<b>резерв</b>' not in message
        assert message.count('<i>') == message.count('</i>')
        assert message.count('<a ') == message.count('</a>')

    def test_topic_first_post_change_1(self, user: User):
        new_value = r"{'del': ['Иван (Иванов)'], 'add': [], 'message': 'Удалено:\n<s>Иван (Иванов)\n</s>'}"
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_first_post_change,
            topic_type_id=TopicType.search_regular,
            new_value=new_value,
        )
        message = MessageComposer(record).compose_message_for_user(user)

        assert '🔀Изменения в первом посте по ' in message
        assert '\n\n➖Удалено:\n<s>Иван (Иванов)\n</s>' in message
        assert record.clickable_name in message

    def test_topic_first_post_change_2(self, user: User):
        new_value = r"{'del': [], 'add': ['Иван (Иванов)'], 'message': 'Добавлено:\n<s>Иван (Иванов)\n</s>'}"
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_first_post_change,
            topic_type_id=TopicType.search_regular,
            new_value=new_value,
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert '➕Добавлено:\nИван (Иванов)\n' in message

    def test_topic_first_post_change_3(self, user: User):
        new_value = 'Удалена информация:\
<s>Координаты пропажи: 53.534658, 49.324723\
</s>'

        record = LineInChageFactory.build(
            change_type=ChangeType.topic_first_post_change,
            topic_type_id=TopicType.search_regular,
            new_value=new_value,
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert 'Удалена информация:<s>Координаты пропажи: 53.534658, 49.324723</s>' in message

    def test_topic_first_post_change_4(self, user: User):
        new_value = '➖Удалено:\
<s>Ожидается выезд!\
</s>\
➕Добавлено:\
Штаб начнёт работать с 14:00 по адресу:\
Стоянка на заправке Газпромнефть, Маньковский разворот, Сергиево-Посадский г.о.\
56.376108, 38.108829\
'

        record = LineInChageFactory.build(
            change_type=ChangeType.topic_first_post_change,
            topic_type_id=TopicType.search_regular,
            new_value=new_value,
            search_latitude='56.1234',
            search_longitude='60.1234',
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert (
            'Удалено:<s>Ожидается выезд!</s>➕Добавлено:Штаб начнёт работать с 14:00 по адресу:Стоянка на заправке Газпромнефть, Маньковский разворот, Сергиево-Посадский г.о.56.376108, 38.108829'
            in message
        )

    def test_topic_first_post_change_5(self, user: User):
        new_value = r"{'del': [], 'add': ['Новые координаты 57.1234 61.12345']}"
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_first_post_change,
            topic_type_id=TopicType.search_regular,
            new_value=new_value,
            search_latitude='56.1234',
            search_longitude='60.1234',
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert (
            '➕Добавлено:\nНовые координаты <code>57.1234 61.12345</code>\n\n\nКоординаты сместились на ~126 км &#8601;&#xFE0E;'
            in message
        )

    def test_topic_first_post_change_escapes_html(self, user: User):
        """Raw < > & in first-post diff lines must not break Telegram HTML."""
        new_value = (
            r"{'del': ['Иван <b>(Иванов)</b> & сын'], 'add': ['Новые координаты 57.1234 61.12345 <i>срочно</i>']}"
        )
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_first_post_change,
            topic_type_id=TopicType.search_regular,
            new_value=new_value,
            search_latitude='56.1234',
            search_longitude='60.1234',
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert '&lt;b&gt;(Иванов)&lt;/b&gt; &amp; сын' in message
        assert '&lt;i&gt;срочно&lt;/i&gt;' in message
        assert '<b>' not in message
        assert '<i>срочно' not in message
        # coordinates are still wrapped in <code> for the location pin
        assert 'Новые координаты <code>57.1234 61.12345</code>' in message
        assert message.count('<s>') == message.count('</s>')
        assert message.count('<code>') == message.count('</code>')
        assert message.count('<i>') == message.count('</i>')

    def test_topic_first_post_change_legacy_message_escapes_html(self, user: User):
        """Legacy plain-string diffs: text is escaped, intentional <s> tags survive."""
        new_value = '➖Удалено: <s><b>Ожидается выезд</b> срочно!</s> ➕Добавлено: Штаб & штаб начнёт <i>работу</i>'
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_first_post_change,
            topic_type_id=TopicType.search_regular,
            new_value=new_value,
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert '<s>&lt;b&gt;Ожидается выезд&lt;/b&gt; срочно!</s>' in message
        assert '&amp;' in message
        assert '&lt;i&gt;работу&lt;/i&gt;' in message
        assert '<b>Ожидается' not in message
        assert message.count('<s>') == message.count('</s>')

    def test_topic_new_search_escapes_managers_html(self, user: User):
        """Raw < > & in manager names from forum must not break Telegram HTML."""
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_new,
            start_time=datetime.now(),
            topic_type_id=TopicType.search_regular,
            managers='["Инфорг <i>Иван</i> +79001234567"]',
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert 'Инфорг &lt;i&gt;Иван&lt;/i&gt;  <a href="tel:+79001234567">' in message
        assert '<i>Иван</i>' not in message
        assert message.count('<a ') == message.count('</a>')


def test_parse_change_log_saved_value_dict():
    saved_value = r"{'del': [], 'add': ['Новые координаты 57.1234 61.12345']}"

    res = ChangeLogSavedValue.from_db_saved_value(saved_value)
    assert res.additions
    assert not res.deletions
    assert res.message == ''


def test_parse_change_log_saved_value_str():
    saved_value = r'Внимание! Изменения.'

    res = ChangeLogSavedValue.from_db_saved_value(saved_value)
    assert not res.additions
    assert not res.deletions
    assert res.message == 'Внимание! Изменения.'


def test_parse_change_log_saved_value_dict_with_extra_fields():
    """should be parsed too"""
    saved_value = r"{'del': ['a'], 'add': [], 'foo': 1}"

    res = ChangeLogSavedValue.from_db_saved_value(saved_value)
    assert res.deletions
