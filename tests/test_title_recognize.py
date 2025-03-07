from unittest.mock import Mock, patch

import pytest
from flask import Flask

from title_recognize import main
from title_recognize._utils.person import recognize_one_person_group
from title_recognize._utils.title_commons import Block, PersonGroup, TitleRecognition
from title_recognize.main_old import recognize_title as recognize_title_old


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


class TestRecognizeTitle:
    def test_recognize_title_1(self):
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

    def test_recognize_title_2(self):
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

    def test_recognize_title_3(self):
        """just describe current behavior"""
        title = """
    Нужны ли «суперспособности», чтобы стать добровольцем поисково-спасательного отряда «ЛизаАлерт» и искать людей? 
    Обязательно ли иметь туристические навыки, компас и снаряжение? 
    А что, если вы мама в декрете и не можете ездить на поиски? 
    Как спасти человека, не выходя из дома? 

    Обо всём этом можно узнать на вводной встрече-знакомстве с «ЛизаАлерт». 
    Здесь омичам расскажут о 24 направлениях, которые сегодня есть в отряде. 
    О том, как можно стать кинологом, связистом в штабе или оператором, который запускает в небо беспилотник, и о многом другом.

    Регистрация на встречу по ссылке: https://lizaalertomsk.timepad.ru/event/.../

    Дата: 1 марта 2025 года
    Время: 19:30
    Место: г. Омск, Ленина, 24 к. 1, 5 этаж.

    Контакт по любым вопросам: Елена, тел. 89651234567.

    """

        res = main.recognize_title(title, 'status_only')
        assert res == {
            'topic_type': 'search',
            'status': 'Ищем',
            'persons': {
                'total_persons': -1,
                'total_name': 'Нужны',
                'total_display_name': 'Нужны и ко. 1–24 года',
                'age_min': 1,
                'age_max': 24,
                'person': [
                    {'name': 'Нужны', 'display_name': 'Нужны', 'number_of_persons': -1},
                    {'name': 'искать', 'display_name': 'Искать', 'number_of_persons': -1},
                    {'name': 'снаряжение', 'display_name': 'Снаряжение', 'number_of_persons': 1},
                    {'name': 'не', 'age': 24, 'display_name': 'Не 24 года', 'number_of_persons': 1},
                    {'name': 'о', 'age': 1, 'display_name': 'О 1 год', 'number_of_persons': 1},
                ],
            },
        }

    def test_recognize_title_4(self):
        """just describe current behavior"""
        title = """пропали женщина +2"""

        res = main.recognize_title(title, 'status_only')
        assert res == {
            'topic_type': 'search',
            'status': 'Ищем',
            'persons': {
                'age_max': None,
                'age_min': None,
                'total_persons': 3,
                'total_name': 'женщина',
                'total_display_name': 'Женщина + 2 чел.',
                'person': [
                    {'name': 'женщина', 'display_name': 'Человек', 'number_of_persons': 1},
                    {'name': '2 человека', 'display_name': '2 человека', 'number_of_persons': 2},
                ],
            },
        }

    def test_recognize_title_5(self):
        """doubling word with status"""
        title = """Найден найден мужчина"""

        res = main.recognize_title(title, 'status_only')
        assert res == {
            'topic_type': 'search',
            'status': 'Найден',
            'persons': {
                'age_max': None,
                'age_min': None,
                'total_persons': 1,
                'total_name': 'мужчина',
                'total_display_name': 'Мужчина',
                'person': [
                    {'name': 'мужчина', 'display_name': 'Человек', 'number_of_persons': 1},
                ],
            },
        }

    def test_recognize_title_location_before_person(self):
        """seems wrong, just describe current behavior"""
        title = 'Ярославская область. Пропал мужчина. ФИО - Иванов Иван Иванович.'
        res = main.recognize_title(title, 'status_only')
        assert res == {
            'topic_type': 'search',
            'status': 'Ищем',
            'persons': {
                'age_max': None,
                'age_min': None,
                'total_persons': -1,
                'total_name': 'Ярославская',
                'total_display_name': 'Ярославская и ко.',
                'person': [
                    {'name': 'Ярославская', 'display_name': 'Ярославская', 'number_of_persons': -1},
                    {'name': 'мужчина', 'display_name': 'Человек', 'number_of_persons': 1},
                ],
            },
        }

    def test_recognize_title_multiple_statuses_1(self):
        title = 'Пропал мужчина. Найдена женщина.'
        res = main.recognize_title(title, 'status_only')
        assert res == {
            'topic_type': 'search',
            'status': 'Ищем и Найден',
            'persons': {
                'age_max': None,
                'age_min': None,
                'total_persons': 2,
                'total_name': 'мужчина',
                'total_display_name': 'Мужчина + 1 чел.',
                'person': [
                    {'name': 'мужчина', 'display_name': 'Человек', 'number_of_persons': 1},
                    {'name': 'женщина', 'display_name': 'Человек', 'number_of_persons': 1},
                ],
            },
        }

    def test_recognize_title_multiple_statuses_2(self):
        title = 'Пропал мужчина. Текст посередине. Найдена женщина.'
        res = main.recognize_title(title, 'status_only')
        assert res == {
            'topic_type': 'search',
            'status': 'Ищем и Найден',
            'persons': {
                'age_max': None,
                'age_min': None,
                'total_persons': 2,
                'total_name': 'мужчина',
                'total_display_name': 'Мужчина + 1 чел.',
                'person': [
                    {'name': 'мужчина', 'display_name': 'Человек', 'number_of_persons': 1},
                    {'name': 'женщина', 'display_name': 'Человек', 'number_of_persons': 1},
                ],
            },
        }

    def test_recognize_title_multiple_statuses_3(self):
        title = 'Найдена мужчина. Найдена женщина.'
        res = main.recognize_title(title, 'status_only')
        assert res == {
            'topic_type': 'search',
            'status': 'Найден',
            'persons': {
                'age_max': None,
                'age_min': None,
                'total_persons': 2,
                'total_name': 'мужчина',
                'total_display_name': 'Мужчина + 1 чел.',
                'person': [
                    {'name': 'мужчина', 'display_name': 'Человек', 'number_of_persons': 1},
                    {'name': 'женщина', 'display_name': 'Человек', 'number_of_persons': 1},
                ],
            },
        }

    def test_recognize_title_multiple_statuses_4(self):
        """just describe current behavior"""
        title = 'Найдена мужчина. Найдена женщина. Пропал мужчина.'
        res = main.recognize_title(title, 'status_only')
        assert res == {
            'topic_type': 'search',
            'status': 'Найден',
            'persons': {
                'age_max': None,
                'age_min': None,
                'total_persons': 2,
                'total_name': 'мужчина',
                'total_display_name': 'Мужчина + 1 чел.',
                'person': [
                    {'name': 'мужчина', 'display_name': 'Человек', 'number_of_persons': 1},
                    {'name': 'женщина', 'display_name': 'Женщина', 'number_of_persons': 1},
                ],
            },
        }


