from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from requests import Session

from _dependencies.commons import ChangeType, TopicType


@lru_cache
def get_requests_session() -> Session:
    return Session()


# to be reused by different functions
block_of_profile_rough_code = None


@dataclass
class ChangeLogLine:
    parsed_time: Any = None
    topic_id: Any = None
    changed_field: Any = None  # maybe obsolete too
    new_value: Any = None
    parameters: Any = None  # obsolete
    change_type: ChangeType = None


@dataclass
class SearchSummary:
    topic_type: Any = None
    topic_type_id: Any = None
    topic_id: Any = None
    parsed_time: Any = None
    status: Any = None
    title: Any = None
    link: Any = None
    start_time: Any = None
    num_of_replies: Any = None
    name: Any = None
    display_name: Any = None
    age: Any = None
    searches_table_id: Any = None
    folder_id: Any = None
    age_max: Any = None
    age_min: Any = None
    num_of_persons: Any = None
    locations: Any = None
    new_status: Any = None
    full_dict: Any = None
