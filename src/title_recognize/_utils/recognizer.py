import logging
import re
from datetime import datetime
from typing import Any, Dict, Union

from dateutil import relativedelta
from natasha import Doc, NewsEmbedding, NewsNERTagger, Segmenter
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dataclasses import dataclass, field
from typing import Any
from re import Match
from typing import Tuple
from title_recognize._utils.recognizer import PersonGroup
from title_recognize._utils.recognizer import Block
from typing import List
from typing import Optional
from title_recognize._utils.recognizer import TitleRecognition


@dataclass
class Block:
    block_num: Any = None
    init: str = None
    reco: Any = None
    type: Any = None
    done: bool = False


@dataclass
class PersonGroup:
    block_num: Any = None
    type: Any = None  # TODO rename
    num_of_per: Any = None
    display_name: Any = None
    name: Any = None
    age: Any = None
    age_min: Any = None
    age_max: Any = None
    age_wording: Any = None


@dataclass
class TitleRecognition:
    init: Any = None
    pretty: Any = None
    blocks: list[Block] = field(default_factory=list)
    groups: list = field(default_factory=list)
    reco: Any = None
    st: Any = None
    tr: Any = None
    act: Any = None
    avia: Any = None
    per_num: Any = None


def age_wording(age: int) -> str:
    # TODO DOUBLE age_writer
    """Return age-describing phrase in Russian for age as integer"""

    a = age // 100
    b = (age - a * 100) // 10
    c = age - a * 100 - b * 10

    if c == 1 and b != 1:
        wording = 'год'
    elif (c in {2, 3, 4}) and b != 1:
        wording = 'года'
    else:
        wording = 'лет'

    return wording


