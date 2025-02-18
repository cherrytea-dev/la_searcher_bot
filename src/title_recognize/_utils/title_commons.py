from dataclasses import dataclass, field
from typing import Any


@dataclass
class Block:
    block_num: Any = None
    init: Any = None
    reco: Any = None
    type: Any = None
    done: Any = None


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
    per_list: list = field(default_factory=list)
    loc_list: list = field(default_factory=list)


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
