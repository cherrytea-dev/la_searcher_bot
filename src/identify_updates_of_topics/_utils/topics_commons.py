from dataclasses import dataclass
from typing import Any


@dataclass
class ChangeLogLine:
    parsed_time: Any = None
    topic_id: Any = None
    changed_field: Any = None
    new_value: Any = None
    parameters: Any = None
    change_type: Any = None


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
