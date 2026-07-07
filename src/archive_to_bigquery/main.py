"""move data from Cloud SQL to S3 bucket for long-term storage & analysis"""

import csv
import io
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import boto3
import sqlalchemy
from sqlalchemy import text

from _dependencies.common.commons import get_app_config, setup_logging
from _dependencies.common.db_client import DBClientBase
from _dependencies.common.pubsub import Ctx

setup_logging(__package__)


DAYS_AGO_TO_START = 40  # temporarily increase
DAYS_AGO_TO_FINISH = 1  # at least 1 day ago to avoid timezone problems
BATCH_SIZE = 1000


class DBClient(DBClientBase):
    """DB client for archive_to_bigquery."""

    def delete_exported_records(self, date_from: date, date_to: date) -> None:
        stmt = sqlalchemy.text("""
            DELETE FROM notif_by_user__history
            WHERE created >= :date_from AND created < :date_to
        """)
        with self.connect() as conn:
            conn.execute(stmt, dict(date_from=date_from, date_to=date_to))


@dataclass
class Archiver:
    """
    Archivation algorithm:
    - Stream all records from table notif_by_user__history by one day into
      a zip-compressed BytesIO buffer (no temp files).
    - Upload the compressed buffer directly to s3.
    - Delete unloaded records.
    """

    archive_date: date
    db: DBClient
    s3_client: Any
    s3_prefix: str = 'notif_by_user_archive'  # name of folder inside s3 bucket

    def run(self) -> None:
        data = self._unload_records_to_csv_zip()
        if data:
            self._move_to_s3(data)
            self._delete_old_records()

    @property
    def _unload_file_name(self) -> str:
        return f'notifications-archive-{self.archive_date.isoformat()}.csv.zip'

    @property
    def _csv_entry_name(self) -> str:
        return f'notifications-archive-{self.archive_date.isoformat()}.csv'

    @property
    def _date_from(self) -> date:
        return self.archive_date

    @property
    def _date_to(self) -> date:
        return self.archive_date + timedelta(days=1)

    def _unload_records_to_csv_zip(self) -> io.BytesIO | None:
        """Stream records into a zip-compressed BytesIO buffer; returns None if no records."""

        paginated_query = text("""
            SELECT * FROM notif_by_user__history
            WHERE
                created >= :date_from
                AND created < :date_to
                AND (:last_message_id IS NULL OR message_id > :last_message_id)
            ORDER BY message_id
            LIMIT :limit
        """)

        params = {
            'date_from': self._date_from,
            'date_to': self._date_to,
            'limit': BATCH_SIZE,
        }

        total_count = 0
        last_message_id: int | None = None
        buf = io.BytesIO()

        with self.db.connect() as conn:
            with ZipFile(buf, 'w', compression=ZIP_DEFLATED, compresslevel=9) as zf:
                with zf.open(self._csv_entry_name, 'w') as csv_entry:
                    with io.TextIOWrapper(csv_entry, encoding='utf-8') as text_wrapper:
                        writer = None

                        while True:
                            result = conn.execute(
                                paginated_query,
                                params | {'last_message_id': last_message_id},
                            )
                            rows = result.fetchall()

                            if not rows:
                                break

                            if writer is None:
                                columns = list(result.keys())
                                writer = csv.writer(text_wrapper)
                                writer.writerow(columns)

                            writer.writerows(rows)
                            total_count += len(rows)
                            last_message_id = rows[-1].message_id

        if total_count == 0:
            buf.close()
            return None

        logging.info(f'records to archive: {total_count}')
        buf.seek(0)
        return buf

    def _move_to_s3(self, data: io.BytesIO) -> None:
        result_file_name = self._unload_file_name

        logging.info(f'Uploading to s3: {result_file_name}')

        self.s3_client.upload_fileobj(
            data,
            get_app_config().aws_backup_bucket_name,
            f'{self.s3_prefix}/{result_file_name}',
        )

        logging.info('Archive saved to s3 bucket')

    def _delete_old_records(self) -> None:
        logging.info('Deleting old records')
        self.db.delete_exported_records(self._date_from, self._date_to)
        logging.info('Old records deleted')


def main(event: dict, context: Ctx) -> None:
    """main function"""

    logging.info('Start archivation of old notifications')

    session = boto3.session.Session()
    s3 = session.client(
        service_name='s3',
        endpoint_url='https://storage.yandexcloud.net',
        aws_access_key_id=get_app_config().aws_access_key_id,
        aws_secret_access_key=get_app_config().aws_secret_access_key,
    )

    db = DBClient()

    for i in range(DAYS_AGO_TO_START)[:DAYS_AGO_TO_FINISH:-1]:
        archive_date = date.today() - timedelta(days=i)
        logging.info(f'Processing date: {archive_date}')

        archiver = Archiver(archive_date=archive_date, db=db, s3_client=s3)
        archiver.run()

    logging.info('Done')

    # TODO clean function_registry table. And maybe stat_api_usage_actual_searches too
