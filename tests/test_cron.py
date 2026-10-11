"""Unit tests for the local cron matcher (:mod:`_dependencies.common.cron`)."""

from __future__ import annotations

import datetime

import pytest

from _dependencies.common.cron import CronExpression, CronParseError


def test_every_minute_matches_any_moment() -> None:
    expression = CronExpression('* * * * *')

    assert expression.matches(datetime.datetime(2026, 10, 11, 0, 0))
    assert expression.matches(datetime.datetime(2026, 10, 11, 23, 59))


def test_daily_expression_matches_only_that_minute() -> None:
    expression = CronExpression('13 11 * * *')

    assert expression.matches(datetime.datetime(2026, 10, 11, 11, 13))
    assert not expression.matches(datetime.datetime(2026, 10, 11, 11, 14))
    assert not expression.matches(datetime.datetime(2026, 10, 11, 12, 13))


def test_hourly_expression() -> None:
    expression = CronExpression('0 * * * *')

    assert expression.matches(datetime.datetime(2026, 10, 11, 7, 0))
    assert not expression.matches(datetime.datetime(2026, 10, 11, 7, 1))


def test_steps_lists_and_ranges() -> None:
    assert CronExpression('*/15 * * * *').matches(datetime.datetime(2026, 10, 11, 10, 45))
    assert not CronExpression('*/15 * * * *').matches(datetime.datetime(2026, 10, 11, 10, 46))
    assert CronExpression('1,2,3 * * * *').matches(datetime.datetime(2026, 10, 11, 10, 2))
    assert CronExpression('10-20 * * * *').matches(datetime.datetime(2026, 10, 11, 10, 20))
    assert not CronExpression('10-20 * * * *').matches(datetime.datetime(2026, 10, 11, 10, 21))


def test_day_of_week_matches_monday() -> None:
    monday = datetime.datetime(2026, 10, 12, 9, 0)
    assert monday.weekday() == 0, 'the fixture date must be a Monday'

    expression = CronExpression('0 9 * * 1')
    assert expression.matches(monday)
    assert not expression.matches(monday + datetime.timedelta(days=1))


def test_sunday_is_both_zero_and_seven() -> None:
    sunday = datetime.datetime(2026, 10, 11, 12, 0)
    assert sunday.weekday() == 6, 'the fixture date must be a Sunday'

    assert CronExpression('0 12 * * 0').matches(sunday)
    assert CronExpression('0 12 * * 7').matches(sunday)


def test_day_of_month_and_weekday_are_ored_when_both_restricted() -> None:
    expression = CronExpression('0 0 1 * 1')
    first_of_month_not_monday = datetime.datetime(2026, 10, 1, 0, 0)
    monday_not_first = datetime.datetime(2026, 10, 12, 0, 0)
    neither = datetime.datetime(2026, 10, 13, 0, 0)

    assert expression.matches(first_of_month_not_monday)
    assert expression.matches(monday_not_first)
    assert not expression.matches(neither)


def test_next_after_steps_to_the_next_matching_minute() -> None:
    every_minute = CronExpression('* * * * *')
    assert every_minute.next_after(datetime.datetime(2026, 10, 11, 10, 30, 45)) == datetime.datetime(
        2026, 10, 11, 10, 31
    )

    hourly = CronExpression('0 * * * *')
    assert hourly.next_after(datetime.datetime(2026, 10, 11, 10, 30)) == datetime.datetime(2026, 10, 11, 11, 0)

    daily = CronExpression('13 11 * * *')
    assert daily.next_after(datetime.datetime(2026, 10, 11, 12, 0)) == datetime.datetime(2026, 10, 12, 11, 13)


def test_question_mark_is_a_wildcard() -> None:
    # Yandex Cloud wrote its timers as Quartz-style ``* * ? * * *``.
    assert CronExpression('* * ? * *').matches(datetime.datetime(2026, 10, 11, 10, 30))


@pytest.mark.parametrize(
    'expression',
    ['', '* * * *', '* * * * * *', '60 * * * *', '* 24 * * *', '* * 32 * *', '* * * 13 *', 'a * * * *', '*/0 * * * *'],
)
def test_bad_expressions_are_rejected(expression: str) -> None:
    with pytest.raises(CronParseError):
        CronExpression(expression)
