from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

import identify_updates_of_topics._utils.external_api
import identify_updates_of_topics._utils.forum
from _dependencies.commons import sqlalchemy_get_pool
from identify_updates_of_topics import main
from identify_updates_of_topics._utils import parse
from tests.common import get_event_with_data
from title_recognize.main import recognize_title


@pytest.fixture
def db():
    return sqlalchemy_get_pool(10, 10)


@pytest.fixture(autouse=True)
def patch_google_cloud_storage():
    with patch('google.cloud.storage.Client'):
        yield


@pytest.fixture(autouse=True)
def common_patches():
    def fake_api_call(function: str, data: dict):
        reco_data = recognize_title(data['title'], None)
        return {'status': 'ok', 'recognition': reco_data}

    with (
        # patch.object(main, 'requests_session', requests.Session()),
        patch.object(main, 'make_api_call', fake_api_call),
        # patch('identify_updates_of_topics._utils.topics_commons.get_requests_session', requests.Session()),
        # patch.object(main, 'parse_search_profile', Mock(return_value='foo')),
        # patch('compose_notifications.main.call_self_if_need_compose_more'),  # avoid recursion in tests
    ):
        yield


@pytest.fixture()
def mock_http_get():
    with (
        patch.object(main.get_requests_session(), 'get') as mock_http,
    ):
        yield mock_http


def test_main():
    data = 'foo'
    with pytest.raises(ValueError):
        main.main(get_event_with_data(data), 'context')
    assert True


def test_get_cordinates(db):
    data = 'Москва, Ярославское шоссе 123'
    with patch('identify_updates_of_topics.main.rate_limit_for_api'):
        res = main.get_coordinates_by_address(db, data)
    assert res == (None, None)


def test_rate_limit_for_api(db):
    data = 'Москва, Ярославское шоссе 123'

    identify_updates_of_topics._utils.external_api.rate_limit_for_api(db, data)


def test_parse_one_folder(db, mock_http_get):
    mock_http_get.return_value.content = Path('tests/fixtures/forum_folder_276.html').read_bytes()

    forum_search_folder_id = 276
    summaries, details = main.parse_one_folder(db, forum_search_folder_id)
    assert summaries == [
        ['Жив Иванов Иван, 10 лет, ЗАО, г. Москва', 29],
        ['Пропал Петров Петр Петрович, 48 лет, ЗелАО, г. Москва - Тверская обл.', 116],
    ]
    assert len(details) == 2


def test_process_one_folder(db, mock_http_get):
    mock_http_get.return_value.content = Path('tests/fixtures/forum_folder_276.html').read_bytes()

    forum_search_folder_id = 276
    with patch.object(main, 'parse_search_profile', Mock(return_value='foo')):
        update_trigger, changed_ids = main.process_one_folder(db, forum_search_folder_id)
    assert update_trigger is True


def test_main_full_scenario(mock_http_get):
    mock_http_get.return_value.content = Path('tests/fixtures/forum_folder_276.html').read_bytes()

    forum_search_folder_id = 276
    data = [(forum_search_folder_id,)]
    with patch.object(main, 'parse_search_profile', Mock(return_value='foo')):
        main.main(get_event_with_data(str(data)), 'context')


def test_parse_one_comment(db, mock_http_get):
    mock_http_get.return_value.content = Path('tests/fixtures/forum_comment.html').read_bytes()

    there_are_inforg_comments = main.parse_one_comment(db, 1, 1)
    assert there_are_inforg_comments


