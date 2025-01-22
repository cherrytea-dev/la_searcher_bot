import pytest
from flask import Flask

import _dependencies.misc
from api_get_active_searches import main


def test_main():
    app = Flask(__name__)

    with app.test_request_context('/', json={'app_id': 1}) as app:
        main.main(app.request)
    assert True


def test_get_list_of_active_searches_from_db():
    data = {'depth_days': 20, 'forum_folder_id_list': [1, 2, 3]}

    res = main.get_list_of_active_searches_from_db(data)
    assert not res
