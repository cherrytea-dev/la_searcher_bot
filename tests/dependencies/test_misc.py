from unittest.mock import AsyncMock, Mock, patch

from _dependencies import misc
from tests.common import get_test_config


def test_notify_admin(patch_pubsub_client, bot_mock_send_message: AsyncMock):
    data = 'some message'

    misc.notify_admin(data)
    bot_mock_send_message.assert_called_once_with(chat_id=get_test_config().my_telegram_id, text=data)


def test_make_api_call():
    # TODO mock requests
    misc.make_api_call('test', {'a: 1'})


# TODO remove after refactored

# NO SMOKE TEST api_get_active_searches.main.clean_up_content
# NO SMOKE TEST api_get_active_searches.main.evaluate_city_locations
# NO SMOKE TEST api_get_active_searches.main.time_counter_since_search_start
# NO SMOKE TEST check_topics_by_upd_time.main.notify_admin
# NO SMOKE TEST api_get_active_searches.time_counter_since_search_start.clean_up_content
# NO SMOKE TEST communicate.main.time_counter_since_search_start
# NO SMOKE TEST connect_to_forum.main.get_user_id
# NO SMOKE TEST identify_updates_of_topics.main.process_pubsub_message
# NO SMOKE TEST identify_updates_of_first_posts.main.process_pubsub_message
# NO SMOKE TEST identify_updates_of_first_posts.main.clean_up_content
# NO SMOKE TEST user_provide_info.main.clean_up_content
# NO SMOKE TEST user_provide_info.main.evaluate_city_locations
# NO SMOKE TEST user_provide_info.main.time_counter_since_search_start
