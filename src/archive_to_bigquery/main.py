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

from _dependencies.commons import get_app_config, sqlalchemy_get_pool
from _dependencies.pubsub import Ctx

DAYS_AGO_TO_START = 7
DAYS_AGO_TO_FINISH = 1  # at least 1 day ago to avoid timezone problems


def sql_connect() -> Engine:
    return sqlalchemy_get_pool(5, 5)


@dataclass
class Archiver:
    """
    Archivation algorythm:
    - Unload all records from table notif_by_user__archive by one day to CSV file.
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
        """returns False if no records to unload"""

        logging.info('Fetching records to archive')

        with self.engine.connect() as conn:
            # Use raw SQL to export data to CSV
            query = text("""
                    SELECT * FROM notif_by_user__history
                    WHERE 
                        created >= :date_from
                        AND created < :date_to
            """)

            result = conn.execute(
                query,
                {
                    'date_from': self._date_from,
                    'date_to': self._date_to,
                },
            )

            logging.info(f'records to archive: {result.rowcount}')

            if not result.rowcount:
                return None

            with NamedTemporaryFile('w', delete=False) as f:
                writer = csv.writer(f)
                columns = [desc[0] for desc in result.cursor.description]
                writer.writerow(columns)
                writer.writerows(result)

        logging.info(f'records unloaded to temp file {f.name}')

        return f.name

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

        with self.engine.connect() as conn:
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

        archiver = Archiver(archive_date=archive_date, engine=sql_connect(), s3_client=s3)
        archiver.run()

    logging.info('Done')

    # TODO clean function_registry table. And maybe stat_api_usage_actual_searches too
