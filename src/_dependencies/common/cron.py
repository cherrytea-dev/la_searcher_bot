"""Cron expressions for the single-container scheduler.

The scheduler (:mod:`app.scheduler`) needs the three five-field expressions that
``terraform/_func_cron_trigger.tf`` used to hand to the Yandex timer triggers. Parsing and
matching them is delegated to ``cronsim`` — pure Python, no dependencies of its own, follows
Debian's cron (including its quirks) and is maintained by the author of Healthchecks.

This module is the only place that knows about that library, and it keeps the project's own
rules on top of it:

* **exactly five fields** (``minute hour day month weekday``). The Quartz-style six-field form
  of terraform (``* * ? * * *``) is rejected instead of being read as "second zero of every
  minute", so that copying an expression from the terraform file fails loudly at startup;
* ``?`` is accepted as a synonym for ``*``: Yandex wrote its timers with ``?``, and an operator
  copying one of those by hand should not be tripped by the fifth field.

``cronsim.CronSimError`` and the library's ``StopIteration`` ("no match within 50 years") both
surface as :class:`CronParseError`.
"""

from __future__ import annotations

import datetime

from cronsim import CronSim, CronSimError

_FIELD_COUNT = 5

#: Only used to validate an expression in :meth:`CronExpression.__init__`; any fixed date does.
_VALIDATION_EPOCH = datetime.datetime(2000, 1, 1)


class CronParseError(ValueError):
    """Raised when an expression cannot be understood."""


class CronExpression:
    """A parsed five-field cron expression (a thin wrapper around ``cronsim``)."""

    def __init__(self, expression: str) -> None:
        fields = expression.split()
        if len(fields) != _FIELD_COUNT:
            raise CronParseError(f'expected {_FIELD_COUNT} fields, got {len(fields)}: {expression!r}')

        self.expression = ' '.join('*' if field == '?' else field.replace('?', '*') for field in fields)
        try:
            CronSim(self.expression, _VALIDATION_EPOCH)
        except CronSimError as exc:
            raise CronParseError(f'{exc} in {expression!r}') from exc

    def matches(self, moment: datetime.datetime) -> bool:
        """Does ``moment`` (any timezone) fall on this schedule?"""
        moment = moment.replace(second=0, microsecond=0)
        return self.next_after(moment - datetime.timedelta(minutes=1)) == moment

    def next_after(self, moment: datetime.datetime) -> datetime.datetime:
        """The first matching minute strictly after ``moment`` (seconds are dropped)."""
        try:
            return next(iter(CronSim(self.expression, moment)))
        except StopIteration as exc:
            raise CronParseError(
                f'no match for {self.expression!r} within 50 years after {moment.isoformat()}'
            ) from exc
