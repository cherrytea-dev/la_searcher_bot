from argparse import ArgumentParser
from enum import Enum
from pathlib import Path

import psycopg2

from _dependencies.commons import AppConfig
from tests.common import get_dotenv_config, get_test_config


class DBKind(str, Enum):
    TEST = 'TEST'
    PROD = 'PROD'


def recreate_db(config: AppConfig) -> None:
    script = Path('tests/tools/db.sql').read_text()
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


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument(
        '--db', type=DBKind, required=True, choices=[DBKind.TEST.value, DBKind.PROD.value], help='Choose db type'
    )
    args = parser.parse_args()
    db_kind = args.db

    if db_kind == DBKind.TEST:
        config = get_test_config()
        recreate_db(config)
        print(f'test database "{config.postgres_db}" recreated')

    elif db_kind == DBKind.PROD:
        # ask user if he want to recreate production database and erase all data
        config = get_dotenv_config()
        user_choice = input('Are you sure you want to recreate PRODUCTION database? (y/n) ')
        if user_choice.lower() == 'y':
            recreate_db(config)
            print(f'PROD database "{config.postgres_db}" recreated')
