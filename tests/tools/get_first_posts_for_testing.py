import csv
import json
import re
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path
from random import randint
from typing import Any
from unittest.mock import Mock, patch

import requests
from bs4 import BeautifulSoup, SoupStrainer
from dotenv import load_dotenv
from tqdm import tqdm

from _dependencies.commons import AppConfig
from title_recognize.main import recognize_title
from title_recognize.main_old import recognize_title as recognize_title_old


@lru_cache
def get_dotenv_config() -> AppConfig:
    assert load_dotenv('.env', override=True)
    return AppConfig()


def fake_publish_to_pubsub(topic, message):
    print(f'Publishing to Pub/Sub topic: {topic}, message: {message}')


def get_textx():
    folder_id = 276

    texts = []
    """
    just use table "searches.forum_search_title" to get examples
    """
    requests_session = requests.Session()
    for start_num in (0, 25, 50, 75, 100):
        url = f'https://lizaalert.org/forum/viewforum.php?f={folder_id}&start={start_num}'
        r = requests_session.get(url, timeout=10)  # for every folder - req'd daily at night forum update # noqa

        only_tag = SoupStrainer('div', {'class': 'forumbg'})
        soup = BeautifulSoup(r.content, features='lxml', parse_only=only_tag)
        del r  # trying to free up memory
        search_code_blocks = soup.find_all('dl', 'row-item')
        del soup  # trying to free up memory

        for i, data_block in enumerate(search_code_blocks):
            # First block is always not one we want
            if i == 0:
                continue

            # In rare cases there are aliases from other folders, which have static titles – and we're avoiding them
            if str(data_block).find('<dl class="row-item topic_moved">') > -1:
                continue

            # Current block which contains everything regarding certain search
            search_title_block = data_block.find('a', 'topictitle')
            # rare case: cleaning [size][b]...[/b][/size] tags
            search_title = re.sub(r'\[/?(b|size.{0,6}|color.{0,10})]', '', search_title_block.next_element)
            texts.append(search_title)
            search_id = int(re.search(r'(?<=&t=)\d{2,8}', search_title_block['href']).group())

            data = {'title': search_title}
            print(search_title)
            # title_reco_response = make_api_call('title_recognize', data)  # TODO can use local call in tests

    filename = 'build/titles_for_recognize.json'
    Path(filename).write_text(json.dumps(texts, indent=2, ensure_ascii=False))


def recognize_and_write():
    results = []

    filename = 'build/searches.csv'
    with open(filename, 'r') as file:
        reader = csv.reader(file)
        next(reader)

        lines = [x[0] for x in reader]  # [:2]

        with ProcessPoolExecutor(max_workers=8) as pool:
            pool_results = pool.map(reco_one_title, lines)
            for res in tqdm(pool_results, total=len(lines)):
                results.append(res)

    filename = 'build/new_recognition_results.json'
    Path(filename).write_text(json.dumps(results, indent=2, ensure_ascii=False))


def reco_one_title(line: str) -> dict:
    try:
        reco_result = recognize_title(line, 'full')
    except:
        reco_result = 'Error'
    return {'title': line, 'result': reco_result}


def reco_one_title_old_method(line: str) -> dict:
    try:
        reco_result = recognize_title_old(line, 'full')
    except:
        reco_result = 'Error'
    return {'title': line, 'result': reco_result}


if __name__ == '__main__':
    # get_textx()
    recognize_and_write()