def test_parse_search_profile_mock(mock_http_get):
    mock_http_get.return_value.content = Path('tests/fixtures/forum_topic.html').read_bytes()
    left_text = identify_updates_of_topics._utils.forum.parse_search_profile(83087)
    assert left_text == (
        'Сидорова (Иванова) Надежда Петровна, 30 лет, д. Никольская\n\t\t\t\t\t\t\t\t\t\tСлобода, '
        'Жуковский р-он, Брянская обл. \n\n\t\t\t\t\t\t\t\t6 октября 2024 года заблудилась в лесу.\n\n\n\n'
        'Приметы: рост 156 см, худощавого телосложения,\n\t\t\t\t\t\t\t\tволосы рыжие, глаза голубые.\n\n'
        'Была одета: темно-синяя куртка, синие спортивные\n\t\t\t\t\t\t\t\tштаны, разноцветые резиновые сапоги, платок.\n\n'
        'С собой: желтый рюкзак.\n\nКарты\n\nОриентировка на\n\t\t\t\t\t\t\t\t\t\tпечать\n\n'
        'Ориентировка на\n\t\t\t\t\t\t\t\t\t\tрепост\n\n\t\t\t\t\t\t\t\t--------------------------------------------------\n'
        'Найдена, жива.\n\nСБОР: \nКоординаты\n\t\t\t\t\t\t\t\t\t\tсбора:\n\n'
        'ШТАБ \nКоординаты\n\t\t\t\t\t\t\t\t\t\tштаба:\n\n\n'
        'СНМ: Лагутин Саша \nИнфорги: Светлана gLA_NAs 89001234567, 89001234567\n'
        'https://t.me/gLA_NAs\n\t\t\t\t\t\t\t\tОльга Вжик 89001234567, 89001234567 '
        'https://t.me/Ol_Massarova\n\nПредоставлять комментарии по\n\t\t\t\t\t\t\t\t\t\tпоиску для СМИ '
        'могут только координатор или инфорг поиска, а также представители\n\t\t\t\t\t\t\t\t\t\tпресс-службы «ЛизаАлерт».'
        ' \n\t\t\t\t\t\t\t\t\t\tЕсли же представитель СМИ хочет приехать на поиск, он может сообщить '
        'о своем\n\t\t\t\t\t\t\t\t\t\tжелании на горячую линию отряда\n\t\t\t\t\t\t\t\t\t\t8(800)700-54-52 '
        'или на почту smi@lizaalert.org'
    )


@pytest.mark.parametrize(
    'cleaned_text, activity_type',
    [
        ('штаб свернут', '9 - hq closed'),
        ('штаб работает', '1 - hq now'),
        ('автоном', '6 - autonom'),
        ('нет автоном, забрать оборудование', '3 - hardware logistics'),
        ('опрос', '6 - autonom'),
        ('забрать оборудование', '3 - hardware logistics'),
    ],
)
def test_parse_activity(cleaned_text: str, activity_type: str):
    activities = parse.profile_get_type_of_activity(cleaned_text)
    assert activities == [activity_type]


def test_parse_activity_wrong_case():
    # seems to be wrong
    activities = parse.profile_get_type_of_activity('сбор автоном')
    assert activities == ['1 - hq now', '6 - autonom']


def test_update_change_log_and_searches(db):
    res = main.update_change_log_and_searches(db, 1)
    pass


def test_visibility_check():
    response = Mock()
    response.content = b'foo'
    page_is_visible = identify_updates_of_topics._utils.forum.visibility_check(response, 1)
    assert page_is_visible


def test_parse_coordinates_of_search(db, mock_http_get):
    mock_http_get.return_value.content = Path('tests/fixtures/forum_topic.html').read_bytes()

    search_id = 1
    res = main.parse_coordinates_of_search(db, search_id)
    assert res == (53.510722, 33.637365, '3. deleted coord')


