from unittest.mock import Mock

import pytest

from communicate import main


def test_main_mock():
    # just to run imports and calculate code coverage
    main.main(Mock())
