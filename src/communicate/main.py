"""receives telegram messages from users, acts accordingly and sends back the reply"""

import datetime
import logging
from ast import literal_eval
from functools import lru_cache
from typing import Any, Callable

from flask import Request
from telegram import Bot, CallbackQuery, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update

from _dependencies.commons import (
    Topics,
    get_app_config,
    publish_to_pubsub,
    setup_google_logging,
)
from _dependencies.misc import notify_admin

from ._utils.buttons import TopicTypeInlineKeyboardBuilder, reply_markup_main
from ._utils.common import (
    LA_BOT_CHAT_URL,
    UpdateBasicParams,
    UpdateExtraParams,
    UserInputState,
    save_onboarding_step,
)
from ._utils.database import db
from ._utils.handlers import (
    button_handlers,
    callback_handlers,
    notification_settings_handlers,
    other_handlers,
    state_handlers,
    view_searches_handlers,
)
from ._utils.message_sending import tg_api

setup_google_logging()

# To get rid of telegram "Retrying" Warning logs, which are shown in GCP Log Explorer as Errors.
# Important – these are not errors, but jest informational warnings that there were retries, that's why we exclude them
logging.getLogger('telegram.vendor.ptb_urllib3.urllib3').setLevel(logging.ERROR)

COMMON_HANDLERS = [
    callback_handlers.manage_search_whiteness,
    callback_handlers.handle_search_follow_mode,
    callback_handlers.handle_topic_type_user_changed,
    ###
    state_handlers.handle_radius_value,
    state_handlers.handle_linking_to_forum_user_input,
    state_handlers.handle_user_coordinates_from_text,
    ###
    button_handlers.handle_command_start,
    button_handlers.handle_user_role,
    button_handlers.handle_if_moscow,
    button_handlers.handle_help_needed,
    button_handlers.handle_admin_experimental_settings,
    button_handlers.handle_show_map,
    button_handlers.handle_topic_type_show_menu,
    button_handlers.handle_age_settings,
    button_handlers.handle_radius_menu,
    button_handlers.handle_radius_menu_show,
    button_handlers.handle_linking_to_forum_show_menu,
    button_handlers.handle_linking_to_forum_its_me,
    button_handlers.handle_linking_to_forum_not_me,
    button_handlers.handle_test_admin_check,
    button_handlers.handle_command_other,
    button_handlers.handle_set_region,
    button_handlers.handle_message_is_district,
    button_handlers.handle_message_is_federal_region,
    button_handlers.handle_main_settings,
    button_handlers.handle_coordinates_show_menu,
    button_handlers.handle_coordinates_show_saved,
    button_handlers.handle_coordinates_delete,
    button_handlers.handle_coordinates_menu_manual_input,
    button_handlers.handle_back_to_main_menu,
    button_handlers.handle_goto_community,
    button_handlers.handle_goto_first_search,
    button_handlers.handle_goto_photos,
    notification_settings_handlers.handle_notification_settings,
    notification_settings_handlers.handle_notification_settings_show_menu,
    view_searches_handlers.handle_view_searches,
]


def _get_param_if_exists(upd: Update, func_input: Callable) -> Any:
    """Return either value if exist or None. Used for messages with changing schema from telegram"""
    try:
        return func_input(upd)
    except:  # noqa
        return None


