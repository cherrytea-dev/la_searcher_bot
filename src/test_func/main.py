import json
from pathlib import Path

import psycopg2

from _dependencies.commons import AppConfig, get_app_config


def recreate_db(config: AppConfig) -> None:
    script = Path('db.sql').read_text()
    script = script.replace('<<CLOUD_POSTGRES_USERNAME>>', config.postgres_user)

    connection = psycopg2.connect(
        dbname=config.postgres_db,
        user=config.postgres_user,
        password=config.postgres_password,
        port=config.postgres_port,
        host=config.postgres_host,
    )

    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute(script)

    connection.close()


def handler(event, context):
    # config = get_app_config()
    # recreate_db(config=config)

    return {
        'statusCode': 200,
        'body': 'func deployed',
        # 'body': 'database recreated',
    }