def match_type_to_pattern(pattern_type: str) -> List[List[str]]:
    """Return a list of regex patterns (with additional parameters) for a specific type"""

    if not pattern_type:
        return None

    patterns = []
    index_type = 'per'

    if pattern_type == 'MISTYPE':
        # language=regexp
        patterns = [
            [r'^\W{0,3}Re:\W{0,3}', ''],  # removes replied mark
            [r'(?i)^\W{0,3}внимание\W{1,3}', ''],  # removes unnecessary info
            [r'^(\s{1,3}|])', ''],  # removes all unnecessary symbols in the beginning of the string
            [r'[\s\[/\\(]{1,3}$', ''],  # removes all unnecessary symbols in the end of the string
            # noinspection PyUnresolvedReferences
            [r'([.,;:!?\s])\1+', r'\1'],  # noqa
            # removes all duplicates in blank spaces or punctuation marks
            [r'(?<!\d)\B(?=\d)', ' '],  # when and con  sequent number age typed w/o a space, example: word49
            [r'(\[/?b]|\[?size\W?=\W?140]|\[/size]|\[/?color=.{0,8}])', ''],  # rare case of php formatting
            [
                r'(?i)((?<=\d\Wлет\W)|(?<=\d\Wлет\W\W)|(?<=\d\Wгод\W)|(?<=\d\Wгод\W\W)|'
                r'(?<=\d\Wгода\W)|(?<=\d\Wгода\W\W))\d{1,2}(?=,)',
                '',
            ],  # case when '80 лет 80,' – last num is wrong
            [r'(?i)без вести\s', ' '],  # rare case of 'пропал без вести'
            [r'(?i)^ропал', 'Пропал'],  # specific case for one search
            [r'(?i)пропалпропал', 'Пропал'],  # specific case for one search
            [r'(?i)^форум\W{1,3}', ''],  # specific case for one search
            [r'(?i)^э\W{1,3}', ''],  # specific case for one search
            [r'попал ', 'пропал '],  # specific case for one search
            [r'(?i)найлен(?=\W)', 'найден'],  # specific case for one search
            [r'(?i)^нж(?=\W)', 'найден жив'],  # specific case for one search
            [r'ле,т', 'лет,'],  # specific case for one search
            [r'(?i)^Стор', 'Стоп'],  # specific case for one search
            [r'ПроЖив', 'Жив'],  # specific case for one search
            [r'\(193,', ','],  # specific case for one search
            [r'\[Учения]', 'Учебный'],  # specific case for one search
            [r'(?i)\Bпропал[аи](?=\W)', ''],  # specific case for one search
            [r'(?i)проаерка(?=\W)', 'проверка'],  # specific case for one search
            [r'(?i)поиск завешен', 'поиск завершен'],  # specific case for one search
            [r'(?i)поиск заверешен', 'поиск завершен'],  # specific case for one search
            [r':bd', ''],  # specific case for one search
            [r'Стоп(?=[А-Я])', 'Стоп '],  # specific case for one search
            [r'Жив(?=[А-Я])', 'Жив '],  # specific case for one search
            [r'Жмва ', 'Жива '],  # specific case for one search
            [r'Жтва ', 'Жива '],  # specific case for one search
            [r'Жиаа ', 'Жива '],  # specific case for one search
            [r'Проопал', 'Пропал'],  # specific case for one search
            [r'Жиаа(?=[А-Я])', 'Жива '],  # specific case for one search
            [r'Жива?(?=[А-Я])', 'Жива '],  # specific case for one search
            [r'(?i)погию\s', 'погиб '],  # specific case for one search
            [r'р.п ', 'р.п. '],  # specific case for one search
            [r'(?<=\d{4}\W)г\.?р?', 'г.р.'],  # rare case
            [r'(?<!\d)\d{3}\Wг\.р\.', ''],  # specific case for one search
            [r'(?<=\d{2}\Wгод\W{2}\d{4})\W{1,3}(?!г)', ' г.р. '],  # specific case for one search
            [r'((?<=год)|(?<=года)|(?<=лет))\W{1,2}\(\d{1,2}\W{1,2}(года?|лет)?\W?на м\.п\.\)', ' '],  # rare case
            [r'(?i)провекра\s', 'проверка '],  # specific case for one search
        ]

    elif pattern_type == 'AVIA':
        # language=regexp
        patterns = [[r'(?i)работает авиация\W', 'Авиация']]

    elif pattern_type == 'TR':
        # language=regexp
        patterns = [[r'(?i)\(?учебн(ый|ая)(\W{1,3}((поиск|выход)(\W{1,4}|$))?|$)', 'Учебный', 'search']]

    elif pattern_type == 'ST':
        # language=regexp
        patterns = [
            [
                r'(?i)(личност[ьи] (родных\W{1,3})?установлен[аы]\W{1,3}((родные\W{1,3})?найден[аы]?\W{1,3})?)',
                'Завершен',
                'search reverse',
            ],
            [r'(?i)(найдена?\W{1,3})(?=(неизвестн(ая|ый)|.*называет себя\W|.*на вид\W))', 'Ищем', 'search reverse'],
            [r'(?i)до сих пор не найден[аы]?\W{1,3}', 'Ищем', 'search'],
            [r'(?i)пропал[аи]?\W{1,3}стоп\W', 'СТОП', 'search'],
            [
                r'(?i)(^\W{0,2}|(?<=\W)|(найден[аы]?\W{1,3})?)'
                r'жив[аы]?'
                r'(\W{1,3}(проверка(\W{1,3}информации)?|пропал[аи]?))?'
                r'(\W{1,3}|$)',
                'НЖ',
                'search',
            ],
            [
                r'(?i)(^\W{0,2}|(?<=\W)|(найден[аы]?\W{1,3})?)'
                r'погиб(л[иа])?'
                r'(\W{1,3}(проверка(\W{1,3}информации)?|пропал[аи]?))?'
                r'(\W{1,3}|$)',
                'НП',
                'search',
            ],
            [
                r'(?i)(?<!родственники\W)(?<!родные\W)(пропал[аы]\W{1,3}?)?найден[аы]?\W{1,3}(?!неизвестн)',
                'Найден',
                'search',
            ],
            [
                r'(?i)[сc][тt][оo]п\W{1,3}(?!проверка)(.{0,15}эвакуация\W)\W{0,2}(пропал[аи]?\W{1,3})?',
                'СТОП ЭВАКУАЦИЯ',
                'search',
            ],
            [r'(?i)[сc][тt][оo]п\W(.{0,15}проверка( информации)?\W)\W{0,2}(пропал[аи]?\W{1,3})?', 'СТОП', 'search'],
            [r'(?i)[сc][тt][оo]п\W{1,3}(пропал[аи]?\W{1,3})?', 'СТОП', 'search'],
            [r'(?i)проверка( информации)?\W{1,3}(пропал[аи]?\W{1,3})?', 'СТОП', 'search'],
            [r'(?i).{0,15}эвакуация\W{1,3}', 'ЭВАКУАЦИЯ', 'search'],
            [r'(?i)поиск ((при)?остановлен|заверш[её]н|прекращ[её]н)\W{1,3}', 'Завершен', 'search'],
            [r'(?i)\W{0,2}(поиск\W{1,3})?возобновл\w{1,5}\W{1,3}', 'Возобновлен', 'search'],
            [r'(?i)((выезд\W{0,3})?пропал[аи]?|похищен[аы]?)\W{1,3}', 'Ищем', 'search'],
            [
                r'(?i)(поиски?|помогите найти|ищем)\W(родных|родственник(ов|а)|знакомых)\W{1,3}',
                'Ищем',
                'search reverse',
            ],
            [r'(?i)помогите (установить личность|опознать человека)\W{1,3}', 'Ищем', 'search reverse'],
            [r'(?i)(родные|родственники)\Wнайдены\W{1,3}', 'Завершен', 'search reverse'],
            [r'(?i)личность установлена\W{1,3}', 'Завершен', 'search reverse'],
            [r'(?i)потеряшки в больницах\W{1,3}', 'Ищем', 'search reverse'],
            [r'(?i)(^|\W)информации\W', 'СТОП', 'search'],
            [r'(?i)(?<!поиск\W)((при)?остановлен|заверш[её]н|прекращ[её]н)\W{1,3}', 'Завершен', 'search'],
        ]

    elif pattern_type == 'ACT':
        # language=regexp
        patterns = [
            [r'(?i).*учебные\sсборы.*\n?', 'event', 'event'],
            [r'(?i).*учения.*\n?', 'event', 'event'],
            [
                r'(?i).*((полевое|практическ(ое|ие)) обучение|полевая тр?енировка|'
                r'полевое( обучающее)? заняти[ея]|практическ(ое|ие)\W{1,3}заняти[ея]).*\n?',
                'event',
                'event',
            ],
            [r'(?i).*(обучалк[иа]).*\n?', 'event', 'event'],
            [r'(?i).*обучение по.*\n?', 'event', 'event'],
            [r'(?i).*курс по.*\n?', 'event', 'event'],
            [
                r'(?i).*(новичк(и|ами?|овая|овый)|новеньки[ем]|знакомство с отрядом|для новичков)(\W.*|$)\n?',
                'event',
                'event',
            ],
            [r'(?i).*(вводная лекция)\W.*\n?', 'event', 'event'],
            [r'(?i).*(лекци\w\sо)\W.*\n?', 'event', 'event'],
            [
                r'(?i).*\W?(обучение|онлайн-лекция|лекция|школа волонт[её]ров|обучающее мероприятие|(?<!парт)съезд|'
                r'семинар|собрание).*\n?',
                'event',
                'event',
            ],
            [r'(?i).*ID-\W?\d{1,7}.*\n?', 'info', 'info'],
            [r'(?i)ночной патруль.*\n?', 'search patrol', 'search patrol'],
        ]

    elif pattern_type == 'LOC_BLOCK':
        index_type = 'loc'
        # language=regexp
        patterns = [
            r'(\W[\w-]{3,20}\W)?с\.п\..*',
            r'(?i)\W(дер\.|деревня|село|пос\.|урочище|ур\.|станица|хутор|пгт|аул|городок|город\W|пос\W|улус\W|'
            r'садовое тов|[сc][нh][тt]|ст\W|р\.п\.|жск|тсн|тлпх|днт|днп|о.п.|б/о|ж/м|ж/р|база\W|местечко|кп[.\s]|'
            r'го\W|рп|коллективный сад|г-к|г\.о\W|ми?крн?|м-н|улица|квартал|'
            r'([\w-]{3,20}\W)?(р-о?н|район|гп|ао|обл\.?|г\.о|мост|берег|пристань|шоссе|автодорога|окр\W)|'
            r'ж[/.]д|жд\W|пл\.|тер\.|массив|'
            r'москва|([свзюцн]|юв|св|сз|юз|зел)ао\W|мо\W|одинцово|санкт-петербург|краснодар|адлер|сочи|'
            r'самара|лыткарино|ессентуки|златоуст|абхазия|старая|калуга|ростов-на-дону|кропоткин|'
            r'А-108|\d{1,3}(-?ы?й)?\s?км\W|'
            r'гора|лес\W|в лесу|лесной массив|парк|нац(иональный)?\W{0,2}парк|охотоугодья).*',
            r'\W[гдспхоу]\.($|(?!(р\.|р,|,|р\)|р\W\)|р\.\)|\Wр\.?\)?)).*)',
            r'\W(?<!\Wг\.)(?<!\dг\.)р\.\W.*',
            r'\sг\s.*',
        ]

    elif pattern_type == 'LOC_BY_INDIVIDUAL':
        # language=regexp
        patterns = [r'(?<![\-–—])*\W{1,3}[\-–—]\W{1,2}(?![\-–—])*']

    elif pattern_type == 'PER_AGE_W_WORDS':
        # language=regexp
        patterns = [
            r'(?i)(.*\W|^)\d?\d?\d([.,]\d)?\W{0,2}'
            r'(?:лет|года?|л\.|мес(яц(?:а|ев)?)?|г\.,)'
            r'(.{0,3}\W\d{4}\W?(года?(\Wр.{0,8}\W)\W?|г\.?\W?р?\.?\)?\W\W?))?'
            r'(\W{0,2}\d{1,2}\W)?'
            r'(\W{0,5}\+\W{0,2}(женщина|девушка|\d))?\W{0,5}',
            r'(?i).*\W\d{4}\W?'
            r'(?:года?(\Wр.{0,8}\W)\W?|г\.?р?\.?)'
            r'(\W{0,3}\+\W{0,2}(женщина|девушка|\d))?'
            r'(.{0,3}\W\d?\d?\d([.,]\d)?\W?'
            r'(?:лет|года?|л\.|мес(яц(?:а|ев)?)?))?'
            r'\W{1,5}',
        ]

    elif pattern_type == 'PER_AGE_WO_WORDS':
        # language=regexp
        patterns = [r'(?i)\d{1,3}(\W{1,4}(?!\d)|$)']

    elif pattern_type == 'PER_WITH_PLUS_SIGN':
        # language=regexp
        patterns = [
            r'(?i)\W{0,3}\+\W{0,2}((женщина|девушка|мама|\d(\W{0,3}человека?\W{1,3})?)|'
            r'(?=[^+]*$)[^+]{0,25}\d{0,3})[^+\w]{1,3}'
        ]

    elif pattern_type == 'PER_HUMAN_BEING':
        # language=regexp
        patterns = [
            r'(?i).*(женщин[аы]|мужчин[аы]|декушк[аи]|человека?|дочь|сын|жена|муж|отец|мать|папа|мама|'
            r'бабушк[аи]|дедушк[аи])(\W{1,3}|$)'
        ]

    elif pattern_type == 'PER_FIO':
        # language=regexp
        patterns = [r'.*\W{1,3}[А-Я]\.\W{0,2}[А-Я]\.\W*']

    elif pattern_type == 'PER_BY_LAST_NUM':
        # language=regexp
        patterns = [r'.*[^1]1?\d{1,2}(?![0-9])\W{1,5}']

    elif pattern_type == 'PER_BY_INDIVIDUAL':
        # language=regexp
        patterns = [
            r'\+\W{0,3}(?!\W{0,2}\d{1,2}\Wлет)',
            r'(?<!\d)(?<!\d\Wлет)\Wи\W{1,3}',  # "3 девочки 10 , 12 и 13 лет" should not split into 2 groups
            r'(?i)'
            r'\W\d?\d?\d([.,]\d)?\W{0,2}'
            r'(?:лет|года?|л\.|мес(яц(?:а|ев)?)?|г\.,)\W{0,2}'
            r'(.{0,3}\d{4}\W?(года?(\Wр.{0,8}\W)\W?|г\.?\W?р?\.?\W{1,4}))?'
            r'(?-i:[\Wи]{0,5})(?!.{0,5}\d{1,2}\Wлет)',
            # "2 мужчин 80 лет и 67 лет" should not split into 2 groups
            r'(?i).*(женщин[аы]|мужчин[аы]|декушк[аи]|человека?|дочь|сын|жена|муж|отец|мать|папа|мама|'
            r'бабушк[аи]|дедушк[аи])(\W{1,3}|$)'
            r'\W\d?\d?\d([.,]\d)?\W{0,2}'
            r'(?:лет|года?|л\.|мес(яц(?:а|ев)?)?|г\.,)\W{0,2}'
            r'(.{0,3}\d{4}\W?(года?(\Wр.{0,8}\W)\W?|г\.?\W?р?\.?\)?\W\W?))?(?-i:[\Wи]*)',
        ]

    else:
        pass

    if pattern_type in {
        'LOC_BLOCK',
        'PER_AGE_W_WORDS',
        'PER_AGE_WO_WORDS',
        'PER_WITH_PLUS_SIGN',
        'PER_HUMAN_BEING',
        'PER_FIO',
        'PER_BY_LAST_NUM',
    }:
        return patterns, index_type
    else:
        return patterns


