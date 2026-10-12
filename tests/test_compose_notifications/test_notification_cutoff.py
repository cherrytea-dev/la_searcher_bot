"""Notification cutoff for temporary deployments (``NOTIFY_SEARCHES_SINCE``).

The cutoff is an absolute lower bound on a search's start time: changes of searches started
before it are composed but never sent. It has to cover *every* folder — including the Samara
folders that otherwise bypass the 60-day window (see ``_set_ignorance_mark``).
"""

import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv
from pydantic import ValidationError

from _dependencies.common.commons import ChangeType
from compose_notifications._utils.commons import LineInChangeLog
from compose_notifications._utils.log_record_composer import LogRecordComposer
from tests.common import AppTestConfig
from tests.test_compose_notifications.factories import LineInChangeLogFactory

# ``AppTestConfig`` reads the process environment, and ``.env.test`` is only loaded by the
# session fixture once something asks for the app config — load it here so the required
# POSTGRES_* fields are present.
load_dotenv('.env.test', override=True)

# Derived from now: the code under test compares against the real ``datetime.now()`` in the
# 60-day window check, so a hardcoded date would turn these tests into time bombs.
CUTOFF = datetime.datetime.now() - datetime.timedelta(days=4)
SAMARA_FOLDER = 333  # one of FORUM_FOLDERS_OF_SAMARA


def _config(cutoff: datetime.datetime | None) -> SimpleNamespace:
    return SimpleNamespace(notify_searches_since=cutoff)


def _set_ignore_mark(line: LineInChangeLog, cutoff: datetime.datetime | None) -> None:
    composer = LogRecordComposer(MagicMock())
    with patch('compose_notifications._utils.log_record_composer.get_app_config', return_value=_config(cutoff)):
        composer._set_ignorance_mark(line)


def _line(start_time: datetime.datetime | None, folder: int = 0) -> LineInChangeLog:
    # topic_status_change is outside both the "not Ищем" and the 2-day rules, so the line is
    # ignored (or not) purely because of the window / the cutoff.
    return LineInChangeLogFactory.build(
        change_type=ChangeType.topic_status_change,
        status='Ищем',
        start_time=start_time,
        forum_folder=folder,
        ignore=False,
    )


def test_search_started_before_the_cutoff_is_ignored():
    line = _line(start_time=CUTOFF - datetime.timedelta(days=30))

    _set_ignore_mark(line, CUTOFF)

    assert line.ignore is True


def test_search_started_after_the_cutoff_is_kept():
    line = _line(start_time=CUTOFF + datetime.timedelta(days=1))

    _set_ignore_mark(line, CUTOFF)

    assert line.ignore is False


def test_search_without_start_time_is_ignored_with_a_cutoff():
    # searches.search_start_time is nullable; failing open here would deliver exactly the
    # backlog the cutoff exists to suppress.
    line = _line(start_time=None)

    _set_ignore_mark(line, CUTOFF)

    assert line.ignore is True


def test_cutoff_covers_samara_folders_that_bypass_the_window():
    old = CUTOFF - datetime.timedelta(days=400)
    line = _line(start_time=old, folder=SAMARA_FOLDER)

    # without a cutoff the Samara folder is exempt from the 60-day window...
    _set_ignore_mark(line, None)
    assert line.ignore is False

    # ...with the cutoff it is not.
    _set_ignore_mark(line, CUTOFF)
    assert line.ignore is True


def test_no_cutoff_keeps_the_previous_behaviour():
    line = _line(start_time=CUTOFF - datetime.timedelta(days=1))

    _set_ignore_mark(line, None)

    assert line.ignore is False


def test_tz_aware_cutoff_is_rejected_at_config_load():
    # An aware value would raise on every comparison, and that error is swallowed upstream —
    # the cutoff would silently stop filtering.
    with pytest.raises(ValidationError):
        AppTestConfig(notify_searches_since=datetime.datetime(2026, 10, 8, tzinfo=datetime.timezone.utc))