@pytest.mark.parametrize(
    'initial_title, expected_output',
    [
        ('John Doe, 30 лет, Москва', 'Москва, Россия'),
        ('John Doe, Москва', 'Москва, Россия'),
        ('30 лет, Москва', 'Москва, Россия'),
        ('Москва', 'Москва, Россия'),
        ('Москва, Россия', 'Москва, Россия, Россия'),
        ('г.о. Москва', 'городской округ Москва, Россия'),
        ('м.о. Москва', 'муниципальный округ Москва, Россия'),
        ('мкрн Москва', 'Москва, Россия'),
        ('мкр Москва', 'Москва, Россия'),
        ('р-н Москва АО', 'район Москва , Россия'),
        ('р-на Москва', 'район Москва, Россия'),
        ('обл. Москва', 'область Москва, Россия'),
        ('НСО Москва', 'Новосибирская область Москва, Россия'),
        ('МО Москва', 'МО Москва, Россия'),
        ('ЛО Москва', 'ЛО Москва, Россия'),
        ('г.Сочи Москва', 'Сочи Москва, Россия'),
        ('района Москва', 'района Москва, Россия'),
        ('области Москва', 'области Москва, Россия'),
        ('г. Москва', 'Москва, Россия'),
        ('г.москва', 'москва, Россия'),
        (
            'г. Сольцы, Новгородская обл. – г. Санкт-Петербург',
            'Сольцы, Новгородская область – г. Санкт-Петербург, Россия',
        ),
        ('Орехово-Зуевский район', 'Орехово-Зуевский городской округ, Россия'),
        ('СНТ Нефтяник', 'СНТ Нефтянник, Россия'),
        ('Коченевский', 'Коченёвский, Россия'),
        ('Самара - с. Красный Яр', 'Самара - с. Красный Яр, Россия'),
        ('Букреево-Плессо', 'Букреево Плёсо, Россия'),
        ('Москва Москва: Юго-Западный АО, ', 'Москва Москва: Юго-Западный АО, , Россия'),
        (
            'Луховицы - д.Алтухово, Зарайский городской округ,',
            'Луховицы - д.Алтухово, Зарайский городской округ,, Россия',
        ),
        ('Сагкт-Петербург', 'Санкт-Петербург, Россия'),
        ('Краснозерский', 'Краснозёрский, Россия'),
        ('Толмачевское', 'Толмачёвское, Россия'),
        ('Кочевский', 'Кочёвский, Россия'),
        ('Чесцы', 'Часцы, Россия'),
        ('John Doe, Чесцы', 'Часцы, Россия'),
        ('John Doe, 30, Чесцы', 'Часцы, Россия'),
        ('John Doe, Чесцы, 30 лет', ''),
        ('John Doe, Чесцы, 30 лет, Москва', 'Москва, Россия'),
    ],
)
def test_parse_address_from_title(initial_title, expected_output):
    fact_out = parse.parse_address_from_title(initial_title)

    if fact_out != expected_output:
        raise AssertionError(f'input: {initial_title},\nactual output is: {fact_out},\nexpected: {expected_output}')


class TestProfileGetManagers:
    def test_profile_get_managers_1(self):
        # Test case 1: Normal case
        text_of_managers = '--------\nКоординатор-консультант John Doe\nКоординатор Jane Smith\nИнфорг Bob Johnson\nСтаршая на месте Alice Brown\nСтарший на месте Charlie Davis\nДИ Emily Wilson\nСНМ Michael Taylor'
        expected_output = [
            'Координатор-консультант John Doe',
            'Координатор Jane Smith',
            'Инфорг Bob Johnson',
            'СНМ Michael Taylor',
        ]
        assert parse.profile_get_managers(text_of_managers) == expected_output

    def test_profile_get_managers_2(self):
        # Test case 2: No managers mentioned
        text_of_managers = '--------\nNo managers mentioned'
        expected_output = []
        assert parse.profile_get_managers(text_of_managers) == expected_output

    def test_profile_get_managers_3(self):
        # Test case 3: Managers mentioned but not in the list_of_roles
        text_of_managers = '--------\nManager John Doe\nManager Jane Smith\nManager Bob Johnson'
        expected_output = []
        assert parse.profile_get_managers(text_of_managers) == expected_output

    def test_profile_get_managers_4(self):
        # Test case 5: Managers mentioned and in the list_of_roles with telegram links
        text_of_managers = '--------\nКоординатор-консультант John Doe https://telegram.im/@johndoe\nКоординатор Jane Smith https://t.me/janesmith\nИнфорг Bob Johnson https://telegram.im/@bobjohnson\nСтаршая на месте Alice Brown https://t.me/alicebrown\nСтарший на месте Charlie Davis https://telegram.im/@charliedavis\nДИ Emily Wilson https://t.me/emilywilson\nСНМ Michael Taylor https://telegram.im/@michaeltaylor'
        expected_output = [
            'Координатор-консультант John Doe https://telegram.im/@johndoe',
            'Координатор Jane Smith https://t.me/janesmith',
            'Инфорг Bob Johnson https://telegram.im/@bobjohnson',
            'СНМ Michael Taylor https://telegram.im/@michaeltaylor',
        ]
        assert parse.profile_get_managers(text_of_managers) == expected_output
