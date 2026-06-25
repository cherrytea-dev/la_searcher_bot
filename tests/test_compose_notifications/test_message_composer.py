from datetime import datetime

import pytest
from polyfactory.factories import DataclassFactory

from _dependencies.common.commons import ChangeLogSavedValue, ChangeType, TopicType
from compose_notifications._utils.commons import LineInChangeLog, User
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

    def test_topic_title_change(self, user: User):
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_title_change,
            topic_type_id=TopicType.event,
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert 'обновление заголовка мероприятия по' in message
        assert record.clickable_name in message

    def test_topic_comment_new(self, user: User):
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_comment_new,
            topic_type_id=TopicType.search_regular,
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert 'Новые комментарии по поиску' in message
        assert record.clickable_name in message

    def test_topic_inforg_comment_new(self, user: User):
        record = LineInChageFactory.build(
            change_type=ChangeType.topic_inforg_comment_new,
        )
        message = MessageComposer(record).compose_message_for_user(user)
        assert 'Сообщение от ' in message
        assert record.clickable_name in message

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