def recognize_a_pattern(pattern_type: str, input_string: str) -> Tuple[Optional[List[Union[None, str, Block]]], Optional[str]]:
    """Recognize data in a string with help of given pattern type"""

    block = None
    status = None
    activity = None

    patterns = match_type_to_pattern(pattern_type)

    if patterns:
        for pattern in patterns:
            block = re.search(pattern[0], input_string)
            if block:
                status = pattern[1]
                if pattern_type in {'ST', 'TR', 'ACT'}:
                    activity = pattern[2]
                break

    if block:
        start_number = block.start()
        end_number = block.end()

        reco_part = Block()
        reco_part.init = block.group()
        reco_part.reco = status
        reco_part.type = pattern_type
        reco_part.done = True

        rest_part_before = input_string[:start_number] if start_number != 0 else None
        rest_part_after = input_string[end_number:] if end_number != len(input_string) else None

        return [rest_part_before, reco_part, rest_part_after], activity

    else:
        return None, None


def clean_and_prettify(string: str) -> str:
    """Convert a string with known mistypes to the prettified view"""

    patterns = match_type_to_pattern('MISTYPE')

    for pattern in patterns:
        string = re.sub(pattern[0], pattern[1], string)

    return string


def update_full_blocks_with_new(init_num_of_the_block_to_split: int, prev_recognition: TitleRecognition, recognized_blocks: Optional[List[Union[None, str, Block]]]) -> List[Block]:
    """Update the 'b1 Blocks' with the new recognized information"""

    if recognized_blocks:
        curr_recognition_blocks_b1 = []

        # 0. Get Blocks, which go BEFORE the recognition
        for i in range(init_num_of_the_block_to_split):
            curr_recognition_blocks_b1.append(prev_recognition.blocks[i])

        # 1. Get Blocks, which ARE FORMED by the recognition
        j = 0
        for item in recognized_blocks:
            if item and item != 'None':
                if isinstance(item, str):
                    new_block = Block()
                    new_block.init = item
                    new_block.done = False
                else:
                    new_block = item
                new_block.block_num = init_num_of_the_block_to_split + j
                j += 1
                curr_recognition_blocks_b1.append(new_block)

        # 2. Get Blocks, which go AFTER the recognition
        prev_num_of_b1_blocks = len(prev_recognition.blocks)
        num_of_new_blocks = len([item for item in recognized_blocks if item])

        if prev_num_of_b1_blocks - 1 - init_num_of_the_block_to_split > 0:
            for i in range(prev_num_of_b1_blocks - init_num_of_the_block_to_split - 1):
                new_block = prev_recognition.blocks[init_num_of_the_block_to_split + 1 + i]
                new_block.block_num = init_num_of_the_block_to_split + num_of_new_blocks + i
                curr_recognition_blocks_b1.append(new_block)

    else:
        curr_recognition_blocks_b1 = prev_recognition.blocks

    return curr_recognition_blocks_b1


