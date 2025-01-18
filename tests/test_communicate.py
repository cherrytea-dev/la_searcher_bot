from unittest.mock import MagicMock

from communicate import main


def test_update_and_download_list_of_regions():
    main.main(MagicMock())
