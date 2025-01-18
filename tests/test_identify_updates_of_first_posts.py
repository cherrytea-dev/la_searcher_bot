import pytest

from identify_updates_of_first_posts import main
from tests.common import get_event_with_data


def test_main():
    with pytest.raises(ValueError):
        main.main(get_event_with_data('foo'), 'context')
    assert True