def split_status_training_activity(initial_title: str, prettified_title: str) -> TitleRecognition:
    """Create an initial 'Recognition' object and recognize data for Status, Training, Activity, Avia"""

    list_of_pattern_types = [
        'ST',
        'ST',  # duplication – is not a mistake: there are cases when two status checks are necessary
        'TR',
        'AVIA',
        'ACT',
    ]

    recognition = TitleRecognition(init=initial_title, pretty=prettified_title)

    first_block = Block()
    first_block.block_num = 0
    first_block.init = prettified_title
    first_block.done = False
    recognition.blocks.append(first_block)

    # find status / training / aviation / activity – via PATTERNS
    for pattern_type in list_of_pattern_types:
        for non_reco_block in recognition.blocks:
            if non_reco_block.done:
                pass
            else:
                text_to_recognize = non_reco_block.init
                recognized_blocks, recognized_activity = recognize_a_pattern(pattern_type, text_to_recognize)
                recognition.blocks = update_full_blocks_with_new(
                    non_reco_block.block_num, recognition, recognized_blocks
                )
                if recognition.act and recognized_activity and recognition.act != recognized_activity:
                    logging.error(
                        f'RARE CASE! recognized activity does not match: ' f'{recognition.act} != {recognized_activity}'
                    )
                    pass
                if recognized_activity and not recognition.act:
                    recognition.act = recognized_activity

    for block in recognition.blocks:
        if block.type == 'TR':
            recognition.tr = block.reco
        if block.type == 'AVIA':
            recognition.avia = block.reco
        if block.type == 'ACT':
            recognition.act = block.reco
        # MEMO: recognition.st is done on the later stages of title recognition

        # FIXME – 07.11.2023 –temp debug to see blocks
        logging.info(f'0 HERE IS THE BLOCK {block.type=}, {block.init=}, {block.reco=}, {block.block_num=}')
        # FIXME ^^^

    return recognition


def check_word_by_natasha(string_to_check, direction):
    """Uses the Natasha module to define persons / locations.
    There are two directions processed: 'loc' for location and 'per' for person.
    For 'loc': Function checks if the first word in recognized string is location -> returns True
    For 'per': Function checks if the last word in recognized string is person -> returns True"""

    match_found = False

    segmenter = Segmenter()
    emb = NewsEmbedding()
    ner_tagger = NewsNERTagger(emb)

    doc = Doc(string_to_check)
    doc.segment(segmenter)
    doc.tag_ner(ner_tagger)

    if doc.spans:
        if direction == 'loc':
            first_span = doc.spans[0]

            # If first_span.start is zero it means the 1st word just after the PERSON in title – are followed by LOC
            if first_span.start == 0:
                match_found = True

        elif direction == 'per':
            last_span = doc.spans[-1]
            stripped_string = re.sub(r'\W{1,3}$', '', string_to_check)

            if last_span.stop == len(stripped_string):
                match_found = True

    return match_found


def update_reco_with_per_and_loc_blocks(recognition: TitleRecognition, string_to_split: str, block: Block, marker: int) -> TitleRecognition:
    """Update the Recognition object with two separated Blocks for Persons and Locations"""

    recognized_blocks = []

    if len(string_to_split[:marker]) > 0:
        name_block = Block()
        name_block.block_num = block.block_num
        name_block.init = string_to_split[:marker]
        name_block.done = True
        name_block.type = 'PER'
        recognized_blocks.append(name_block)

    if len(string_to_split[marker:]) > 0:
        location_block = Block()
        location_block.block_num = block.block_num + 1
        location_block.init = string_to_split[marker:]
        location_block.done = True
        location_block.type = 'LOC'
        recognized_blocks.append(location_block)

    recognition.blocks = update_full_blocks_with_new(block.block_num, recognition, recognized_blocks)

    return recognition


def split_per_from_loc_blocks(recognition: TitleRecognition) -> TitleRecognition:
    """Split the string with persons and locations into two blocks of persons and locations"""

    patterns_list = [
        'LOC_BLOCK',
        'PER_AGE_W_WORDS',
        'PER_AGE_WO_WORDS',
        'PER_WITH_PLUS_SIGN',
        'PER_HUMAN_BEING',
        'PER_FIO',
        'PER_BY_LAST_NUM',
    ]

    for block in recognition.blocks:
        if not block.type:
            string_to_split = block.init
            marker_per = 0
            marker_loc = len(string_to_split)
            marker_final = None

            for patterns_list_item in patterns_list:
                patterns, marker = match_type_to_pattern(patterns_list_item)

                for pattern in patterns:
                    marker_search = re.search(pattern, string_to_split[:marker_loc])

                    if marker_search:
                        if marker == 'loc':
                            marker_loc = min(marker_search.span()[0] + 1, marker_loc)
                        elif marker == 'per':
                            marker_per = max(marker_search.span()[1], marker_per)

                    # INTERMEDIATE RESULT: IF PERSON FINISHES WHERE LOCATION STARTS
                    if marker_per == marker_loc:
                        break
                else:
                    continue
                break

            if marker_per == marker_loc:
                marker_final = marker_per

            elif marker_per > 0:
                marker_final = marker_per

            else:
                # now we check, if the part of Title excl. recognized LOC finishes right before PER
                last_not_loc_word_is_per = check_word_by_natasha(string_to_split[:marker_loc], 'per')

                if last_not_loc_word_is_per:
                    marker_final = marker_loc

                else:
                    # language=regexp
                    patterns_2 = [[r'(?<=\W)\([А-Я][а-яА-Я,\s]*\)\W', ''], [r'\W*$', '']]
                    temp_string = string_to_split[marker_per:marker_loc]

                    for pattern_2 in patterns_2:
                        temp_string = re.sub(pattern_2[0], pattern_2[1], temp_string)

                    last_not_loc_word_is_per = check_word_by_natasha(temp_string, 'per')

                    if last_not_loc_word_is_per:
                        marker_final = marker_loc

                    elif marker_loc < len(string_to_split):
                        marker_final = marker_loc

                    else:
                        # let's check if there's any status defined for this activity
                        # if yes – there's a status – that means we can treat all the following as PER
                        there_is_status = False
                        there_is_training = False
                        num_of_blocks = len(recognition.blocks)

                        for block_2 in recognition.blocks:
                            if block_2.type == 'ST':
                                there_is_status = True
                            elif block_2.type == 'TR':
                                there_is_training = True

                        if there_is_status:
                            # if nothing helps – we're assuming all the words are Person with no Location
                            marker_final = marker_loc

                        elif there_is_training and num_of_blocks == 1:
                            pass

                        else:
                            logging.info(f'NEW RECO was not able to split per and loc for {string_to_split}')
                            pass

            if marker_final:
                recognition = update_reco_with_per_and_loc_blocks(recognition, string_to_split, block, marker_final)

    return recognition


