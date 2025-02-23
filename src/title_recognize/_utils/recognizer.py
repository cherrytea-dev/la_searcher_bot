import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, ValidationError


from .person import define_person_display_name_and_age
from .title_commons import Block, PersonGroup, TitleRecognition, age_wording, check_word_by_natasha, TopicType

from typing import List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict


class Person(BaseModel):
    name: str = Field(description='One-word description')
    age: Optional[int] = Field(None, ge=0, le=199, description='Age in years')
    age_min: Optional[int] = Field(None, ge=0, le=199, description='Minimum age in years')
    age_max: Optional[int] = Field(None, ge=0, le=199, description='Maximum age in years')
    display_name: str = Field(description='Display name + age')
    number_of_persons: int = Field(..., ge=-1, le=9, description='Number of persons in this group, -1 or 1-9')


class Persons(BaseModel):
    total_persons: Union[int, str] = Field(..., description="Total number of persons: 1-9, 'group', or 'undefined'")
    age_min: Optional[int] = Field(None, ge=0, le=199, description='Minimum age across all persons')
    age_max: Optional[int] = Field(None, ge=0, le=199, description='Maximum age across all persons')
    total_name: str = Field(description='Name of the first person')
    total_display_name: str = Field(description='Display name + age (age range)')
    person: List[Person] = Field(default_factory=list)


class Location(BaseModel):
    address: str


class RecognitionResult(BaseModel):
    topic_type: TopicType
    avia: Optional[bool] = Field(None, description='Only for search')
    status: Optional[str] = Field(None, description='Only for search / search reverse')
    persons: Optional[Persons] = Field(None, description='Only for search')
    locations: Optional[List[Location]] = Field(None, description='Only for search')


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


def recognize_a_pattern(
    pattern_type: str, input_string: str
) -> Tuple[Optional[List[Union[None, str, Block]]], Optional[str]]:
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

        reco_part = Block(init=block.group(), reco=status, type=pattern_type, done=True)

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


def update_full_blocks_with_new(
    init_num_of_the_block_to_split: int,
    prev_recognition: TitleRecognition,
    recognized_blocks: Optional[List[Union[None, str, Block]]],
) -> List[Block]:
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

    first_block = Block(block_num=0, init=prettified_title, done=False)
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


def update_reco_with_per_and_loc_blocks(
    recognition: TitleRecognition, string_to_split: str, block: Block, marker: int
) -> TitleRecognition:
    """Update the Recognition object with two separated Blocks for Persons and Locations"""

    recognized_blocks = []

    if len(string_to_split[:marker]) > 0:
        name_block = Block(block_num=block.block_num, init=string_to_split[:marker], done=True, type='PER')
        recognized_blocks.append(name_block)

    if len(string_to_split[marker:]) > 0:
        location_block = Block(block_num=block.block_num + 1, init=string_to_split[marker:], done=True, type='LOC')
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


def define_person_block_display_name_and_age_range(curr_recognition: TitleRecognition) -> TitleRecognition:
    """Define the Displayed Name (Pseudonym) and Age Range for the whole Persons Block"""

    # level of PERSON BLOCKS (likely to be only one for each title)
    num_of_per_blocks = len([x for x in curr_recognition.blocks if x.is_person()])
    num_of_per_groups = len([x for x in curr_recognition.groups if x.is_person()])

    for block in curr_recognition.blocks:
        if not block.is_person():
            continue
        block.reco = PersonGroup()
        final_num_of_pers = 0
        num_of_groups_in_block = 0
        final_pseudonym = ''
        age_list = []
        first_group_num_of_pers = None

        # go to the level of PERSON GROUPS (subgroup in person block)
        for group in curr_recognition.groups:
            if group.is_person():
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

    for block in curr_recognition.groups:
        if block.is_location():
            block.reco = block.init
            block.reco = re.sub(r'[,!?\s\-–—]{1,5}$', '', block.reco)

    return curr_recognition


def define_loc_block_summary(curr_recognition: TitleRecognition) -> TitleRecognition:
    """For Debug and not for real prod use. Define the cumulative location string based on addresses"""

    # level of PERSON BLOCKS (should be only one for each title)
    for block in curr_recognition.blocks:
        if block.is_location():
            block.reco = ''

            # go to the level of LOCATION GROUPS (subgroup in locations block)
            for individual_block in curr_recognition.groups:
                if individual_block.is_location():
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

    if recognition.act != 'search':
        return recognition

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
        if block.is_person():
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


def generate_final_reco_dict(recognition: TitleRecognition) -> RecognitionResult:
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

    result = RecognitionResult.model_construct()
    persons_identified = any(True for block in recognition.blocks if block.type == 'PER')

    if not recognition.act and not recognition.st and persons_identified:
        recognition.act = 'search'
        recognition.st = 'Ищем'
        # FIXME - 07.11.2023 – for status_only debug
        logging.info(f'2 RECO ST: {recognition.st}')
        # FIXME ^^^

    if recognition.act and not recognition.st and recognition.tr:
        recognition.st = 'Ищем'

    if recognition.act:
        result.topic_type = recognition.act

    if recognition.avia:
        final_dict['avia'] = True

    if recognition.st:
        final_dict['status'] = recognition.st

    persons = []
    locations = []
    for block in recognition.groups:
        if block.type == 'ACT':
            result.topic_type = block.reco

        elif block.is_person():
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

        elif block.is_location():
            individual_dict = {}
            if block.reco:
                individual_dict['address'] = block.reco
            if individual_dict:
                locations.append(individual_dict)

    if recognition.tr:
        result.topic_type = 'search training'

    _fill_result_persons(recognition, final_dict, persons)

    if locations:
        final_dict['locations'] = locations

    # placeholders if no persons
    if result.topic_type in {'search', 'search training'} and 'persons' not in final_dict.keys():
        per_dict = {'total_persons': -1, 'total_name': 'Неизвестный', 'total_display_name': 'Неизвестный'}
        final_dict['persons'] = per_dict

    if (
        'persons' in final_dict.keys()
        and 'total_persons' in final_dict['persons'].keys()
        and final_dict['persons']['total_persons'] == -1
        and recognition.per_num == 1
    ):
        final_dict['persons']['total_persons'] = 1

    final_dict['topic_type'] = result.topic_type
    result = RecognitionResult.model_validate(final_dict)
    # result.model_validate(**result)
    return result


def _fill_result_persons(recognition: TitleRecognition, final_dict: dict, persons: list[dict]) -> None:
    if not persons:
        return
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

    final_recognition = generate_final_reco_dict(recognition_result)

    return final_recognition.model_dump(exclude_none=True)
