import json
from pathlib import Path

import psycopg2

from _dependencies.commons import AppConfig, get_app_config, setup_google_logging

setup_google_logging()


def handler(event, context):
    config = get_app_config()
    # recreate_db(config=config)

    return {
        'statusCode': 200,
        # 'body': 'func deployed',
        'body': 'hello 123',
    }


def main(event, context):
    config = get_app_config()
    # recreate_db(config=config)

    return {
        'statusCode': 200,
        # 'body': 'func deployed',
        'body': 'hello from main',
    }