def split_per_and_loc_blocks_to_groups(recognition: TitleRecognition) -> TitleRecognition:
    """Split the recognized Block with aggregated persons/locations to separate Groups of individuals/addresses"""

    for block in recognition.blocks:
        if block.type in {'PER', 'LOC'}:
            individual_stops = []
            groups = []
            patterns = match_type_to_pattern(f'{block.type}_BY_INDIVIDUAL')

            for pattern in patterns:
                delimiters_list = re.finditer(pattern, block.init)

                if delimiters_list:
                    for delimiters_line in delimiters_list:
                        if delimiters_line.span()[1] != len(block.init):
                            individual_stops.append(delimiters_line.span()[1])

            individual_stops = list(set(individual_stops))
            individual_stops.sort()

            block_start = 0
            block_end = 0

            for item in individual_stops:
                block_end = item
                groups.append(block.init[block_start:block_end])
                block_start = block_end
            if len(individual_stops) > 0:
                groups.append(block.init[block_end:])

            if not groups:
                groups = [block.init]

            for i, gr in enumerate(groups):
                group = Block()
                group.init = gr
                group.type = f'{block.type[0]}{i + 1}'

                recognition.groups.append(group)

        else:
            recognition.groups.append(block)

    return recognition


def define_person_display_name_and_age(curr_recognition: TitleRecognition) -> TitleRecognition:
    """Recognize the Displayed Name (Pseudonym) for ALL person/groups as well as ages"""

    def define_number_of_persons(name_string: str) -> Tuple[int, Match]:
        """Define and return the number of persons out of string input"""

        name_string_end = 'None'
        number_of_persons = None
        block = None

        # language=regexp
        pattern = r'\d{1,4}\W{0,3}(лет|л\.|года?|мес|г)?'
        block_0 = re.search(pattern, name_string)
        if block_0:
            name_string_end = block_0.span()[0]

        if name_string_end != 'None' and int(name_string_end) == 0:
            number_of_persons = 1

        else:
            # language=regexp
            patterns = [
                r'(?i)^\W{0,3}(\d|дв(а|о?е)|тр(ое|и)|чет(веро|ыре))(\W{1,2}'
                r'(человека?|женщин[аы]|мужчин[аы]?|реб[её]нок))?(?!\d)(?!\w)',  # case "2 человека"
                r'(?i)(^|(?<=\W))[\w-]{1,100}(?=\W)',  # regular case
            ]

            for pattern in patterns:
                block = re.search(pattern, name_string)
                if block:
                    # language=regexp
                    patterns_2 = [
                        [
                            r'(?i)(?<!\w)(человек|женщина|мужчина|реб[её]нок|девочка|мальчик|девушка|'
                            r'мама|папа|сын|дочь|дедушка|бабушка)(?!\w)',
                            1,
                        ],
                        [r'(?i)(?<!\w)дв(а|о?е)(?!\w)', 2],
                        [r'(?i)(?<!\w)(трое|три)(?!\w)', 3],
                        [r'(?i)(?<!\w)чет(веро|ыре)(?!\w)', 4],
                    ]
                    for pattern_2 in patterns_2:
                        exact_num_of_individuals_in_group = re.search(pattern_2[0], name_string)
                        if exact_num_of_individuals_in_group:
                            number_of_persons = pattern_2[1]
                            break

                    break

        if not number_of_persons:
            number_of_persons = -1  # -1 for unrecognized

        return number_of_persons, block

    def define_age_of_person(block: Match, name_string: str, person_reco: PersonGroup) -> PersonGroup:
        """Define and return the age (given or estimation based on birth year) for a person"""

        age = None
        year = None
        months = None
        date = None
        date_full = None
        date_short = None
        number = None

        age_string_start = block.span()[1] if block else 0

        # language=regexp
        patterns = [
            [r'\d{2}.\d{2}\.\d{4}', 'date_full'],
            [r'\d{2}.\d{2}\.\d{2}(?!\d)', 'date_short'],
            [r'(?<!\d)\d{1,2}(?=\W{0,2}мес(\W|яц))', 'age_months'],
            [r'(?<!\d)1?\d{1,2}(?!(\W{0,2}мес|\W{0,3}\d))', 'age'],
            [r'(?<!\d)\d{4}', 'year'],
            [r'(?<!\d)\d{1,2}(?!\d)', 'number'],
        ]

        for pattern in patterns:
            block_2 = re.search(pattern[0], name_string[age_string_start:])
            if block_2:
                person_reco.num_of_per = 1
                if pattern[1] == 'age_months':
                    months = block_2.group()
                if pattern[1] == 'date_full':
                    date_full = block_2.group()
                elif pattern[1] == 'date_short':
                    date_short = block_2.group()
                elif pattern[1] == 'age':
                    age = block_2.group()
                elif pattern[1] == 'year':
                    year = block_2.group()
                elif pattern[1] == 'number':
                    number = block_2.group()

        if date_full:
            date = datetime.strptime(date_full, '%d.%m.%Y')
        elif date_short:
            date = datetime.strptime(date_short, '%d.%m.%y')

        if not age and date:
            age = relativedelta.relativedelta(datetime.now(), date).years

        elif not age and year:
            year_today = datetime.today().year
            age_from_year = year_today - int(year)
            # if there's an indication of the age without explicit "years", but just a number, e.g. 57
            if number and abs(int(number) - age_from_year) in {0, 1}:
                age = number
            else:
                age = age_from_year

        elif months and not age and not year:
            age = round(int(months) / 12)

        if age:
            person_reco.age = int(age)
            person_reco.age_wording = f'{str(person_reco.age)} {age_wording(person_reco.age)}'

        if person_reco.age_wording:
            person_reco.age_wording = f' {person_reco.age_wording}'
        else:
            person_reco.age_wording = ''

        return person_reco

    def define_display_name(block: Match, person_reco: PersonGroup) -> PersonGroup:
        """Define and record the name / pseudonym that will be displayed to users"""

        # DISPLAY NAME (PSEUDONYM) IDENTIFICATION
        if block:
            person_reco.name = block.group()
        else:
            if person_reco.age and int(person_reco.age) < 18:
                person_reco.name = 'Ребёнок'
            else:
                person_reco.name = 'Человек'

        display_name = f'{person_reco.name}{person_reco.age_wording}'
        person_reco.display_name = display_name.capitalize()

        # case of two-word last names like Tom-Scott. in this case capitalize killed capital S, and we restore it
        dashes_in_names = re.search(r'\w-\w', person_reco.display_name)
        if dashes_in_names:
            letter_to_up = dashes_in_names.span()[0] + 2
            d = person_reco.display_name
            person_reco.display_name = f'{d[:letter_to_up]}{d[letter_to_up].capitalize()}{d[letter_to_up + 1:]}'

        return person_reco

    def define_age_of_person_by_natasha(person_reco: PersonGroup, name_string: str) -> PersonGroup:
        """Define and return the age for a person if the predecessor symbols are recognized as Person by Natasha"""

        # last chance to define number of persons in group - with help of Natasha
        if person_reco.num_of_per == -1:
            # language=regexp
            patterns = [r'^\D*\w(?=\W{1,3}\d)', r'^\D*\w(?=\W{1,3}$)']

            for pattern in patterns:
                block_2 = re.search(pattern, name_string)

                if block_2:
                    name_string_is_a_name = check_word_by_natasha(block_2.group(), 'per')
                    if name_string_is_a_name:
                        person_reco.num_of_per = 1
                        break

        return person_reco

    def recognize_one_person_group(person: Block) -> PersonGroup:
        """Recognize the Displayed Name (Pseudonym) for a SINGLE person/group as well as age"""

        name_string = person.init
        person_reco = PersonGroup()
        person_reco.block_num = person.type[1]

        # CASE 0. When the whole person is defined as "+N" only (NB – we already cut "+" before)
        case_0 = re.search(
            r'^\W{0,2}\d(?=(\W{0,2}(человека|женщины|мужчины|девочки|мальчика|бабушки|дедушки))?' r'\W{0,4}$)',
            name_string,
        )
        if case_0:
            person_reco.num_of_per = int(case_0.group())
            if person_reco.num_of_per == 1:
                person_reco.display_name = 'Человек'
            elif person_reco.num_of_per in {2, 3, 4}:
                person_reco.display_name = f'{person_reco.num_of_per} человека'
            else:
                person_reco.display_name = f'{person_reco.num_of_per} человек'
            person_reco.name = person_reco.display_name

            return person_reco

        # CASE 1. When there is only one person like "age" (e.g. "Пропал 10 лет")
        case = re.search(r'^1?\d?\d\W{0,3}(лет|года?)\W{0,2}$', name_string)
        if case:
            age = int(re.search(r'\d{1,3}', name_string).group())
            person_reco.num_of_per = 1
            person_reco.age = age
            if person_reco.age < 18:
                person_reco.name = 'Ребёнок'
            else:
                person_reco.name = 'Человек'
            person_reco.display_name = f'{person_reco.name}{age_wording(person_reco.age)}'

            return person_reco

        # CASE 2. When the whole person is defined as "+N age, age" only
        case_2 = re.search(
            r'(?i)^\W{0,2}(\d(?!\d)|двое|трое)'
            r'(?=(\W{0,2}(человека|женщины?|мужчины?|девочки|мальчика|бабушки|дедушки))?)',
            name_string,
        )
        if case_2:
            case_2 = case_2.group()
            if len(case_2) == 1:
                person_reco.num_of_per = int(case_2)
            elif case_2[-4:] == 'двое':
                person_reco.num_of_per = 2
            elif case_2[-4:] == 'трое':
                person_reco.num_of_per = 3

            string_with_ages = name_string[re.search(case_2, name_string).span()[1] :]
            ages_list = re.findall(r'1?\d?\d(?=\W)', string_with_ages)
            ages_list = [int(x) for x in ages_list]
            if ages_list:
                ages_list.sort()
                person_reco.age_min = int(ages_list[0])
                person_reco.age_max = int(ages_list[-1])

            if person_reco.num_of_per == 1:
                if ages_list and person_reco.age_max < 18:
                    person_reco.display_name = 'Ребёнок'
                else:
                    person_reco.display_name = 'Человек'
            elif person_reco.num_of_per in {2, 3, 4}:
                if ages_list and person_reco.age_max < 18:
                    person_reco.display_name = f'{person_reco.num_of_per} ребёнка'
                else:
                    person_reco.display_name = f'{person_reco.num_of_per} человека'
            else:
                if ages_list and person_reco.age_max < 18:
                    person_reco.display_name = f'{person_reco.num_of_per} детей'
                else:
                    person_reco.display_name = f'{person_reco.num_of_per} человек'

            person_reco.name = person_reco.display_name

            if person_reco.age_min and person_reco.age_max:
                if person_reco.age_min != person_reco.age_max:
                    person_reco.display_name = (
                        f'{person_reco.display_name} '
                        f'{person_reco.age_min}–{person_reco.age_max}'
                        f' {age_wording(person_reco.age_max)}'
                    )
                else:
                    person_reco.display_name = (
                        f'{person_reco.display_name} ' f'{person_reco.age_max}' f' {age_wording(person_reco.age_max)}'
                    )

            return person_reco

        # CASE 3. When the "person" is defined as plural form  and ages like "people age, age"
        case_3 = re.search(
            r'(?i)(?<!\d)(подростки|дети|люди|мужчины?|женщины?|мальчики|девочки|бабушки|дедушки)' r'\W{0,4}(?=\d)',
            name_string,
        )
        if case_3:
            case_3 = case_3.group()

            person_reco.num_of_per = -1

            string_with_ages = name_string[re.search(case_3, name_string).span()[1] :]
            ages_list = re.findall(r'1?\d?\d(?=\W)', string_with_ages)
            if ages_list:
                ages_list.sort()
                person_reco.age_min = int(ages_list[0])
                person_reco.age_max = int(ages_list[-1])

            if person_reco.age_max < 18:
                person_reco.display_name = 'Дети'
            else:
                person_reco.display_name = 'Взрослые'

            person_reco.name = person_reco.display_name

            if person_reco.age_min and person_reco.age_max:
                if person_reco.age_min != person_reco.age_max:
                    person_reco.display_name = (
                        f'{person_reco.display_name} '
                        f'{person_reco.age_min}–{person_reco.age_max}'
                        f' {age_wording(person_reco.age_max)}'
                    )
                else:
                    person_reco.display_name = (
                        f'{person_reco.display_name} ' f'{person_reco.age_max}' f' {age_wording(person_reco.age_max)}'
                    )
            return person_reco

        # CASE 4. When the whole person is defined as "role" only
        if re.search(
            r'(?i)^(женщина|мужчина|декушка|человек|дочь|сын|жена|муж|отец|мать|папа|мама|'
            r'бабушка|дедушка)(?=\W{0,4}$)',
            name_string,
        ):
            person_reco.num_of_per = 1
            person_reco.name = re.search(r'(?i)^\w*(?=\W{0,4}$)', name_string).group()
            person_reco.display_name = 'Человек'

            return person_reco

        # CASE 5. All the other more usual cases
        person_reco.num_of_per, block = define_number_of_persons(name_string)
        person_reco = define_age_of_person(block, name_string, person_reco)
        person_reco = define_display_name(block, person_reco)
        person_reco = define_age_of_person_by_natasha(person_reco, name_string)

        return person_reco

    for person_group in curr_recognition.groups:
        if person_group.type and person_group.type[0] == 'P':
            person_group.reco = recognize_one_person_group(person_group)

    return curr_recognition


