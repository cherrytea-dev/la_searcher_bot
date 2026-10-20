"""The cron jobs of the single container: ``archive_to_bigquery`` can be switched off.

The daily archiving uploads to Object Storage (S3). When the bucket is unavailable the job is
left out of the scheduler entirely, so it does not fail on every run (``ARCHIVE_TO_BIGQUERY_ENABLED``).
"""

from dotenv import load_dotenv

from app.scheduler import default_jobs
from tests.common import AppTestConfig

# ``AppTestConfig`` reads the process environment, and ``.env.test`` is only loaded by the
# session fixture once something actually asks for the app config — load it here so the
# required POSTGRES_* fields are present.
load_dotenv('.env.test', override=True)


def _job_names(config: AppTestConfig) -> list[str]:
    return [job.name for job in default_jobs(config)]


def test_archive_to_bigquery_is_scheduled_by_default():
    assert _job_names(AppTestConfig()) == ['check_first_posts', 'archive_to_bigquery', 'archive_notifications']


def test_archive_to_bigquery_can_be_switched_off():
    assert _job_names(AppTestConfig(archive_to_bigquery_enabled=False)) == [
        'check_first_posts',
        'archive_notifications',
    ]
