import csv
import io
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from zipfile import ZipFile

import pytest
from sqlalchemy.orm.session import Session

from archive_to_bigquery.main import Archiver, DBClient, main
from tests.common import find_model
from tests.factories.db_factories import NotifByUserHistory, NotifByUserHistoryFactory, faker


class TestArchiveNotifications:
    @pytest.fixture
    def archiver(self, connection_pool) -> Archiver:
        return Archiver(
            archive_date=faker.date_object(),
            db=DBClient(db=connection_pool),
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

    def test_records_unloaded(self, archiver: Archiver, session: Session):
        """unload old records — returns zipped BytesIO, then deletes"""
        records_count = 3
        first_notif, *others = NotifByUserHistoryFactory.create_batch_sync(
            records_count,
            created=archiver.archive_date,
        )
        data = archiver._unload_records_to_csv_zip()

        assert data is not None
        assert isinstance(data, io.BytesIO)

        assert find_model(session, NotifByUserHistory, message_id=first_notif.message_id)
        archiver._delete_old_records()
        assert not find_model(session, NotifByUserHistory, message_id=first_notif.message_id)

    def test_no_records(self, archiver: Archiver):
        """records are not enough old to unload"""

        NotifByUserHistoryFactory.create_sync(created=archiver.archive_date - timedelta(days=1))
        data = archiver._unload_records_to_csv_zip()
        assert data is None

    def test_backup_file_upload(self, archiver: Archiver):
        """upload zipped BytesIO to s3 storage"""

        buf = io.BytesIO(b'fake,compressed,data')
        archiver._move_to_s3(buf)
        archiver.s3_client.upload_fileobj.assert_called_once()

    @patch('archive_to_bigquery.main.BATCH_SIZE', 2)
    def test_batch_unload(self, archiver: Archiver):
        """unload more records than batch size — verifies keyset pagination"""

        batch_override = 2
        records_count = batch_override * 2 + 1  # 5 records, 3 batches

        NotifByUserHistoryFactory.create_batch_sync(records_count, created=archiver.archive_date)

        data = archiver._unload_records_to_csv_zip()

        assert data is not None

        with ZipFile(data) as zf:
            csv_entry = archiver._csv_entry_name
            assert csv_entry in zf.namelist()
            with zf.open(csv_entry) as csv_file:
                reader = csv.reader(io.TextIOWrapper(csv_file, encoding='utf-8'))
                rows = list(reader)

        assert len(rows) == 1 + records_count  # header + data