def define_person_block_display_name_and_age_range(curr_recognition: TitleRecognition) -> TitleRecognition:
    """Define the Displayed Name (Pseudonym) and Age Range for the whole Persons Block"""

    # level of PERSON BLOCKS (likely to be only one for each title)
    num_of_per_blocks = len([x for x in curr_recognition.blocks if x.type and x.type[0] == 'P'])
    num_of_per_groups = len([x for x in curr_recognition.groups if x.type and x.type[0] == 'P'])
    for block in curr_recognition.blocks:
        if block.type and block.type[0] == 'P':
            block.reco = PersonGroup()
            final_num_of_pers = 0
            num_of_groups_in_block = 0
            final_pseudonym = ''
            age_list = []
            first_group_num_of_pers = None

            # go to the level of PERSON GROUPS (subgroup in person block)
            for group in curr_recognition.groups:
                if group.type and group.type[0] == 'P':
                    num_of_groups_in_block += 1

                    # STEP 1. Define the number of persons for search
                    num_of_persons = group.reco.num_of_per
                    if not first_group_num_of_pers:
                        first_group_num_of_pers = num_of_persons

                    if isinstance(num_of_persons, int) and num_of_persons > 0 and final_num_of_pers != -1:
                        # -1 stands for unrecognized number of people
                        final_num_of_pers += num_of_persons
                    else:
                        final_num_of_pers = -1  # -1 stands for unrecognized number of people

                    # STEP 2. Define the pseudonym for the person / group
                    if group.reco.name:
                        if not final_pseudonym:
                            if num_of_persons > 1:
                                final_pseudonym = group.reco.display_name
                            else:
                                final_pseudonym = group.reco.name
                            block.reco.name = group.reco.name

                    if group.reco.age or group.reco.age == 0:
                        age_list.append(group.reco.age)
                    if group.reco.age_min:
                        age_list.append(group.reco.age_min)
                    if group.reco.age_max:
                        age_list.append(group.reco.age_max)

            if age_list and len(age_list) > 1:
                age_list.sort()
                block.reco.age = age_list
                if min(age_list) != max(age_list):
                    block.reco.age_wording = f'{min(age_list)}–{max(age_list)} {age_wording(max(age_list))}'
                else:
                    block.reco.age_wording = f'{max(age_list)} {age_wording(max(age_list))}'

            elif age_list and len(age_list) == 1:
                block.reco.age = age_list[0]
                block.reco.age_wording = f'{age_list[0]} {age_wording(age_list[0])}'
            else:
                block.reco.age = []
                block.reco.age_wording = None

            if block.reco.age_wording:
                final_age_words = f' {block.reco.age_wording}'
            else:
                final_age_words = ''

            if final_pseudonym and final_num_of_pers == 1:
                final_pseudonym = f'{final_pseudonym}{final_age_words}'
            elif final_pseudonym and final_num_of_pers > 1:
                if final_pseudonym in {'дети', 'люди', 'подростки'}:
                    final_pseudonym = f'{final_pseudonym}{final_age_words}'
                elif num_of_per_blocks == 1 and num_of_per_groups == 1:
                    if not block.reco.age:  # added due to 5052
                        final_pseudonym = block.reco.name
                else:
                    final_pseudonym = (
                        f'{final_pseudonym} + {final_num_of_pers - first_group_num_of_pers} ' f'чел.{final_age_words}'
                    )
            elif final_pseudonym and num_of_groups_in_block == 1 and final_num_of_pers == -1:
                final_pseudonym = f'{final_pseudonym}{final_age_words}'
            else:
                final_pseudonym = f'{final_pseudonym} и Ко.{final_age_words}'

            block.reco.display_name = final_pseudonym.capitalize()
            block.reco.block_num = final_num_of_pers

    return curr_recognition


