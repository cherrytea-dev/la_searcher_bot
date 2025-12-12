from datetime import datetime, timedelta
from tempfile import NamedTemporaryFile
from unittest.mock import Mock, patch

import pytest

from archive_to_bigquery.main import Archiver, main, sql_connect
from tests.factories.db_factories import NotifByUserHistoryFactory, faker


class TestArchiveNotifications:
    @pytest.fixture
    def archiver(self) -> Archiver:
        return Archiver(
            archive_date=faker.date_object(),
            engine=sql_connect(),
            s3_client=Mock(),
        )

    @pytest.mark.skip(reason='real run')
    def test_main_real(self):
        """simply run whole process"""

        NotifByUserHistoryFactory.create_batch_sync(3, created=datetime.now() - timedelta(days=3))
        main('event', 'context')

    @patch('boto3.session')
    def test_main(self, mock_boto3):
        """simply run whole process"""

        NotifByUserHistoryFactory.create_batch_sync(3, created=datetime.now())
        main('event', 'context')

    def test_records_unloaded(self, archiver: Archiver):
        """unload old records"""
        records_count = 3
        NotifByUserHistoryFactory.create_batch_sync(records_count, created=archiver.archive_date)
        unload_file_name = archiver._unload_records_to_csv()

        assert unload_file_name.startswith('/tmp')

        archiver._delete_old_records()

    def test_no_records(self, archiver: Archiver):
        """records are not enough old to unload"""

        NotifByUserHistoryFactory.create_sync(created=archiver.archive_date - timedelta(days=1))
        unload_file_name = archiver._unload_records_to_csv()
        assert unload_file_name is None

    @patch('boto3.session')
    def test_backup_file_upload(self, mock_boto3, archiver: Archiver):
        """upload file to s3 storage"""

        with NamedTemporaryFile(delete=False) as file:
            file.close()
            with patch('boto3.session'):
                archiver._move_to_s3(file.name)
                pass
