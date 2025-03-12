from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import identify_updates_of_topics._utils.external_api
import identify_updates_of_topics._utils.folder_updater
import identify_updates_of_topics._utils.forum
from identify_updates_of_topics import main
from identify_updates_of_topics._utils import folder_updater, forum, parse
from tests.common import get_event_with_data
from title_recognize.main import recognize_title


def test_main():
    data = 'foo'
    with pytest.raises(ValueError):
        main.main(get_event_with_data(data), 'context')
    assert True


def test_rate_limit_for_api(db):
    data = 'Москва, Ярославское шоссе 123'

    identify_updates_of_topics._utils.external_api.rate_limit_for_api(db, data)


def test_main_full_scenario(mock_http_get):
    mock_http_get.return_value.content = Path('tests/fixtures/forum_folder_276.html').read_bytes()

    forum_search_folder_id = 276
    data = [(forum_search_folder_id,)]
    with patch.object(forum.ForumClient, 'parse_search_profile', Mock(return_value='foo')):
        main.main(get_event_with_data(str(data)), 'context')


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


def test_parse_coordinates_of_search(db, mock_http_get):
    mock_http_get.return_value.content = Path('tests/fixtures/forum_topic.html').read_bytes()

    search_id = 1
    res = folder_updater.FolderUpdater(db, search_id).parse_coordinates_of_search(search_id)
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
