from dataclasses import dataclass, field
from typing import Any


@dataclass
class Search:
    topic_id: int


@dataclass
class PercentGroup:
    n: int
    start_percent: int
    finish_percent: int
    frequency: int
    first_delay: int
    start_num: int = 0
    finish_num: int = 0
    searches: list[Search] = field(default_factory=list)  # searches

    def __str__(self) -> str:
        days = f' or {int(self.frequency // 1440)} day(s)' if self.frequency >= 1440 else ''
        return (
            f'N{self.n: <2}: {self.start_percent}%–{self.finish_percent}%. Updated every {self.frequency} minute(s){days}. '
            f'First delay = {self.first_delay} minutes. nums {self.start_num}-{self.finish_num}. num of searches {len(self.searches)}'
        )
