from dataclasses import dataclass
from typing import Any

from _dependencies.commons import ChangeType, TopicType


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
    topic_type_id: TopicType = None
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


@dataclass
class ForumSearchItem:
    title: str
    search_id: int
    replies_count: int
    start_datetime: str


@dataclass
class ForumCommentItem:
    search_num: int
    comment_num: int
    comment_url: str
    comment_author_nickname: str
    comment_author_link: str
    comment_forum_global_id: int
    comment_text: str
    ignore: bool
    inforg_comment_present: bool
