from pathlib import Path

import psycopg2

from tests.common import get_test_config


def recreate_db_schema(script: str):
    config = get_test_config()

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
    pass
    connection.close()


def main():
    config = get_test_config()
    script = Path('tests/tools/db.sql').read_text()
    script = script.replace('<<CLOUD_POSTGRES_USERNAME>>', config.postgres_user)
    recreate_db_schema(script)
    print(f'test database "{config.postgres_db}" recreated')


if __name__ == '__main__':
    main()
