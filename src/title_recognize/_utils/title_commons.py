from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pymorphy3 import MorphAnalyzer


class BlockType(str, Enum):
    AVIA = 'AVIA'
    TR = 'TR'  # training
    ST = 'ST'  # status
    ACT = 'ACT'  # activity?


class PatternType(str, Enum):
    LOC_BLOCK = 'LOC_BLOCK'
    PER_AGE_W_WORDS = 'PER_AGE_W_WORDS'
    PER_AGE_WO_WORDS = 'PER_AGE_WO_WORDS'
    PER_WITH_PLUS_SIGN = 'PER_WITH_PLUS_SIGN'
    PER_HUMAN_BEING = 'PER_HUMAN_BEING'
    PER_FIO = 'PER_FIO'
    PER_BY_LAST_NUM = 'PER_BY_LAST_NUM'


@dataclass
class PersonGroup:
    name: str
    num_of_per: int
    display_name: str = ''
    type_: Any = None
    age: int | None = None
    age_min: int | None = None
    age_max: int | None = None
    age_wording: str | None = None


@dataclass
class PersonGroupSummary:
    name: str
    block_num: int
    age: int | list[int]
    age_wording: str | None
    display_name: str | None = None


@dataclass
class Block:
    init: str  # initial text, prettified
    reco: str | None = None
    type: BlockType | str | None = None
    done: bool = False
    activity: str | None = None

    def is_person(self) -> bool:
        return bool(self.type and self.type.startswith('P'))

    def is_location(self) -> bool:
        return bool(self.type and self.type.startswith('L'))


@dataclass
class TitleRecognition:
    _initial_text: str  # just save source string
    _pretty: str
    blocks: list[Block] = field(default_factory=list)
    groups: list[Block] = field(default_factory=list)
    person_groups: list[PersonGroup] = field(default_factory=list)  # from "groups"
    person_groups_summary: PersonGroupSummary | None = None

    st: str | None = None  # status
    act: str | None = None  # activity
    per_num: str | int | None = None  # count of persons

    @property
    def is_training(self) -> bool:
        return any(True for block in self.blocks if block.type == BlockType.TR)

    @property
    def is_avia(self) -> bool:
        return any(True for block in self.blocks if block.type == BlockType.AVIA)


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


_NAME_GRAMMEMES = frozenset({'Name', 'Surn', 'Patr', 'Init'})
# pymorphy3 `score` is the relative frequency of a reading in the dictionary. Below 5 % only
# noise lives: the particle `ли`, the preposition `по` and adjectives like `Московская` all have
# a "surname" reading with score <= 0.038.
_MIN_NAME_READING_SCORE = 0.05
_WORD_RE = re.compile(r'[А-Яа-яЁё][-А-Яа-яЁё]{1,}')
_INITIALS_RE = re.compile(r'\b[А-ЯЁ]\.(?:\s*[А-ЯЁ]\.)?')
_STATUS_MARKERS_RE = re.compile(
    r'пропал|пропавш|ищем|поиск|найден|найд|жив|жива|живы|погиб|стоп|розыск|потерял|бюро|мчс',
    re.IGNORECASE,
)


@lru_cache
def _get_morph() -> MorphAnalyzer:
    # pymorphy3 is imported lazily on purpose: the package ships ~16 MB of dictionaries and is
    # needed only here, while this check fires for less than 2 % of titles (measured on 101 613
    # real titles: 1.8 %). Do not move this import back to module level.
    from pymorphy3 import MorphAnalyzer

    return MorphAnalyzer()


def _has_name_reading(word: str) -> bool:
    return any(_NAME_GRAMMEMES & set(parse.tag.grammemes) for parse in _get_morph().parse(word))


def check_word_by_pymorphy(string_to_check: str, direction: str) -> bool:
    """Defines whether the last word of the string is a person, with the help of pymorphy3.

    Replaces the former Natasha NER check: the dictionary is ~17 MB instead of ~123 MB (no numpy,
    no models), and only the last word of the string is analysed. For 'per' the function answers
    "the string ends with a name" — same question Natasha was asked.

    Two traps of the naive "any dictionary reading is a name" check are closed explicitly, both
    used to give phantom persons:

    * readings rarer than 5 % are dropped (`score < 0.05`) — that is where the phantoms live:
      the particle `ли` and the adjective `Московская` have a "surname" reading with score 0.038,
      the preposition `по` — 0.000. Real, just rare, surnames stay above the line
      (`Дергалев` 0.078, `Сдвижкова` 0.153);
    * toponyms that are read as a city more often than as a surname (`Киров`: city 0.50 vs
      surname 0.25) — accepted only when the string carries support: another name word, initials
      like `Б. В.` or a status marker (`пропал`, `найден`, `жив`, `стоп`).

    Measured against Natasha on the 1 794 real titles where the check is called at all: 368
    differences — 88 phantom "searches" disappear, 119 persons are found, 64 person counters are
    lost (mostly garbage), 0 new phantoms. The naive "any reading" version instead produces 2 new
    phantoms (`Выставка "Не по-детски" Киров`, `Якутский обычай - поможет ли?`), the "most
    frequent reading only" version misses 10 persons that do exist.
    """
    if direction != 'per':
        # The 'loc' direction was dead code under Natasha (see git history) and is not supported.
        return False

    words = _WORD_RE.findall(string_to_check)
    if not words:
        return False

    parses = _get_morph().parse(words[-1])
    top_grammemes = set(parses[0].tag.grammemes)
    if _NAME_GRAMMEMES & top_grammemes:
        return True

    name_reading = next(
        (parse for parse in parses if _NAME_GRAMMEMES & set(parse.tag.grammemes)),
        None,
    )
    if name_reading is None or name_reading.score < _MIN_NAME_READING_SCORE:
        return False

    if 'Geox' in top_grammemes and name_reading.score < 0.5:
        has_support = (
            _INITIALS_RE.search(string_to_check) is not None
            or _STATUS_MARKERS_RE.search(string_to_check) is not None
            or any(_has_name_reading(word) for word in words[:-1])
        )
        if not has_support:
            return False

    return True
