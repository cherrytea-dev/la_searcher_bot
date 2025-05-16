import logging

from _dependencies.commons import setup_google_logging
from _dependencies.pubsub import ManageUserAction, ManageUsersData, process_pubsub_message
from _dependencies.users_management import save_default_notif_settings, save_new_user, save_updated_status_for_user

setup_google_logging()


def main(event: dict[str, bytes], context: str) -> str:  # noqa
    """main function"""

    try:
        received_dict_raw = process_pubsub_message(event)
        received_dict = ManageUsersData.model_validate(received_dict_raw)
        action = received_dict.action

        curr_user_id = received_dict.info.user
        # save in table user_statuses_history and table users (for non-new users)
        save_updated_status_for_user(action, curr_user_id, received_dict.info.username, received_dict.time)

    except Exception as e:
        logging.exception('User management script failed')

    return 'ok'