class TestPersonRecognize:
    def test_1(self):
        block = Block(init='Иванов Иван Иванович. Возраст 37 лет', type='PER')
        res = recognize_one_person_group(block)
        assert res == PersonGroup(
            type_=None,
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
            type_=None,
            num_of_per=1,
            display_name='Ярославская',
            name='Ярославская',
            age=None,
            age_min=None,
            age_max=None,
            age_wording='',
        )


# @pytest.mark.skip(reason='temporarily disabled to speed up')
class TestPersonRecognizeAIGenerated:
    def test_recognize_one_person_group_case_0(self):
        block = Block(init='3 человека', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            type_=None,
            num_of_per=3,
            display_name='3 человека',
            name='3 человека',
            age=None,
            age_min=None,
            age_max=None,
            age_wording=None,
        )

    def test_recognize_one_person_group_case_1(self):
        block = Block(init='10 лет', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            type_=None,
            num_of_per=1,
            display_name='Ребёноклет',
            name='Ребёнок',
            age=10,
            age_min=None,
            age_max=None,
            age_wording=None,
        )

    def test_recognize_one_person_group_case_2(self):
        block = Block(init='2 женщины 25, 30 лет', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            type_=None,
            num_of_per=2,
            display_name='2 человека 25–30 лет',
            name='2 человека',
            age=None,
            age_min=25,
            age_max=30,
            age_wording=None,
        )

    def test_recognize_one_person_group_case_3(self):
        block = Block(init='дети 5, 7, 10 лет', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            type_=None,
            num_of_per=-1,
            display_name='Дети 10–7 лет',  # TODO wrong age, current behavior
            name='Дети',
            age=None,
            age_min=10,
            age_max=7,
            age_wording=None,
        )

    def test_recognize_one_person_group_case_4(self):
        block = Block(init='мужчина', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            type_=None,
            num_of_per=1,
            display_name='Человек',
            name='мужчина',
            age=None,
            age_min=None,
            age_max=None,
            age_wording=None,
        )

    def test_recognize_one_person_group_cyrillic(self):
        block = Block(init='Мужчина 45 лет', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            type_=None,
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
            type_=None,
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
            type_=None,
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
            type_=None,
            num_of_per=2,
            display_name='2 человека 30 лет',
            name='2 человека',
            age=None,
            age_min=30,
            age_max=30,
            age_wording=None,
        )

    def test_recognize_one_person_group_case_двое_трое(self):
        block = Block(init='двое мужчин 25, 30 лет', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            type_=None,
            num_of_per=2,
            display_name='2 человека 25–30 лет',
            name='2 человека',
            age=None,
            age_min=25,
            age_max=30,
            age_wording=None,
        )

        block = Block(init='трое детей 5, 7, 10 лет', type='PER')
        result = recognize_one_person_group(block)
        assert result == PersonGroup(
            type_=None,
            num_of_per=3,
            display_name='3 ребёнка 5–10 лет',
            name='3 ребёнка',
            age=None,
            age_min=5,
            age_max=10,
            age_wording=None,
        )


