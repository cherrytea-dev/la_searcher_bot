import pytest

from identify_updates_of_first_posts import main
from tests.common import get_event_with_data


def test_main():
    # NO SMOKE TEST identify_updates_of_first_posts.main.main
    # TODO paste some posts in db
    main.main(get_event_with_data('[1,2]'), 'context')
    assert True


def test_compose_diff_message():
    # NO SMOKE TEST identify_updates_of_first_posts.main.compose_diff_message
    current = ['line1', 'line2']
    previous = ['line1', 'line3']
    message, deleted, added = main.compose_diff_message(current, previous)
    assert message == 'Удалено:\n<s>line3\n</s>\nДобавлено:\nline2\n'
    assert deleted == ['line3']
    assert added == ['line2']
