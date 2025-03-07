from typing import List

from .title_commons import BlockType, PatternType


class BlockTypePatternCollection:
    @classmethod
    def get_patterns(cls, pattern_type: BlockType) -> List[tuple[str, str, str]]:
        """Return a list of regex patterns (with additional parameters) for a specific type"""

        match = {
            BlockType.TR: cls._train_search_patterns,
            BlockType.ST: cls._status_patterns,
            BlockType.ACT: cls._act_patterns,
            BlockType.AVIA: cls._avia_patterns,
        }
        return match[pattern_type]()

    @classmethod
    def get_person_by_individual_patterns(cls) -> list[str]:
        return [
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

    @classmethod
    def get_location_by_individual_patterns(cls) -> list[str]:
        return [r'(?<![\-–—])*\W{1,3}[\-–—]\W{1,2}(?![\-–—])*']

    @classmethod
    def _act_patterns(cls) -> list[tuple[str, str, str]]:
        return [
            (r'(?i).*учебные\sсборы.*\n?', 'event', 'event'),
            (r'(?i).*учения.*\n?', 'event', 'event'),
            (
                r'(?i).*((полевое|практическ(ое|ие)) обучение|полевая тр?енировка|'
                r'полевое( обучающее)? заняти[ея]|практическ(ое|ие)\W{1,3}заняти[ея]).*\n?',
                'event',
                'event',
            ),
            (r'(?i).*(обучалк[иа]).*\n?', 'event', 'event'),
            (r'(?i).*обучение по.*\n?', 'event', 'event'),
            (r'(?i).*курс по.*\n?', 'event', 'event'),
            (
                r'(?i).*(новичк(и|ами?|овая|овый)|новеньки[ем]|знакомство с отрядом|для новичков)(\W.*|$)\n?',
                'event',
                'event',
            ),
            (r'(?i).*(вводная лекция)\W.*\n?', 'event', 'event'),
            (r'(?i).*(лекци\w\sо)\W.*\n?', 'event', 'event'),
            (
                r'(?i).*\W?(обучение|онлайн-лекция|лекция|школа волонт[её]ров|обучающее мероприятие|(?<!парт)съезд|'
                r'семинар|собрание).*\n?',
                'event',
                'event',
            ),
            (r'(?i).*ID-\W?\d{1,7}.*\n?', 'info', 'info'),
            (r'(?i)ночной патруль.*\n?', 'search patrol', 'search patrol'),
        ]

    @classmethod
    def _status_patterns(cls) -> list[tuple[str, str, str]]:
        return [
            (
                r'(?i)(личност[ьи] (родных\W{1,3})?установлен[аы]\W{1,3}((родные\W{1,3})?найден[аы]?\W{1,3})?)',
                'Завершен',
                'search reverse',
            ),
            (r'(?i)(найдена?\W{1,3})(?=(неизвестн(ая|ый)|.*называет себя\W|.*на вид\W))', 'Ищем', 'search reverse'),
            (r'(?i)до сих пор не найден[аы]?\W{1,3}', 'Ищем', 'search'),
            (r'(?i)пропал[аи]?\W{1,3}стоп\W', 'СТОП', 'search'),
            (
                r'(?i)(^\W{0,2}|(?<=\W)|(найден[аы]?\W{1,3})?)'
                r'жив[аы]?'
                r'(\W{1,3}(проверка(\W{1,3}информации)?|пропал[аи]?))?'
                r'(\W{1,3}|$)',
                'НЖ',
                'search',
            ),
            (
                r'(?i)(^\W{0,2}|(?<=\W)|(найден[аы]?\W{1,3})?)'
                r'погиб(л[иа])?'
                r'(\W{1,3}(проверка(\W{1,3}информации)?|пропал[аи]?))?'
                r'(\W{1,3}|$)',
                'НП',
                'search',
            ),
            (
                r'(?i)(?<!родственники\W)(?<!родные\W)(пропал[аы]\W{1,3}?)?найден[аы]?\W{1,3}(?!неизвестн)',
                'Найден',
                'search',
            ),
            (
                r'(?i)[сc][тt][оo]п\W{1,3}(?!проверка)(.{0,15}эвакуация\W)\W{0,2}(пропал[аи]?\W{1,3})?',
                'СТОП ЭВАКУАЦИЯ',
                'search',
            ),
            (r'(?i)[сc][тt][оo]п\W(.{0,15}проверка( информации)?\W)\W{0,2}(пропал[аи]?\W{1,3})?', 'СТОП', 'search'),
            (r'(?i)[сc][тt][оo]п\W{1,3}(пропал[аи]?\W{1,3})?', 'СТОП', 'search'),
            (r'(?i)проверка( информации)?\W{1,3}(пропал[аи]?\W{1,3})?', 'СТОП', 'search'),
            (r'(?i).{0,15}эвакуация\W{1,3}', 'ЭВАКУАЦИЯ', 'search'),
            (r'(?i)поиск ((при)?остановлен|заверш[её]н|прекращ[её]н)\W{1,3}', 'Завершен', 'search'),
            (r'(?i)\W{0,2}(поиск\W{1,3})?возобновл\w{1,5}\W{1,3}', 'Возобновлен', 'search'),
            (r'(?i)((выезд\W{0,3})?пропал[аи]?|похищен[аы]?)\W{1,3}', 'Ищем', 'search'),
            (
                r'(?i)(поиски?|помогите найти|ищем)\W(родных|родственник(ов|а)|знакомых)\W{1,3}',
                'Ищем',
                'search reverse',
            ),
            (r'(?i)помогите (установить личность|опознать человека)\W{1,3}', 'Ищем', 'search reverse'),
            (r'(?i)(родные|родственники)\Wнайдены\W{1,3}', 'Завершен', 'search reverse'),
            (r'(?i)личность установлена\W{1,3}', 'Завершен', 'search reverse'),
            (r'(?i)потеряшки в больницах\W{1,3}', 'Ищем', 'search reverse'),
            (r'(?i)(^|\W)информации\W', 'СТОП', 'search'),
            (r'(?i)(?<!поиск\W)((при)?остановлен|заверш[её]н|прекращ[её]н)\W{1,3}', 'Завершен', 'search'),
        ]

    @classmethod
    def _train_search_patterns(cls) -> list[tuple[str, str, str]]:
        return [(r'(?i)\(?учебн(ый|ая)(\W{1,3}((поиск|выход)(\W{1,4}|$))?|$)', 'Учебный', 'search')]

    @classmethod
    def _avia_patterns(cls) -> list[tuple[str, str, str]]:
        # TODO do we need second element in tuple here?
        return [(r'(?i)работает авиация\W', 'Авиация', '')]


class PatternCollectionbyBlockType:
    @classmethod
    def get_patterns(cls, pattern_type: PatternType) -> list[str]:
        """Return a list of regex patterns for a specific type"""

        match = {
            PatternType.LOC_BLOCK: cls._loc_block_patterns,
            PatternType.PER_AGE_W_WORDS: cls._per_age_w_words_patterns,
            PatternType.PER_AGE_WO_WORDS: cls._per_age_wo_words_patterns,
            PatternType.PER_WITH_PLUS_SIGN: cls._per_with_plus_sign_patterns,
            PatternType.PER_HUMAN_BEING: cls._per_human_being_patterns,
            PatternType.PER_FIO: cls._per_fio_patterns,
            PatternType.PER_BY_LAST_NUM: cls._per_by_last_num_patterns,
        }
        return match[pattern_type]()

    @classmethod
    def _loc_block_patterns(cls) -> list[str]:
        return [
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

    @classmethod
    def _per_age_w_words_patterns(cls) -> list[str]:
        return [
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

    @classmethod
    def _per_age_wo_words_patterns(cls) -> list[str]:
        return [r'(?i)\d{1,3}(\W{1,4}(?!\d)|$)']

    @classmethod
    def _per_with_plus_sign_patterns(cls) -> list[str]:
        return [
            r'(?i)\W{0,3}\+\W{0,2}((женщина|девушка|мама|\d(\W{0,3}человека?\W{1,3})?)|'
            r'(?=[^+]*$)[^+]{0,25}\d{0,3})[^+\w]{1,3}'
        ]

    @classmethod
    def _per_human_being_patterns(cls) -> list[str]:
        return [
            r'(?i).*(женщин[аы]|мужчин[аы]|декушк[аи]|человека?|дочь|сын|жена|муж|отец|мать|папа|мама|'
            r'бабушк[аи]|дедушк[аи])(\W{1,3}|$)'
        ]

    @classmethod
    def _per_fio_patterns(cls) -> list[str]:
        return [r'.*\W{1,3}[А-Я]\.\W{0,2}[А-Я]\.\W*']

    @classmethod
    def _per_by_last_num_patterns(cls) -> list[str]:
        return [r'.*[^1]1?\d{1,2}(?![0-9])\W{1,5}']


def get_mistype_patterns() -> list[tuple[str, str]]:
    """Known mistypes and their replaces in posts texts"""
    return [
        (r'^\W{0,3}Re:\W{0,3}', ''),  # removes replied mark
        (r'(?i)^\W{0,3}внимание\W{1,3}', ''),  # removes unnecessary info
        (r'^(\s{1,3}|])', ''),  # removes all unnecessary symbols in the beginning of the string
        (r'[\s\[/\\(]{1,3}$', ''),  # removes all unnecessary symbols in the end of the string
        # noinspection PyUnresolvedReferences
        (r'([.,;:!?\s])\1+', r'\1'),  # noqa
        # removes all duplicates in blank spaces or punctuation marks
        (r'(?<!\d)\B(?=\d)', ' '),  # when and con  sequent number age typed w/o a space, example: word49
        (r'(\[/?b]|\[?size\W?=\W?140]|\[/size]|\[/?color=.{0,8}])', ''),  # rare case of php formatting
        (
            r'(?i)((?<=\d\Wлет\W)|(?<=\d\Wлет\W\W)|(?<=\d\Wгод\W)|(?<=\d\Wгод\W\W)|'
            r'(?<=\d\Wгода\W)|(?<=\d\Wгода\W\W))\d{1,2}(?=,)',
            '',
        ),  # case when '80 лет 80,' – last num is wrong
        (r'(?i)без вести\s', ' '),  # rare case of 'пропал без вести'
        (r'(?i)^ропал', 'Пропал'),  # specific case for one search
        (r'(?i)пропалпропал', 'Пропал'),  # specific case for one search
        (r'(?i)^форум\W{1,3}', ''),  # specific case for one search
        (r'(?i)^э\W{1,3}', ''),  # specific case for one search
        (r'попал ', 'пропал '),  # specific case for one search
        (r'(?i)найлен(?=\W)', 'найден'),  # specific case for one search
        (r'(?i)^нж(?=\W)', 'найден жив'),  # specific case for one search
        (r'ле,т', 'лет,'),  # specific case for one search
        (r'(?i)^Стор', 'Стоп'),  # specific case for one search
        (r'ПроЖив', 'Жив'),  # specific case for one search
        (r'\(193,', ','),  # specific case for one search
        (r'\[Учения]', 'Учебный'),  # specific case for one search
        (r'(?i)\Bпропал[аи](?=\W)', ''),  # specific case for one search
        (r'(?i)проаерка(?=\W)', 'проверка'),  # specific case for one search
        (r'(?i)поиск завешен', 'поиск завершен'),  # specific case for one search
        (r'(?i)поиск заверешен', 'поиск завершен'),  # specific case for one search
        (r':bd', ''),  # specific case for one search
        (r'Стоп(?=[А-Я])', 'Стоп '),  # specific case for one search
        (r'Жив(?=[А-Я])', 'Жив '),  # specific case for one search
        (r'Жмва ', 'Жива '),  # specific case for one search
        (r'Жтва ', 'Жива '),  # specific case for one search
        (r'Жиаа ', 'Жива '),  # specific case for one search
        (r'Проопал', 'Пропал'),  # specific case for one search
        (r'Жиаа(?=[А-Я])', 'Жива '),  # specific case for one search
        (r'Жива?(?=[А-Я])', 'Жива '),  # specific case for one search
        (r'(?i)погию\s', 'погиб '),  # specific case for one search
        (r'р.п ', 'р.п. '),  # specific case for one search
        (r'(?<=\d{4}\W)г\.?р?', 'г.р.'),  # rare case
        (r'(?<!\d)\d{3}\Wг\.р\.', ''),  # specific case for one search
        (r'(?<=\d{2}\Wгод\W{2}\d{4})\W{1,3}(?!г)', ' г.р. '),  # specific case for one search
        (r'((?<=год)|(?<=года)|(?<=лет))\W{1,2}\(\d{1,2}\W{1,2}(года?|лет)?\W?на м\.п\.\)', ' '),  # rare case
        (r'(?i)провекра\s', 'проверка '),  # specific case for one search
    ]
