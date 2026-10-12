"""Notification cutoff for temporary deployments (``NOTIFY_SEARCHES_SINCE``).

The cutoff is an absolute lower bound on a search's start time: changes of searches started
before it are composed but never sent. It has to cover *every* folder — including the Samara
folders that otherwise bypass the 60-day window (see ``_set_ignorance_mark``).
"""

import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from _dependencies.common.commons import ChangeType
from compose_notifications._utils.commons import LineInChangeLog
from compose_notifications._utils.log_record_composer import LogRecordComposer
from tests.test_compose_notifications.factories import LineInChangeLogFactory

CUTOFF = datetime.datetime(2026, 10, 8)
SAMARA_FOLDER = 333  # one of FORUM_FOLDERS_OF_SAMARA


def _config(cutoff: datetime.datetime | None) -> SimpleNamespace:
    return SimpleNamespace(notify_searches_since=cutoff)


def _set_ignore_mark(line: LineInChangeLog, cutoff: datetime.datetime | None) -> None:
    composer = LogRecordComposer(MagicMock())
    with patch('compose_notifications._utils.log_record_composer.get_app_config', return_value=_config(cutoff)):
        composer._set_ignorance_mark(line)


def _line(start_time: datetime.datetime, folder: int = 0) -> LineInChangeLog:
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
