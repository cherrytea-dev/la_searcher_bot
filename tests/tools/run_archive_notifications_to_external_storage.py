from archive_to_bigquery import main
from tests.common import get_event_with_data, setup_logging_to_console

if __name__ == '__main__':
    setup_logging_to_console()
    event = get_event_with_data('foo')
    main.main(event, '')