def prettify_loc_group_address(curr_recognition: TitleRecognition) -> TitleRecognition:
    """Prettify (delete unneeded symbols) every location address"""

    for location in curr_recognition.groups:
        if location.type and location.type[0] == 'L':
            location.reco = location.init
            location.reco = re.sub(r'[,!?\s\-–—]{1,5}$', '', location.reco)

    return curr_recognition


def define_loc_block_summary(curr_recognition: TitleRecognition) -> TitleRecognition:
    """For Debug and not for real prod use. Define the cumulative location string based on addresses"""

    # level of PERSON BLOCKS (should be only one for each title)
    for block in curr_recognition.blocks:
        if block.type and block.type[0] == 'L':
            block.reco = ''

            # go to the level of LOCATION GROUPS (subgroup in locations block)
            for individual_block in curr_recognition.groups:
                if individual_block.type and individual_block.type[0] == 'L':
                    block.reco += f', {individual_block.reco}'

            if block.reco:
                block.reco = block.reco[2:]

    return curr_recognition


def define_general_status(recognition: TitleRecognition) -> TitleRecognition:
    """In rare cases searches have 2 statuses: or by mistake or due to differences between lost persons' statues"""

    # FIXME - 07.11.2023 – for status_only debug
    for block in recognition.blocks:
        logging.info(f'3 RECO BLOCKS: {block.type=}, {block.init=}, {block.reco=}, {block.block_num=}')
    logging.info(f'3 RECO ST: {recognition.st}')
    # FIXME ^^^

    if recognition:
        statuses_list = []
        for j, block in enumerate(recognition.groups):
            if block.type and block.type == 'ST':
                statuses_list.append([j, block.reco])

        # FIXME - 07.11.2023 – for status_only debug
        logging.info(f'5 RECO list: {statuses_list=}')
        # FIXME ^^^

        # if status is the only one (which is true in 99% of cases)
        if len(statuses_list) == 1:
            recognition.st = statuses_list[0][1]

            # FIXME - 07.11.2023 – for status_only debug
            logging.info(f'6 RECO list: {statuses_list=}')
            logging.info(f'6 RECO ST: {recognition.st}')
            # FIXME ^^^

        # if there are more than 1 status. have never seen 3, so stopping on 2
        elif len(statuses_list) > 1:
            # if statuses goes one-just-after-another --> it means a mistake. Likely 1st status is correct
            if statuses_list[1][0] - statuses_list[0][0] == 1:
                recognition.st = statuses_list[0][1]

            # if there's another block between status blocks – which is not mistake, but just a rare case
            else:
                if statuses_list[0][1] == statuses_list[1][1]:
                    recognition.st = statuses_list[0][1]
                else:
                    recognition.st = f'{statuses_list[0][1]} и {statuses_list[1][1]}'

    # FIXME - 07.11.2023 – for status_only debug
    for block in recognition.blocks:
        logging.info(f'4 RECO BLOCKS: {block.type=}, {block.init=}, {block.reco=}, {block.block_num=}')
    logging.info(f'4 RECO ST: {recognition.st}')
    # FIXME ^^^

    return recognition


