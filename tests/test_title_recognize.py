from unittest.mock import Mock, patch

import pytest
from flask import Flask

from title_recognize import main


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