def _get_basic_update_parameters(update: Update) -> UpdateBasicParams:
    """decompose the incoming update into the key parameters"""

    user_new_status = _get_param_if_exists(update, lambda update: update.my_chat_member.new_chat_member.status)
    timer_changed = _get_param_if_exists(update, lambda update: update.message.message_auto_delete_timer_changed)
    photo = _get_param_if_exists(update, lambda update: update.message.photo)
    document = _get_param_if_exists(update, lambda update: update.message.document)
    voice = _get_param_if_exists(update, lambda update: update.message.voice)
    contact = _get_param_if_exists(update, lambda update: update.message.contact)
    inline_query = _get_param_if_exists(update, lambda update: update.inline_query)
    sticker = _get_param_if_exists(update, lambda update: update.message.sticker.file_id)
    user_latitude = _get_param_if_exists(update, lambda update: update.effective_message.location.latitude)
    user_longitude = _get_param_if_exists(update, lambda update: update.effective_message.location.longitude)
    got_message = _get_param_if_exists(update, lambda update: update.effective_message.text)

    channel_type = _get_param_if_exists(update, lambda update: update.edited_channel_post.chat.type)
    if not channel_type:
        channel_type = _get_param_if_exists(update, lambda update: update.channel_post.chat.type)
    if not channel_type:
        channel_type = _get_param_if_exists(update, lambda update: update.my_chat_member.chat.type)

    # the purpose of this bot - sending messages to unique users, this way
    # chat_id is treated as user_id and vice versa (which is not true in general)

    username = _get_param_if_exists(update, lambda update: update.effective_user.username)
    if not username:
        username = _get_param_if_exists(update, lambda update: update.effective_message.from_user.username)

    user_id = _get_param_if_exists(update, lambda update: update.effective_user.id)
    if not user_id:
        logging.error('EFFECTIVE USER.ID IS NOT GIVEN!')
        user_id = _get_param_if_exists(update, lambda update: update.effective_message.from_user.id)
    if not user_id:
        user_id = _get_param_if_exists(update, lambda update: update.effective_message.chat.id)
    if not user_id:
        user_id = _get_param_if_exists(update, lambda update: update.edited_channel_post.chat.id)
    if not user_id:
        user_id = _get_param_if_exists(update, lambda update: update.my_chat_member.chat.id)
    if not user_id:
        user_id = _get_param_if_exists(update, lambda update: update.inline_query.from_user.id)
    if not user_id:
        raise ValueError('user_id is not found')

    callback_query = _get_param_if_exists(update, lambda update: update.callback_query)
    callback_query_id = _get_param_if_exists(update, lambda update: update.callback_query.id)

    logging.info(f'get_basic_update_parameters..callback_query==, {str(callback_query)}')
    got_callback = None
    if callback_query:
        callback_data_text = callback_query.data
        try:
            got_callback = literal_eval(callback_data_text)
        except Exception:
            logging.exception(f'callback dict was not recognized for {callback_data_text=}')
            notify_admin(f'callback dict was not recognized for {callback_data_text=}')
        logging.info(f'get_basic_update_parameters..{got_callback=}, from {callback_data_text=}')

    return UpdateBasicParams(
        user_new_status=user_new_status,
        timer_changed=timer_changed,
        photo=photo,
        document=document,
        voice=voice,
        contact=contact,
        inline_query=inline_query,
        sticker=sticker,
        user_latitude=user_latitude,
        user_longitude=user_longitude,
        got_message=got_message or '',
        channel_type=channel_type,
        username=username,
        user_id=user_id,
        got_callback=got_callback,  # type:ignore[arg-type]
        callback_query_id=callback_query_id,
        callback_query=callback_query,
    )


def _save_new_user(user_id: int, username: str) -> None:
    """send pubsub message to dedicated script to save new user"""
    # TODO remove pub/sub, create user directly

    username = username if username else 'unknown'
    message_for_pubsub = {
        'action': 'new',
        'info': {'user': user_id, 'username': username},
        'time': str(datetime.datetime.now()),
    }
    publish_to_pubsub(Topics.topic_for_user_management, message_for_pubsub)


