import csv
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from tqdm import tqdm

from _dependencies.recognition_schema import RecognitionResult
from title_recognize.main import recognize_title
from title_recognize.main_old import recognize_title as recognize_title_old


def reco_one_title(line: str) -> dict:
    try:
        reco_result = recognize_title(line, 'full')
        RecognitionResult.model_validate(reco_result)
    except:
        print('reco_result not validated for title:' + line)
        reco_result = 'Error'
    return {'title': line, 'result': reco_result}


def reco_one_title_old_method(line: str) -> dict:
    try:
        reco_result = recognize_title_old(line, 'full')
    except:
        reco_result = 'Error'
    return {'title': line, 'result': reco_result}


def compare_recognition(line: str) -> dict | None:
    old_reco = reco_one_title_old_method(line)
    new_reco = reco_one_title(line)

    if new_reco == old_reco:
        return None

    print(f'different results for line {line}')
    return {'title': line, 'old_reco': old_reco, 'new_reco': new_reco}


def recognize_and_write():
    results = []

    filename = 'build/searches.csv'
    with open(filename, 'r') as file:
        reader = csv.reader(file)
        next(reader)

        lines = [x[0] for x in reader]  # [:2000]

        with ProcessPoolExecutor(max_workers=12) as pool:
            pool_results = pool.map(compare_recognition, lines)
            for res in tqdm(pool_results, total=len(lines)):
                if res:
                    results.append(res)

    filename = 'build/comparison.json'
    Path(filename).write_text(json.dumps(results, indent=2, ensure_ascii=False))
    if not results:
        print('Identical results')
    else:
        print(f'Different results saved to {filename}')


if __name__ == '__main__':
    recognize_and_write()
