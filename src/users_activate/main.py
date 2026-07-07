import logging

from _dependencies.common.commons import setup_logging

from ._utils.database import DBClient

setup_logging(__package__)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logging.warning('it is a synthetic warning')


def mark_up_onboarding_status_0(db: DBClient) -> None:
    """marks up Onboarding step_id=0 for existing old users"""
    user_id_to_update = db.get_user_for_onboarding_step_0()
    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=0')
        db.insert_onboarding_step(user_id_to_update, 'start', 0)
    else:
        logging.info('There are no users to assign onboarding pref_id=0.')


def mark_up_onboarding_status_0_2(db: DBClient) -> None:
    """marks up Onboarding step_id=0 for existing old users"""
    user_id_to_update = db.get_user_for_onboarding_step_0_2()
    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=0')
        db.insert_onboarding_step(user_id_to_update, 'start', 0)
    else:
        logging.info('There are no users to assign onboarding pref_id=0.')


def mark_up_onboarding_status_10(db: DBClient) -> None:
    """marks up Onboarding step_id=10 ('role_set') for existing old users"""
    user_id_to_update = db.get_user_for_onboarding_step_10()
    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=10')
        db.insert_onboarding_step(user_id_to_update, 'role_set', 10)
    else:
        logging.info('There are no users to assign onboarding pref_id=10.')


def mark_up_onboarding_status_10_2(db: DBClient) -> None:
    """marks up Onboarding step_id=0 for existing old users"""
    user_id_to_update = db.get_user_for_onboarding_step_10_2()
    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=10')
        db.insert_onboarding_step(user_id_to_update, 'role_set', 10)
    else:
        logging.info('There are no users to assign onboarding pref_id=10.')


def mark_up_onboarding_status_20(db: DBClient) -> None:
    """marks up Onboarding step_id=20 ('moscow_replied') for existing old users"""
    user_id_to_update = db.get_user_for_onboarding_step_20()
    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=20')
        db.insert_onboarding_step(user_id_to_update, 'moscow_replied', 20)
    else:
        logging.info('There are no users to assign onboarding pref_id=20.')


def mark_up_onboarding_status_21(db: DBClient) -> None:
    """marks up Onboarding step_id=21 ('region_set') for existing old users"""
    user_id_to_update = db.get_user_for_onboarding_step_21()
    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=21')
        db.insert_onboarding_step(user_id_to_update, 'region_set', 21)
    else:
        logging.info('There are no users to assign onboarding pref_id=21.')


def mark_up_onboarding_status_80(db: DBClient) -> None:
    """marks up Onboarding step_id=80 for existing old users"""
    user_id_to_update = db.get_user_for_onboarding_step_80()
    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')
        db.insert_onboarding_step(user_id_to_update, 'finished', 80)
    else:
        logging.info('There are no users to assign onboarding pref_id=80.')


def mark_up_onboarding_status_80_patch(db: DBClient) -> None:
    """marks up Onboarding step_id=80 for existing old users"""
    user_id_to_update = db.get_user_for_onboarding_step_80_patch()
    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')
        db.insert_onboarding_step(user_id_to_update, 'finished', 80)
    else:
        logging.info('There are no users to assign onboarding pref_id=80.')


def mark_up_onboarding_status_80_wo_dialogs(db: DBClient) -> None:
    """marks up Onboarding step_id=80 for existing old users w/o dialogs at all"""
    user_id_to_update = db.get_user_for_onboarding_step_80_wo_dialogs()
    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')
        db.insert_onboarding_step(user_id_to_update, 'finished', 80)
    else:
        logging.info('There are no users to assign onboarding pref_id=80.')


def mark_up_onboarding_status_80_just_got_summaries(db: DBClient) -> None:
    """marks up Onboarding step_id=80 for existing old users"""
    user_id_to_update = db.get_user_for_onboarding_step_80_just_summaries()
    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')
        db.insert_onboarding_step(user_id_to_update, 'finished', 80)
    else:
        logging.info('There are no users to assign onboarding pref_id=80.')


def mark_up_onboarding_status_80_have_all_settings(db: DBClient) -> None:
    """marks up Onboarding step_id=80 for existing old users"""
    user_id_to_update = db.get_user_for_onboarding_step_80_all_settings()
    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')
        db.insert_onboarding_step(user_id_to_update, 'finished', 80)
    else:
        logging.info('There are no users to assign onboarding pref_id=80.')


def mark_up_onboarding_status_80_self_deactivated(db: DBClient) -> None:
    """marks up Onboarding step_id=80 for existing old users"""
    user_id_to_update = db.get_user_for_onboarding_step_80_self_deactivated()
    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')
        db.insert_onboarding_step(user_id_to_update, 'finished', 80)
        db.delete_temp_onboarding_user(user_id_to_update)
    else:
        logging.info('There are no users to assign onboarding pref_id=80.')


def mark_up_onboarding_status_99(db: DBClient) -> None:
    """marks up Onboarding step_id=99 for existing old users"""
    user_id_to_update = db.get_user_for_onboarding_step_99()
    if user_id_to_update:
        logging.info(f'User {user_id_to_update}, will be assigned with onboarding pref_id=80')
        db.insert_onboarding_step(user_id_to_update, 'unrecognized', 99)
        db.delete_temp_onboarding_user(user_id_to_update)
    else:
        logging.info('There are no users to assign onboarding pref_id=80.')


def main(event, context):  # noqa
    """main function"""

    # FIXME –testing logging, which, seems, disappeared
    logging.info('this is 1st logging line')
    print('this is 1st print line')
    # FIXME ^^^

    db = DBClient()
    try:
        # mark_up_onboarding_status_0(db)
        # mark_up_onboarding_status_10(db)
        # mark_up_onboarding_status_20(db)
        # mark_up_onboarding_status_21(db)
        # mark_up_onboarding_status_80(db)
        # mark_up_onboarding_status_80_patch(db)
        # mark_up_onboarding_status_80_wo_dialogs(db)

        for _ in range(20):
            # mark_up_onboarding_status_0_2(db)
            # mark_up_onboarding_status_10_2(db)
            # mark_up_onboarding_status_80_just_got_summaries(db)
            # mark_up_onboarding_status_80_have_all_settings(db)
            # mark_up_onboarding_status_80_self_deactivated(db)
            # mark_up_onboarding_status_99(db)
            pass

    except Exception as e:
        logging.error('User activation script failed')
        logging.exception(e)

    return 'ok'
