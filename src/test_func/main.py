import json
from pathlib import Path
from .some_package.some_utils import get_response
# import psycopg2

# from _dependencies.commons import AppConfig, get_app_config, setup_google_logging

# setup_google_logging()


def handler(event, context):
    # config = get_app_config()
    # recreate_db(config=config)

    return {
        'statusCode': 200,
        # 'body': 'func deployed',
        'body': get_response(),
    }
