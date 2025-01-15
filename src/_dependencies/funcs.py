import os
import urllib.request
from functools import lru_cache

import google.cloud.logging
from google.cloud import secretmanager


@lru_cache
def get_secret_manager_client() -> secretmanager.SecretManagerServiceClient:
    return secretmanager.SecretManagerServiceClient()


@lru_cache
def get_project_id():
    url = 'http://metadata.google.internal/computeMetadata/v1/project/project-id'
    req = urllib.request.Request(url)
    req.add_header('Metadata-Flavor', 'Google')
    project_id = urllib.request.urlopen(req).read().decode()
    return project_id


@lru_cache  # TODO maybe cachetools/timed_lru_cache?
def get_secrets(secret_request):
    """Get GCP secret"""

    name = f'projects/{get_project_id()}/secrets/{secret_request}/versions/latest'
    response = get_secret_manager_client().access_secret_version(name=name)

    return response.payload.data.decode('UTF-8')


def setup_google_logging():
    logging_disabled = os.getenv('GOOGLE_LOGGING_DISABLED', False)
    if logging_disabled:
        # TODO pydantic-settings or improve parsing here.
        return

    log_client = google.cloud.logging.Client()
    log_client.setup_logging()
