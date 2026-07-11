"""Data models for send_notifications."""

import datetime
from dataclasses import dataclass, field


@dataclass
class TimeAnalytics:
    script_start_time: datetime.datetime = field(default_factory=datetime.datetime.now)
    notif_times: list[float] = field(default_factory=list)
    delays: list[float] = field(default_factory=list)
    parsed_times: list[float] = field(default_factory=list)
