"""move data from Cloud SQL to S3 bucket for long-term storage & analysis"""

import csv
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from tempfile import NamedTemporaryFile
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import boto3
from sqlalchemy import text
from sqlalchemy.engine import Engine

from _dependencies.common.commons import get_app_config, setup_logging, sqlalchemy_get_pool
from _dependencies.common.pubsub import Ctx

setup_logging(__package__)


DAYS_AGO_TO_START = 40  # temporarily increase
DAYS_AGO_TO_FINISH = 1  # at least 1 day ago to avoid timezone problems
BATCH_SIZE = 10_000  # rows per paginated query (keeps memory < 100 MB per iteration)


@dataclass
class Archiver:
    """
    Archivation algorythm:
    - Unload all records from table notif_by_user__history by one day to CSV file.
    - Create zip archive.
    - Move archive to s3 storage.
    - Delete unloaded records.
    """

    archive_date: date
    engine: Engine
    s3_client: Any
    s3_prefix: str = 'notif_by_user_archive'  # name of folder inside s3 bucket

    def run(self) -> None:
        temp_file_name = self._unload_records_to_csv()
        if temp_file_name:
            self._move_to_s3(temp_file_name)
            self._delete_old_records()

    @property
    def _unload_file_name(self) -> str:
        return f'notifications-archive-{self.archive_date.isoformat()}.csv'

    @property
    def _date_from(self) -> date:
        return self.archive_date

    @property
    def _date_to(self) -> date:
        return self.archive_date + timedelta(days=1)

    def _unload_records_to_csv(self) -> str | None:
        """returns None if no records to unload"""

        logging.info('Fetching records to archive in batches')

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
        temp_file_name: str | None = None

        with self.engine.connect() as conn:
            with NamedTemporaryFile('w', delete=False) as f:
                writer = None

                while True:
                    result = conn.execute(paginated_query, params | {'last_message_id': last_message_id})
                    rows = result.fetchall()

                    if not rows:
                        break

                    if writer is None:
                        columns = list(result.keys())
                        writer = csv.writer(f)
                        writer.writerow(columns)

                    writer.writerows(rows)
                    total_count += len(rows)
                    last_message_id = rows[-1].message_id

                temp_file_name = f.name

        if total_count == 0:
            return None

        logging.info(f'records to archive: {total_count}')
        logging.info(f'records unloaded to temp file {temp_file_name}')

        return temp_file_name

    def _move_to_s3(self, temp_file_name: str) -> None:
        result_file_name = self._unload_file_name + '.zip'
        zip_file_name = temp_file_name + '.zip'

        logging.info(f'Creating archive: {result_file_name}')

        with ZipFile(zip_file_name, 'w', compression=ZIP_DEFLATED, compresslevel=9) as zip_file:
            zip_file.write(temp_file_name, self._unload_file_name)

        logging.info(f'Uploading to s3: {result_file_name}')

        self.s3_client.upload_file(
            zip_file_name,
            get_app_config().aws_backup_bucket_name,
            f'{self.s3_prefix}/{result_file_name}',
        )

        logging.info('Archive saved to s3 bucket')

    def _delete_old_records(self) -> None:
        logging.info('Deleting old records')

        with self.engine.begin() as conn:
            delete_query = text("""
                    DELETE FROM notif_by_user__history
                    WHERE 
                        created >= :date_from
                        AND created < :date_to
            """)
            conn.execute(
                delete_query,
                {
                    'date_from': self._date_from,
                    'date_to': self._date_to,
                },
            )

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

    for i in range(DAYS_AGO_TO_START)[:DAYS_AGO_TO_FINISH:-1]:
        archive_date = date.today() - timedelta(days=i)
        logging.info(f'Processing date: {archive_date}')

        archiver = Archiver(archive_date=archive_date, engine=sqlalchemy_get_pool(), s3_client=s3)
        archiver.run()

    logging.info('Done')

    # TODO clean function_registry table. And maybe stat_api_usage_actual_searches too