def _process_block_unblock_user(user_id: int, user_new_status: str) -> None:
    """processing of system message on user action to block/unblock the bot"""

    status_dict = {'kicked': 'block_user', 'member': 'unblock_user'}

    # mark user as blocked / unblocked in psql
    message_for_pubsub = {'action': status_dict[user_new_status], 'info': {'user': user_id}}
    publish_to_pubsub(Topics.topic_for_user_management, message_for_pubsub)

    if user_new_status != 'member':
        return
    bot_message = (
        'С возвращением! Бот скучал:) Жаль, что вы долго не заходили. '
        'Мы постарались сохранить все ваши настройки с вашего прошлого визита. '
        'Если у вас есть трудности в работе бота или пожелания, как сделать бот '
        'удобнее – напишите, пожалуйста, свои мысли в'
        f'<a href="{LA_BOT_CHAT_URL}">Специальный Чат'
        'в телеграм</a>. Спасибо:)'
    )

    keyboard_main = [['посмотреть актуальные поиски'], ['настроить бот'], ['другие возможности']]
    reply_markup = ReplyKeyboardMarkup(keyboard_main, resize_keyboard=True)

    data = {
        'text': bot_message,
        'reply_markup': reply_markup,
        'parse_mode': 'HTML',
        'chat_id': user_id,
        'disable_web_page_preview': True,
    }
    tg_api().send_message(data)


def _run_onboarding(user_id: int, username: str, onboarding_step_id: int, got_message: str) -> int:
    """part of the script responsible for orchestration of activities for non-finally-onboarded users"""

    if onboarding_step_id == 21:  # region_set
        # mark that onboarding is finished
        if got_message:
            save_onboarding_step(user_id, username, 'finished')
            onboarding_step_id = 80

    return onboarding_step_id


def _reply_to_user(
    user_id: int,
    got_callback: dict[str, Any] | None,
    callback_query: CallbackQuery | None,
    reply_markup: ReplyKeyboardMarkup | InlineKeyboardMarkup | ReplyKeyboardRemove | None,
    bot_message: str,
) -> None:
    context_step = '01a1'
    context = f'if reply_markup and not isinstance(reply_markup, dict): {reply_markup=}, {context_step=}'
    logging.info(f'{context=}: {reply_markup=}')

    user_used_inline_button = got_callback and not TopicTypeInlineKeyboardBuilder.manual_callback_handling(got_callback)

    if user_used_inline_button:
        # call editMessageText to edit inline keyboard
        # in the message where inline button was pushed
        last_user_message_id = callback_query.message.id  # type: ignore [union-attr]
        # was get_last_user_inline_dialogue( user_id)
        logging.info(f'{last_user_message_id=}')
        # params['message_id'] = last_user_message_id
        params = {
            'chat_id': user_id,
            'text': bot_message,
            'message_id': last_user_message_id,
            'reply_markup': reply_markup,
        }
        context_step = '1a1'
        context = f'main() if user_used_inline_button: {user_id=}, {context_step=}'
        tg_api().edit_message_text(params, context)

    else:
        params = {
            'parse_mode': 'HTML',
            'disable_web_page_preview': True,
            'reply_markup': reply_markup,
            'chat_id': user_id,
            'text': bot_message,
        }
        context_step = '1b1'
        context = f'main() if user_used_inline_button: else: {user_id=}, {context_step=}'
        tg_api().send_message(params, context)


