"""A tiny cron matcher — no third-party dependency.

The single-container scheduler needs the three classic five-field expressions from
``terraform/_func_cron_trigger.tf``. Pulling in a scheduling library for that would add a
dependency to a container that has to fit into 1 CPU / 1 GB, so the matcher is local:

    ┌───────────── minute (0-59)
    │ ┌─────────── hour (0-23)
    │ │ ┌───────── day of month (1-31)
    │ │ │ ┌─────── month (1-12)
    │ │ │ │ ┌───── day of week (0-7, both 0 and 7 mean Sunday)
    │ │ │ │ │
    * * * * *

Each field accepts ``*``/``?``, a number, a range (``a-b``), a step (``*/n``, ``a-b/n``) and
comma-separated lists. Standard cron semantics for day-of-month/day-of-week: when both are
restricted, a moment matches if **either** of them matches.
"""

from __future__ import annotations

import datetime

_FIELD_COUNT = 5
_MINUTES_IN_DAY = 24 * 60
#: How far :meth:`CronExpression.next_after` looks for the next matching minute before giving up.
_MAX_SEARCH_MINUTES = 366 * _MINUTES_IN_DAY

_RANGES: tuple[tuple[int, int], ...] = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


class CronParseError(ValueError):
    """Raised when an expression cannot be understood."""


def _parse_field(field: str, low: int, high: int) -> frozenset[int]:
    values: set[int] = set()
    for part in field.split(','):
        part = part.strip()
        if not part:
            raise CronParseError(f'empty element in field {field!r}')

        step = 1
        if '/' in part:
            part, _, step_raw = part.partition('/')
            if not step_raw.isdigit() or int(step_raw) < 1:
                raise CronParseError(f'bad step in {field!r}')
            step = int(step_raw)

        if part in {'*', '?'}:
            start, end = low, high
        elif '-' in part:
            start_raw, _, end_raw = part.partition('-')
            if not start_raw.isdigit() or not end_raw.isdigit():
                raise CronParseError(f'bad range in {field!r}')
            start, end = int(start_raw), int(end_raw)
        elif part.isdigit():
            start = end = int(part)
        else:
            raise CronParseError(f'bad element {part!r} in field {field!r}')

        if not (low <= start <= high and low <= end <= high) or start > end:
            raise CronParseError(f'value out of range in field {field!r}: {part!r}')

        values.update(range(start, end + 1, step))

    return frozenset(values)


class CronExpression:
    """A parsed five-field cron expression."""

    def __init__(self, expression: str) -> None:
        fields = expression.split()
        if len(fields) != _FIELD_COUNT:
            raise CronParseError(f'expected {_FIELD_COUNT} fields, got {len(fields)}: {expression!r}')

        self.expression = ' '.join(fields)
        parsed = [_parse_field(field, low, high) for field, (low, high) in zip(fields, _RANGES, strict=True)]
        self.minutes, self.hours, self.days, self.months, self.weekdays = parsed

        # 7 and 0 are the same day (Sunday).
        weekdays = set(self.weekdays)
        if 7 in weekdays:
            weekdays.add(0)
        self._weekdays: frozenset[int] = frozenset(weekdays)

        self._day_restricted = fields[2] not in {'*', '?'}
        self._weekday_restricted = fields[4] not in {'*', '?'}

    def matches(self, moment: datetime.datetime) -> bool:
        """Does ``moment`` (any timezone) fall on this schedule?"""
        if moment.minute not in self.minutes or moment.hour not in self.hours or moment.month not in self.months:
            return False

        # cron weekday numbering is 0 = Sunday … 6 = Saturday, while Python's ``weekday()`` is
        # 0 = Monday … 6 = Sunday — hence the shift.
        cron_weekday = (moment.weekday() + 1) % 7
        day_match = moment.day in self.days
        weekday_match = cron_weekday in self._weekdays

        if self._day_restricted and self._weekday_restricted:
            return day_match or weekday_match
        if self._day_restricted:
            return day_match
        if self._weekday_restricted:
            return weekday_match
        return True

    def next_after(self, moment: datetime.datetime) -> datetime.datetime:
        """The first matching minute strictly after ``moment`` (seconds are dropped)."""
        candidate = moment.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
        for _ in range(_MAX_SEARCH_MINUTES):
            if self.matches(candidate):
                return candidate
            candidate += datetime.timedelta(minutes=1)
        raise CronParseError(f'no match for {self.expression!r} within a year after {moment.isoformat()}')
