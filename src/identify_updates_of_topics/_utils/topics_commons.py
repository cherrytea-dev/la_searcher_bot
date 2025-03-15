from dataclasses import dataclass
from datetime import datetime
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
    topic_id: int
    folder_id: int
    topic_type_id: TopicType
    topic_type: str
    parsed_time: datetime
    status: str
    title: str
    # link: Any = None
    start_time: datetime
    num_of_replies: int
    name: str
    display_name: str = ''
    age: int | None = None
    searches_table_id: Any = None
    age_max: int | None = None
    age_min: int | None = None
    num_of_persons: int | None = None
    locations: Any = None
    new_status: Any = None
    # full_dict: Any = None


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