def process_update(update: Update) -> str:
    update_params = _get_basic_update_parameters(update)

    logging.info(f'after get_basic_update_parameters:  {update_params.got_callback=}')

    if other_handlers.process_unneeded_messages(update, update_params):
        return 'finished successfully. it was useless message for bot'

    user_id = update_params.user_id
    got_message = update_params.got_message
    got_callback = update_params.got_callback
    username = update_params.username

    if update_params.user_new_status in {'kicked', 'member'}:
        _process_block_unblock_user(update_params.user_id, update_params.user_new_status)
        return 'finished successfully. it was a system message on bot block/unblock'

    # Admin - specially keep it for Admin, regular users unlikely will be interested in it

    logging.info(f'Before if got_message and not got_callback: {got_message=}')

    if got_message and not got_callback:
        last_inline_message_ids = db().get_last_user_inline_dialogue(user_id)
        if last_inline_message_ids:
            for last_inline_message_id in last_inline_message_ids:
                tg_api().edit_message_reply_markup(
                    user_id, last_inline_message_id, 'main() if got_message and not got_callback'
                )
            db().delete_last_user_inline_dialogue(user_id)

    if got_message:
        db().save_user_message_to_bot(user_id, got_message)

    user_is_new = db().check_if_new_user(user_id)
    logging.info(f'After check_if_new_user: {user_is_new=}')
    if user_is_new:
        _save_new_user(user_id, username)

    onboarding_step_id, onboarding_step_name = db().get_onboarding_step(user_id, user_is_new)

    # ONBOARDING PHASE
    if onboarding_step_id < 80:
        onboarding_step_id = _run_onboarding(user_id, username, onboarding_step_id, got_message)

    # Check what was last request from bot and if bot is expecting user's input
    user_input_state = db().get_user_input_state(user_id)

    extra_params = UpdateExtraParams(user_is_new, onboarding_step_id, user_input_state=user_input_state)

    if not got_message and not update_params.user_latitude:
        # all other cases when bot was not able to understand the message from user
        logging.info('DBG.C.6. THERE IS a COMM SCRIPT INVOCATION w/O MESSAGE:')
        logging.info(str(update))
        text_for_admin = (
            f'[comm]: Empty message in Comm, user={user_id}, username={username}, '
            f'got_message={got_message}, update={update}, '
            f'user_input_state={user_input_state}'
        )
        logging.info(text_for_admin)
        notify_admin(text_for_admin)
        return 'Got empty message. Finished successfully.'

    try:
        _run_handlers(update_params, extra_params)

    except Exception:
        logging.exception('GENERAL COMM CRASH:')
        notify_admin('[comm] general script fail')

    return 'finished successfully. in was a regular conversational message'


def _process_handler_result(
    update_params: UpdateBasicParams,
    bot_message: str,
    reply_markup: ReplyKeyboardMarkup | InlineKeyboardMarkup | ReplyKeyboardRemove | None,
    new_user_input_state: UserInputState | None = None,
) -> None:
    user_id = update_params.user_id
    got_callback = update_params.got_callback
    callback_query = update_params.callback_query

    if bot_message or reply_markup:
        _reply_to_user(user_id, got_callback, callback_query, reply_markup, bot_message)

    if not new_user_input_state:
        new_user_input_state = UserInputState.not_defined
    db().set_user_input_state(user_id, new_user_input_state)

    if bot_message:
        db().save_bot_reply_to_user(user_id, bot_message)


def _run_handlers(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> None:
    ### COMMON HANDLERS ###
    for handler in COMMON_HANDLERS:
        result = handler(update_params, extra_params)
        if not result:
            continue

        bot_message, reply_markup = result[0], result[1]
        new_user_input_state = result[2] if len(result) >= 3 else None

        _process_handler_result(update_params, bot_message, reply_markup, new_user_input_state)
        return

    ### AUTO COORDINATES BY BUTTON ###
    if update_params.user_latitude:
        # auto coordinates by button
        bot_message, reply_markup = other_handlers.handle_user_geolocation(update_params, extra_params)
        _process_handler_result(update_params, bot_message, reply_markup)
        return

    ### CUSTOM TEXT ###
    user_regions = db().get_user_reg_folders_preferences(update_params.user_id)
    if not user_regions:
        # force user to input a region
        bot_message, reply_markup = other_handlers.handle_force_user_to_set_region(update_params.user_id)
        _process_handler_result(update_params, bot_message, reply_markup)
        return

    # in case of other user messages, when command is unknown
    bot_message = 'не понимаю такой команды, пожалуйста, используйте кнопки со стандартными командами ниже'
    reply_markup = reply_markup_main

    _process_handler_result(update_params, bot_message, reply_markup_main)


@lru_cache
def _get_bot() -> Bot:
    return Bot(token=get_app_config().bot_api_token__prod)


def main(request: Request) -> str:
    """Main function to orchestrate the whole script"""

    if request.method != 'POST':
        logging.error(f'non-post request identified {request}')
        return 'it was not post request'

    bot = _get_bot()
    update = Update.de_json(request.get_json(force=True), bot)

    with db().connect():
        return process_update(update)  # type: ignore[arg-type]
