from pathlib import Path

import click
import psycopg2

from _dependencies.common.commons import AppConfig
from tests.common import get_dotenv_config, get_test_config


def _get_connection(config: AppConfig) -> psycopg2.extensions.connection:
    return psycopg2.connect(
        dbname=config.postgres_db,
        user=config.postgres_user,
        password=config.postgres_password,
        port=config.postgres_port,
        host=config.postgres_host,
    )


def load_initial_data(config: AppConfig) -> None:
    """Execute initial data scripts (geo divisions, folders, regions)."""
    connection = _get_connection(config)
    connection.autocommit = True
    with connection.cursor() as cursor:
        initial_data_dir = Path('tests/tools/db_initial_data')
        sql_files = sorted(initial_data_dir.glob('*.sql'))
        for sql_file in sql_files:
            script = sql_file.read_text()
            cursor.execute(script)
    connection.close()


def recreate_db(config: AppConfig) -> None:
    script = Path('tests/tools/db.sql').read_text()
    script = script.replace('<<CLOUD_POSTGRES_USERNAME>>', config.postgres_user)

    connection = _get_connection(config)
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute(script)

    connection.close()

    load_initial_data(config)


@click.command()
@click.option('--db', type=click.Choice(['TEST', 'PROD']), required=True, help='Choose db type')
@click.option(
    '--init-data-only', is_flag=True, default=False, help='Only load initial data without recreating the DB schema'
)
def main(db: str, init_data_only: bool) -> None:
    """Recreate test/production database or load initial data only."""
    if db == 'TEST':
        config = get_test_config()
        if init_data_only:
            load_initial_data(config)
            click.echo(f'initial data loaded into test database "{config.postgres_db}"')
        else:
            recreate_db(config)
            click.echo(f'test database "{config.postgres_db}" recreated')

    elif db == 'PROD':
        config = get_dotenv_config()
        if init_data_only:
            load_initial_data(config)
            click.echo(f'initial data loaded into PROD database "{config.postgres_db}"')
        else:
            click.confirm('Are you sure you want to recreate PRODUCTION database?', abort=True)
            recreate_db(config)
            click.echo(f'PROD database "{config.postgres_db}" recreated')


if __name__ == '__main__':
    main()
