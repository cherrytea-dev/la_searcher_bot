"""
Tool for search duplicate functions in modules
"""

import importlib
import inspect
from pathlib import Path


def generate_all():
    """
    Generate all smoke testcases
    """

    dir_names = [x.name for x in Path('src').glob('*')]
    dir_names.sort()
    print('')

    cases = dict()
    for dir_name in dir_names:
        if dir_name.startswith('_'):
            continue
        module = importlib.import_module(f'{dir_name}.main')

        _add_cases(module, dir_name, cases)

    cases = {key: value for key, value in cases.items() if len(value) > 1}
    print('-----')
    # print(cases)
    # print("-----")
    for key, value in cases.items():
        print(f'def {key}: {value}')

    # print(cases.keys())
    # print("-----")


def _add_cases(module, module_name: str, cases: dict) -> str:
    """generate test cases for all functions in module"""

    members = inspect.getmembers(module)
    for member_name, member in members:
        if not inspect.isfunction(member):
            continue
        if member.__module__ != module.__name__:
            # don't test imported functions
            continue

        used_modules: list = cases.get(member_name, list())
        used_modules.append(module_name)
        cases[member_name] = used_modules


if __name__ == '__main__':
    generate_all()


"""
{
    'clean_up_content': ['api_get_active_searches', 'identify_updates_of_first_posts', 'user_provide_info'],
    'evaluate_city_locations': ['api_get_active_searches', 'user_provide_info'],
    'main': [
        'api_get_active_searches',
        'archive_notifications',
        'archive_to_bigquery',
        'check_first_posts_for_changes',
        'check_topics_by_upd_time',
        'communicate',
        'compose_notifications',
        'connect_to_forum',
        'identify_updates_of_first_posts',
        'identify_updates_of_folders',
        'identify_updates_of_topics',
        'manage_topics',
        'manage_users',
        'send_debug_to_admin',
        'send_notifications',
        'send_notifications_helper',
        'send_notifications_helper_2',
        'title_recognize',
        'user_provide_info',
        ...,
    ],
 # DIFF   'save_user_statistics_to_db': ['api_get_active_searches', 'user_provide_info'], 
 # NO   'sql_connect': [
        'archive_notifications',
        'archive_to_bigquery',
        'check_first_posts_for_changes',
        'compose_notifications',
        'identify_updates_of_first_posts',
        'identify_updates_of_topics',
        'manage_topics',
    ],
# NO    'save_new_user': ['communicate', 'manage_users'],
# NO    'save_onboarding_step': ['communicate', 'manage_users'],
    'send_message_to_api': [
        'communicate',
        'send_notifications',
        'send_notifications_helper',
        'send_notifications_helper_2',
    ],
    'check_and_save_event_id': [
        'compose_notifications',
        'send_notifications',
        'send_notifications_helper',
        'send_notifications_helper_2',
    ],

    'get_triggering_function': [
        'compose_notifications',
        'send_notifications',
        'send_notifications_helper',
        'send_notifications_helper_2',
    ],
    'process_pubsub_message': [
        'compose_notifications',
        'identify_updates_of_first_posts',
        'identify_updates_of_topics',
        'manage_users',
        'send_debug_to_admin',
        'send_notifications',
        'send_notifications_helper',
        'send_notifications_helper_2',
        'users_activate',
    ],
    'save_function_into_register': ['identify_updates_of_first_posts', 'identify_updates_of_topics', 'manage_topics'],
    'read_snapshot_from_cloud_storage': ['identify_updates_of_folders', 'identify_updates_of_topics'],
# NO    'set_cloud_storage': ['identify_updates_of_folders', 'identify_updates_of_topics'],
    'write_snapshot_to_cloud_storage': ['identify_updates_of_folders', 'identify_updates_of_topics'],
    'check_for_notifs_to_send': ['send_notifications', 'send_notifications_helper', 'send_notifications_helper_2'],
    'finish_time_analytics': ['send_notifications', 'send_notifications_helper', 'send_notifications_helper_2'],
# OK    'get_change_log_update_time': ['send_notifications', 'send_notifications_helper', 'send_notifications_helper_2'],
    'iterate_over_notifications': ['send_notifications', 'send_notifications_helper', 'send_notifications_helper_2'],
    'process_response': ['send_notifications', 'send_notifications_helper', 'send_notifications_helper_2'],
    'save_sending_status_to_notif_by_user': [
        'send_notifications',
        'send_notifications_helper',
        'send_notifications_helper_2',
    ],
    'send_location_to_api': ['send_notifications', 'send_notifications_helper', 'send_notifications_helper_2'],
    'send_single_message': ['send_notifications', 'send_notifications_helper', 'send_notifications_helper_2'],
    'check_first_notif_to_send': ['send_notifications_helper', 'send_notifications_helper_2'],
}

"""
