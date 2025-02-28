from contextlib import suppress
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


def compare_recognition(element: dict) -> dict | None:
    old_reco = reco_one_title_old_method(element['title'])
    if old_reco['result'] == element['result']:
        return None
    element['new_result'] = element['result']
    del element['result']
    element['old_result'] = old_reco
    # element['old_result'] = old_reco['result']  # should be so
    
    return element


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


def recognize_old_and_compare():
    diffs = []

    filename = 'build/new_recognition_results.json'
    filename_diffs = 'build/recognition_results_diffs.json'
    new_reco_results = json.loads(Path(filename).read_text())  # [:2]

    with ProcessPoolExecutor(max_workers=8) as pool:
        pool_results = pool.map(compare_recognition, new_reco_results)
        for res in tqdm(pool_results, total=len(new_reco_results)):
            if res:
                diffs.append(res)

    Path(filename_diffs).write_text(json.dumps(diffs, indent=2, ensure_ascii=False))


def compare_with_age():
    
    final_diffs = []

    filename_diffs = 'build/recognition_results_diffs.json'
    filename_diffs_final = 'build/recognition_results_diffs_final.json'
    diffs = json.loads(Path(filename_diffs).read_text())  # [:2]
    for diff in diffs:
        old_res = diff['old_result']["result"]
        new_res = diff['result']
        with suppress(Exception):
            if not old_res['persons']['age_min']:
                del old_res['persons']['age_min']
        with suppress(Exception):
            if not old_res['persons']['age_max']:
                del old_res['persons']['age_max']

        if new_res != old_res:
            final_diffs.append(diff)

    Path(filename_diffs_final).write_text(json.dumps(final_diffs, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    # get_textx()
    # recognize_and_write()
    # recognize_old_and_compare()
    compare_with_age()


"""
  {
    "title": "Жив Краснов Алексей Александрович, 43 года, Остановочный пункт 3412 км, Мошковский район, НСО",
    "result": "Error",
    "old_result": {
      "title": "Жив Краснов Алексей Александрович, 43 года, Остановочный пункт 3412 км, Мошковский район, НСО",
      "result": {
        "topic_type": "search",
        "status": "НЖ",
        "persons": {
          "total_persons": 2,
          "total_name": "Краснов",
          "total_display_name": "Краснов + 1 чел. -1387–43 года",
          "age_min": -1387,
          "age_max": 43,
          "person": [
            {
              "name": "Краснов",
              "age": 43,
              "display_name": "Краснов 43 года",
              "number_of_persons": 1
            },
            {
              "name": "Остановочный",
              "age": -1387,
              "display_name": "Остановочный -1387 лет",
              "number_of_persons": 1
            }
          ]
        },
        "locations": [
          {
            "address": "км, Мошковский район, НСО"
          }
        ]
      }
    }
  },
"""