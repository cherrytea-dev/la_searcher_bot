"""Data models for send_notifications."""

import datetime
from dataclasses import dataclass, field

from _dependencies.common.message_params import (
    MessageParams,
)


@dataclass
class TimeAnalytics:
    script_start_time: datetime.datetime = field(default_factory=datetime.datetime.now)
    notif_times: list[float] = field(default_factory=list)
    delays: list[float] = field(default_factory=list)
    parsed_times: list[float] = field(default_factory=list)


# Re-export the unified MessageParams for backward compatibility
# until all consumers are migrated to _dependencies.common.message_params.
__all__ = ['TimeAnalytics', 'MessageParams']
