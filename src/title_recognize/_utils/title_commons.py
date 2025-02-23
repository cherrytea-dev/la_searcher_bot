from _dependencies.misc import age_writer
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from natasha import Doc, NewsEmbedding, NewsNERTagger, Segmenter


class TopicType(str, Enum):
    search = 'search'
    search_reverse = 'search reverse'
    search_patrol = 'search patrol'
    search_training = 'search training'
    event = 'event'
    info = 'info'
    unrecognized = 'UNRECOGNIZED'


class BlockType(str, Enum):
    AVIA = 'AVIA'
    TR = 'TR'  # training
    ST = 'ST'  # status
    ACT = 'ACT'  # activity?
    LOC_BY_INDIVIDUAL = 'LOC_BY_INDIVIDUAL'
    PER_BY_INDIVIDUAL = 'PER_BY_INDIVIDUAL'


class PatternType(str, Enum):
    LOC_BLOCK = 'LOC_BLOCK'
    PER_AGE_W_WORDS = 'PER_AGE_W_WORDS'
    PER_AGE_WO_WORDS = 'PER_AGE_WO_WORDS'
    PER_WITH_PLUS_SIGN = 'PER_WITH_PLUS_SIGN'
    PER_HUMAN_BEING = 'PER_HUMAN_BEING'
    PER_FIO = 'PER_FIO'
    PER_BY_LAST_NUM = 'PER_BY_LAST_NUM'

    @classmethod
    def all_without_mistype(cls) -> list['PatternType']:
        #  TODO can be removed
        return [
            cls.LOC_BLOCK,
            cls.PER_AGE_W_WORDS,
            cls.PER_AGE_WO_WORDS,
            cls.PER_WITH_PLUS_SIGN,
            cls.PER_HUMAN_BEING,
            cls.PER_FIO,
            cls.PER_BY_LAST_NUM,
        ]


@dataclass
class PersonGroup:
    block_num: int | None = None
    type: Any = None  # TODO rename
    num_of_per: Any = None
    display_name: Any = None
    name: Any = None
    age: Any = None
    age_min: Any = None
    age_max: Any = None
    age_wording: Any = None


@dataclass
class Block:
    block_num: int = 0
    init: str = None  # initial text, prettified
    reco: PersonGroup = None
    type: str | None = None
    done: bool = False

    def is_person(self) -> bool:
        return self.type and self.type.startswith('P')

    def is_location(self) -> bool:
        return self.type and self.type.startswith('L')


@dataclass
class TitleRecognition:
    init: str
    pretty: str
    blocks: list[Block] = field(default_factory=list)
    groups: list[Block] = field(default_factory=list)
    reco: Any = None
    st: Any = None
    tr: Any = None
    act: str | None = None  # activity (topic_type)
    avia: Any = None
    per_num: str | int | None = None


def age_wording(age: int) -> str:
    """Return age-describing phrase in Russian for age as integer"""
    # TODO partially doubles age_writer()

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


def check_word_by_natasha(string_to_check: str, direction: str) -> bool:
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
            # TODO never called with 'loc', only 'per'
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