def calculate_total_num_of_persons(recognition: TitleRecognition) -> TitleRecognition:
    """Define the Total number of persons to search"""

    if recognition.act == 'search':
        # language=regexp
        patterns = [
            [r'(?i)пропала?(?!и)', True],
            [r'(?i)пропали', False],
            [r'(?i)ппохищена?(?!ы)', True],
            [r'(?i)похищены', False],
            [r'(?i)найдена?(?!ы)', True],
            [r'(?i)найдены', False],
            [r'(?i)жива?(?!ы)', True],
            [r'(?i)живы', False],
            [r'(?i)погиб(ла)?(?!ли)', True],
            [r'(?i)погибли', False],
        ]

        status_says_only_one_person = None  # can be None - unrecognized / True or False

        for block in recognition.blocks:
            if block.type == 'ST':
                for pattern in patterns:
                    match = re.search(pattern[0], block.init)
                    if match:
                        # as per statistics of 27k cases these was no single case when
                        # there were two contradictory statuses
                        status_says_only_one_person = pattern[1]
                        break
                else:
                    continue
                break

        pers_list = []
        for block in recognition.groups:
            if block.type and block.type[0] == 'P':
                pers_list.append(block.reco.num_of_per)

        # per_blocks_says can be: [1-9] / 'group' / 'unidentified'
        if not pers_list:
            per_blocks_says = 'unidentified'
        else:
            if min(pers_list) == -1 and len(pers_list) > 1:
                per_blocks_says = 'group'
            elif min(pers_list) == -1 and len(pers_list) == 1:
                per_blocks_says = 'unidentified'
            else:  # that means = min(pers_list) > -1:
                per_blocks_says = sum(pers_list)

        # total_num_of_persons can be: [1-9] / 'group' / 'unidentified'
        if per_blocks_says == 'unidentified':
            if status_says_only_one_person == True:  # noqa – intentively to highlight that it is not False / None
                total_num_of_persons = 1
            elif status_says_only_one_person == False:  # noqa – to aviod case of 'None'
                total_num_of_persons = 'group'
            else:
                total_num_of_persons = 'unidentified'
        else:
            total_num_of_persons = per_blocks_says

        recognition.per_num = total_num_of_persons

    return recognition


def generate_final_reco_dict(recognition: TitleRecognition):
    """Generate the final outcome dictionary for recognized title"""

    final_dict = {}

    """
    SCHEMA:
    {topic_type = search / search reverse / search patrol / search training / event / info,
    [optional, only for search] avia = True / False,
    [optional, only for search / search reverse] status,
    [optional, only for search] persons =
        {
        total_persons = [1-9] / group / undefined
        age_min = [0-199]
        age_max = [0-199]
        total_name = name of the first person
        total_display_name = display name + age (age range)
        person =
            [
            [optional] person =
                {
                name = one-word description,
                [optional] age = [0-199] in years,
                [optional] age_min = [0-199] in years,
                [optional] age_max = [0-199] in years,
                display_name = display name + age,
                number_of_persons = -1 or [1-9] (only in this group of persons)
                }
            ]
        }
    [optional, only for search] locations =
        [
            {
            address = string
            }
        ]
    }
    """

    # FIXME - 07.11.2023 – for status_only debug
    for block in recognition.blocks:
        logging.info(f'1 RECO BLOCKS: {block.type=}, {block.init=}, {block.reco=}, {block.block_num=}')
    logging.info(f'1 RECO ST: {recognition.st}')
    # FIXME ^^^

    persons_identified = False
    for block in recognition.blocks:
        if block.type == 'PER':
            persons_identified = True
            break

    if not recognition.act and not recognition.st and persons_identified:
        recognition.act = 'search'
        recognition.st = 'Ищем'
        # FIXME - 07.11.2023 – for status_only debug
        logging.info(f'2 RECO ST: {recognition.st}')
        # FIXME ^^^

    if recognition.act and not recognition.st and recognition.tr:
        recognition.st = 'Ищем'

    if recognition.act:
        final_dict['topic_type'] = recognition.act
    else:
        final_dict['topic_type'] = 'UNRECOGNIZED'

    if recognition.avia:
        final_dict['avia'] = True

    if recognition.st:
        final_dict['status'] = recognition.st

    persons = []
    locations = []
    for block in recognition.groups:
        if block.type == 'ACT':
            final_dict['topic_type'] = block.reco

        elif block.type and block.type[0] == 'P':
            individual_dict = {}
            if block.reco.name:
                individual_dict['name'] = block.reco.name
            if block.reco.age:
                individual_dict['age'] = block.reco.age
            if block.reco.age_min:
                individual_dict['age_min'] = block.reco.age_min
            if block.reco.age_max:
                individual_dict['age_max'] = block.reco.age_max
            if block.reco.display_name:
                individual_dict['display_name'] = block.reco.display_name
            if block.reco.num_of_per:
                individual_dict['number_of_persons'] = block.reco.num_of_per
            if individual_dict:
                persons.append(individual_dict)

        elif block.type and block.type[0] == 'L':
            individual_dict = {}
            if block.reco:
                individual_dict['address'] = block.reco
            if individual_dict:
                locations.append(individual_dict)

    if recognition.tr:
        final_dict['topic_type'] = 'search training'

    if persons:
        summary = {}
        for block in recognition.blocks:
            if block.type and block.type == 'PER':
                summary['total_persons'] = block.reco.block_num
                summary['total_name'] = block.reco.name
                summary['total_display_name'] = block.reco.display_name
                if isinstance(block.reco.age, list) and len(block.reco.age) > 0:
                    summary['age_min'] = block.reco.age[0]
                    summary['age_max'] = block.reco.age[-1]
                elif isinstance(block.reco.age, list):
                    summary['age_min'] = None
                    summary['age_max'] = None
                else:
                    summary['age_min'] = block.reco.age
                    summary['age_max'] = block.reco.age
                break

        summary['person'] = persons
        final_dict['persons'] = summary

    if locations:
        final_dict['locations'] = locations

    # placeholders if no persons
    if final_dict['topic_type'] in {'search', 'search training'} and 'persons' not in final_dict.keys():
        per_dict = {'total_persons': -1, 'total_name': 'Неизвестный', 'total_display_name': 'Неизвестный'}
        final_dict['persons'] = per_dict

    if (
        'persons' in final_dict.keys()
        and 'total_persons' in final_dict['persons'].keys()
        and final_dict['persons']['total_persons'] == -1
        and recognition.per_num == 1
    ):
        final_dict['persons']['total_persons'] = 1

    return final_dict


def recognize_title(line: str, reco_type: str) -> Union[Dict, None]:
    """Recognize LA Thread Subject (Title) and return a dict of recognized parameters"""
    prettified_line = clean_and_prettify(line)
    recognition_result = split_status_training_activity(line, prettified_line)

    if reco_type == 'status_only':
        recognition_result = split_per_from_loc_blocks(recognition_result)
        recognition_result = split_per_and_loc_blocks_to_groups(recognition_result)
        recognition_result = define_person_display_name_and_age(recognition_result)
        recognition_result = define_person_block_display_name_and_age_range(recognition_result)
        recognition_result = define_general_status(recognition_result)
    else:
        recognition_result = split_per_from_loc_blocks(recognition_result)
        recognition_result = split_per_and_loc_blocks_to_groups(recognition_result)
        recognition_result = define_person_display_name_and_age(recognition_result)
        recognition_result = define_person_block_display_name_and_age_range(recognition_result)
        recognition_result = prettify_loc_group_address(recognition_result)
        recognition_result = define_loc_block_summary(recognition_result)
        recognition_result = define_general_status(recognition_result)
        recognition_result = calculate_total_num_of_persons(recognition_result)

    final_recognition_dict = generate_final_reco_dict(recognition_result)

    return final_recognition_dict
