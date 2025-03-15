from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from polyfactory.factories import DataclassFactory

from _dependencies.commons import sqlalchemy_get_pool
from identify_updates_of_topics._utils.database import DBClient
from identify_updates_of_topics._utils.folder_updater import FolderUpdater
from identify_updates_of_topics._utils.forum import ForumClient
from identify_updates_of_topics._utils.topics_commons import (
    ChangeLogLine,
    ForumCommentItem,
    ForumSearchItem,
    SearchSummary,
)


class SearchSummaryFactory(DataclassFactory[SearchSummary]):
    pass


@pytest.fixture(scope='session')
# @pytest.fixture
def db_client(patch_app_config) -> DBClient:
    pool = sqlalchemy_get_pool(10, 10)
    return DBClient(pool)


class TestDBClient:
    def _test_parse_one_folder(self, db_client: DBClient):
        with pytest.raises(ValueError):
            with db_client._db.begin() as tr:
                searches = db_client.get_searches()
                for search in searches:
                    db_client.delete_search(search.topic_id)
                    raise ValueError()
        pass

    def test_write_search(self, db_client: DBClient):
        search_summary = SearchSummaryFactory.build()
        db_client.write_search(search_summary)
        searches = db_client.get_searches()
        assert search_summary in searches
