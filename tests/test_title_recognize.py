from unittest.mock import Mock, patch

import pytest
from flask import Flask

from title_recognize import main
from title_recognize._utils.person import recognize_one_person_group
from title_recognize._utils.title_commons import Block, PersonGroup, TitleRecognition


@pytest.fixture
def app() -> Flask:
    return Flask(__name__)


def test_main_positive(app: Flask):
    with app.test_request_context('/', json={'title': 'Пропал человек'}) as app_request:
        res = main.main(app_request.request)

    assert 'fail' not in res


def test_main_wrong_request(app: Flask):
    with app.test_request_context('/', json={'foo': 'bar'}) as app_request:
        res = main.main(app_request.request)

    assert 'fail' in res


def test_main_unrecognized(app: Flask):
    with (
        app.test_request_context('/', json={'title': 'Пропал человек'}) as app_request,
        patch.object(main, 'recognize_title', Mock(return_value=None)),
    ):
        res = main.main(app_request.request)

    assert 'fail' in res


def test_recognize_title():
    title = 'Пропал мужчина. ФИО - Иванов Иван Иванович. Возраст 37 лет. Ярославская область.'
    res = main.recognize_title(title, 'status_only')
    assert res == {
        'topic_type': 'search',
        'status': 'Ищем',
        'persons': {
            'total_persons': 1,
            'total_name': 'мужчина',
            'total_display_name': 'Мужчина 37 лет',
            'age_min': 37,
            'age_max': 37,
            'person': [
                {
                    'name': 'мужчина',
                    'age': 37,
                    'display_name': 'Мужчина 37 лет',
                    'number_of_persons': 1,
                }
            ],
        },
    }


def test_recognize_title_2():
    title = """
Иванова Анна Тестовна 25 лет, д. Новая, Талицкий г.о., Свердловская обл. 
01 января 2023 года вышла из дома и не вернулась. 
Нуждается в медицинской помощи.Может находиться в вашем городе.
Приметы: Рост: 170 см. Телосложение: плотного 
Цвет глаз: карие Волосы: тёмно-русые  
Была одета: оранжевая куртка, зелёная футболка, чёрные колготки, синие галоши.  
С собой: 
Нуждается в медицинской помощи 
Может находиться в вашем городе  
Ориентировка на печать  
Ориентировка на репост  
Тема в вк ----------
----------------------------------------  
Инфорг: 
Тест (тест) 89530000000 Написать инфоргу в 
WhatsApp Написать инфоргу в ТГ

"""

    res = main.recognize_title(title, 'status_only')
    assert res == {
        'topic_type': 'search',
        'status': 'Ищем',
        'persons': {
            'total_persons': 1,
            'total_name': 'Иванова',
            'total_display_name': 'Иванова 25 лет',
            'age_min': 25,
            'age_max': 25,
            'person': [{'name': 'Иванова', 'age': 25, 'display_name': 'Иванова 25 лет', 'number_of_persons': 1}],
        },
    }


class TestPersonRecognize:
    def test_1(self):
        block = Block(init='Иванов Иван Иванович. Возраст 37 лет', type='PER')
        res = recognize_one_person_group(block)
        assert res == PersonGroup(
            block_num='E',
            type=None,
            num_of_per=1,
            display_name='Иванов 37 лет',
            name='Иванов',
            age=37,
            age_min=None,
            age_max=None,
            age_wording=' 37 лет',
        )

    def test_2(self):
        block = Block(init='Ярославская область.', type='LOC')
        res = recognize_one_person_group(block)
        assert res == PersonGroup(
            block_num='O',
            type=None,
            num_of_per=1,
            display_name='Ярославская',
            name='Ярославская',
            age=None,
            age_min=None,
            age_max=None,
            age_wording='',
        )


class TestPersonRecognizeAIGenerated:
    def test_recognize_one_person_group_case_0(self):
        block = Block(init='3 человека', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            block_num=None,
            type=None,
            num_of_per=3,
            display_name='3 человека',
            name='3 человека',
            age=None,
            age_min=None,
            age_max=None,
            age_wording='',
        )

    def test_recognize_one_person_group_case_1(self):
        block = Block(init='10 лет', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            block_num='R',
            type=None,
            num_of_per=1,
            display_name='Ребёнок 10 лет',
            name='Ребёнок',
            age=10,
            age_min=None,
            age_max=None,
            age_wording='',
        )

    def test_recognize_one_person_group_case_2(self):
        block = Block(init='2 женщины 25, 30 лет', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            block_num='R',
            type=None,
            num_of_per=2,
            display_name='2 человека 25–30 лет',
            name='2 человека',
            age=None,
            age_min=25,
            age_max=30,
            age_wording='',
        )

    def test_recognize_one_person_group_case_3(self):
        block = Block(init='дети 5, 7, 10 лет', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            block_num='R',
            type=None,
            num_of_per=-1,
            display_name='Дети 5–10 лет',
            name='Дети',
            age=None,
            age_min=5,
            age_max=10,
            age_wording='',
        )

    def test_recognize_one_person_group_case_4(self):
        block = Block(init='мужчина', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            block_num='R',
            type=None,
            num_of_per=1,
            display_name='Человек',
            name='мужчина',
            age=None,
            age_min=None,
            age_max=None,
            age_wording='',
        )

    def test_recognize_one_person_group_cyrillic(self):
        block = Block(init='Мужчина 45 лет', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            block_num='R',
            type=None,
            num_of_per=1,
            display_name='Мужчина 45 лет',
            name='Мужчина',
            age=45,
            age_min=None,
            age_max=None,
            age_wording=' 45 лет',
        )

    def test_recognize_one_person_group_large_age(self):
        block = Block(init='Человек 150 лет', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            block_num='R',
            type=None,
            num_of_per=1,
            display_name='Человек 150 лет',
            name='Человек',
            age=150,
            age_min=None,
            age_max=None,
            age_wording=' 150 лет',
        )

    def test_recognize_one_person_group_with_special_characters(self):
        block = Block(init='  Иванов   Иван  Иванович!!!   Возраст  37  лет  ', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            block_num='E',
            type=None,
            num_of_per=1,
            display_name='Иванов 37 лет',
            name='Иванов',
            age=37,
            age_min=None,
            age_max=None,
            age_wording=' 37 лет',
        )

    def test_recognize_one_person_group_same_age(self):
        block = Block(init='2 человека 30 лет', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            block_num='R',
            type=None,
            num_of_per=2,
            display_name='2 человека 30 лет',
            name='2 человека',
            age=None,
            age_min=30,
            age_max=30,
            age_wording='',
        )

    def test_recognize_one_person_group_case_двое_трое(self):
        block = Block(init='двое мужчин 25, 30 лет', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            block_num='R',
            type=None,
            num_of_per=2,
            display_name='2 человека 25–30 лет',
            name='2 человека',
            age=None,
            age_min=25,
            age_max=30,
            age_wording='',
        )

        block = Block(init='трое детей 5, 7, 10 лет', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            block_num='R',
            type=None,
            num_of_per=3,
            display_name='3 ребёнка 5–10 лет',
            name='3 ребёнка',
            age=None,
            age_min=5,
            age_max=10,
            age_wording='',
        )