def test_location_1():
    title = (
        'Личность установлена. Называет себя Анна Предположительно 75-80 лет, найдена в Московском районе, г. Казань.'
    )
    res = main.recognize_title(title, '')
    assert res


class TestCompare:
    @pytest.mark.parametrize(
        'title',
        [
            'ПАРАЛЛЕЛИ НА ВДНХ - закрытие площадки',
            'Пропала бабушка',
            'Встреча с новичками в пос. Ульт-Ягун',
            'Учебный выход',
            'УЧЕБНАЯ! Живы Тестова Ирина 20 лет и Тестова Татьяна Юрьевна 30 лет, г. Самара, Красноглинский р-н',
            'ГОРОДСКОЙ УЧЕБНЫЙ ПОИСК',
            '10 лет',
            '14.09.2024 Рабочая встреча куратора с добровольцами в Череповце',
            'Сахалин',
            '3 апреля 2021 года в 16:00 встреча-знакомство г. Томск',
        ],
    )
    def test_diffs(self, title: str):
        res_old = recognize_title_old(title, '')
        res_new = main.recognize_title(title, '')
        assert res_old == res_new

    @pytest.mark.parametrize(
        'title',
        [
            'Личность установлена. Называет себя Анна Предположительно 75-80 лет, найдена в Московском районе, г. Казань.',
            'Личность установлена. Найдены, живы Неизвестные мужчина и женщина г. Тюмень,  Нижнетавдинский р-н, Тюменская область.',
            'Учебная Родные найдены Иванова (Петрова) Анна Викторовна, 24 года, Ленинский АО,  г. Тюмень.',
        ],
    )
    def test_rare_cases(self, title: str):
        res_old = recognize_title_old(title, '')
        res_new = main.recognize_title(title, '')
        assert res_old == res_new

    @pytest.mark.parametrize(
        'title',
        [
            'Живы трое подростков д. Гомыленки, Лежневский р-н, Ивановская обл.',
            'Живы 2 мужчины и женщина, д. Прислониха, Вичугский р-н, Ивановская обл.',
            'Живы Мужчина + двое подростков, д. Платково, Заволжский р-он',
            'Пропали Еремин Роман Владимирович, 41 год +1 мужчина, станица Базковская, Шолоховский р-н, Ростовская обл.',
            'Живы Ерошкина Александра Александровна +1 человек, п. Островское, Костромская обл.',
            'Живы трое мужчин, Костромской район, д. Пьяньково',
            'Живы 2 взрослых + 2 детей, д. Сенино, г. о. Чехов, МО',
            'Живы Муранов Абги-Рахман+1 человек , д. Панкратцево, Ивановский р-н, Ивановская обл.',
            'Живы двое мужчин и женщина, д. Зеленый городок, Ивановский р-н, Ивановская обл.',
            'Найдены. Живы. 2 женщины и ребенок 4',
            'Живы 2 женщины 80 и 48 лет, д. Лунинка, Рузский г. о., МО',
        ],
    )
    def test_persons(self, title: str):
        res_old = recognize_title_old(title, '')
        res_new = main.recognize_title(title, '')
        assert res_old == res_new

    def test_wrong_age(self):
        # TODO fix algorythm to recognize age correctly. Now it just describes current algorithm

        text = 'Жив Краснов Алексей Александрович, 43 года, Остановочный пункт 3412 км, Мошковский район, НСО'
        res_old = recognize_title_old(text, '')
        res_new = main.recognize_title(text, '')
        assert res_old == res_new
        assert res_new == {
            'topic_type': 'search',
            'status': 'НЖ',
            'persons': {
                'total_persons': 2,
                'total_name': 'Краснов',
                'total_display_name': 'Краснов + 1 чел. -1387–43 года',
                'age_min': -1387,
                'age_max': 43,
                'person': [
                    {'name': 'Краснов', 'age': 43, 'display_name': 'Краснов 43 года', 'number_of_persons': 1},
                    {
                        'name': 'Остановочный',
                        'age': -1387,
                        'display_name': 'Остановочный -1387 лет',
                        'number_of_persons': 1,
                    },
                ],
            },
            'locations': [{'address': 'км, Мошковский район, НСО'}],
        }
