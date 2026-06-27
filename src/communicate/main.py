"""receives telegram messages from users, acts accordingly and sends back the reply"""

import datetime
import logging
from functools import lru_cache
from typing import Any, Callable

from telegram import Bot, ReplyKeyboardMarkup, Update

from _dependencies.bot.users_management import (
    ManageUserAction,
    register_new_user,
    save_onboarding_step,
    update_user_status,
)
from _dependencies.common.commons import get_app_config, setup_logging
from _dependencies.common.misc import RequestWrapper, ResponseWrapper, request_response_converter
from _dependencies.common.pubsub import notify_admin

from ._utils.buttons import reply_markup_main
from ._utils.common import (
    LA_BOT_CHAT_URL,
    InlineButtonCallbackData,
    UpdateBasicParams,
    UpdateExtraParams,
    UserInputState,
)
from ._utils.database import db
from ._utils.decorators import tg_registry
from ._utils.handler_context import TGHandlerContext
from ._utils.handlers import (  # noqa: F401 — import to trigger @tg_handle registration
    button_handlers,
    callback_handlers,
    notification_settings_handlers,
    other_handlers,
    region_select_handlers,
    state_handlers,
    view_searches_handlers,
)
from ._utils.message_sending import tg_api

setup_logging(__package__)

# To get rid of telegram "Retrying" Warning logs, which are shown in GCP Log Explorer as Errors.
# Important – these are not errors, but jest informational warnings that there were retries, that's why we exclude them
logging.getLogger('telegram.vendor.ptb_urllib3.urllib3').setLevel(logging.ERROR)


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
    got_callback: InlineButtonCallbackData | None = None
    if callback_query:
        callback_data_text = callback_query.data
        try:
            got_callback = InlineButtonCallbackData.model_validate_json(callback_data_text)
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
        got_callback=got_callback,
        callback_query_id=callback_query_id,
        callback_query=callback_query,
    )


def _process_block_unblock_user(user_id: int, user_new_status: str) -> None:
    """processing of system message on user action to block/unblock the bot"""

    status_dict = {'kicked': ManageUserAction.block_user, 'member': ManageUserAction.unblock_user}

    # mark user as blocked / unblocked in psql
    update_user_status(status_dict[user_new_status], user_id)

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

    logging.info('running onboarding')
    if onboarding_step_id == 21:  # region_set
        # mark that onboarding is finished
        if got_message:
            save_onboarding_step(user_id, 'finished')
            onboarding_step_id = 80

    return onboarding_step_id


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
        logging.info(f'triggered handler: {_process_block_unblock_user.__name__}')
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

    if update_params.callback_query:
        # mark user update as 'received by bot'
        tg_api().send_callback_answer_to_api(user_id, update_params.callback_query.id, '')

    user_is_new = db().check_if_new_user(user_id)
    logging.info(f'After check_if_new_user: {user_is_new=}')
    if user_is_new:
        register_new_user(user_id, username, datetime.datetime.now())

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


def _run_registered_handlers(
    ctx: TGHandlerContext,
    **kwargs: Any,
) -> bool:
    """Try registered handlers matching the given conditions.

    Returns True if a handler consumed the context.
    """
    for handler in tg_registry.match(**kwargs):
        try:
            handler.func(ctx)
        except Exception:
            logging.exception(f'Handler {handler.func.__name__} crashed for user {ctx.user_id}')
            continue

        if ctx.is_consumed:
            logging.info(f'triggered handler: {handler.func.__name__}')
            return True

    return False


def _run_handlers(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> None:
    """Run the handler chain with a TGHandlerContext.

    Creates a TGHandlerContext and passes it through the handler chain.
    Each handler calls ctx.reply()/ctx.edit() to respond and mark as consumed.
    """
    ctx = TGHandlerContext(
        update_params=update_params,
        extra_params=extra_params,
        tg_api=tg_api(),
        db=db(),
    )

    got_message = update_params.got_message
    got_callback = update_params.got_callback
    user_input_state = extra_params.user_input_state

    logging.info(f'start checking handlers with {update_params=}, {extra_params=}')

    ### CALLBACK HANDLERS ###
    if got_callback:
        callback_data = str(got_callback.action)
        callback_keyboard = got_callback.keyboard_name
        if _run_registered_handlers(ctx, callback_data=callback_data, callback_keyboard=callback_keyboard):
            return

    ### TEXT + STATE HANDLERS ###
    if got_message and user_input_state and user_input_state != UserInputState.not_defined:
        text = got_message.strip().lower()
        state = user_input_state.value
        if _run_registered_handlers(ctx, text=text, state=state):
            return

    ### STATE-ONLY HANDLERS ###
    if user_input_state and user_input_state != UserInputState.not_defined:
        state = user_input_state.value
        if _run_registered_handlers(ctx, state=state):
            return

    ### TEXT-ONLY HANDLERS ###
    if got_message:
        text = got_message.strip().lower()
        if _run_registered_handlers(ctx, text=text):
            return

    ### AUTO COORDINATES BY BUTTON ###
    if update_params.user_latitude:
        # auto coordinates by button
        other_handlers.handle_user_geolocation(ctx)
        return

    ### CUSTOM TEXT ###
    user_regions = db().get_user_reg_folders_preferences(update_params.user_id)
    if not user_regions:
        # force user to input a region
        other_handlers.handle_force_user_to_set_region(ctx)
        return

    # in case of other user messages, when command is unknown
    ctx.reply(
        text='не понимаю такой команды, пожалуйста, используйте кнопки со стандартными командами ниже',
        reply_markup=reply_markup_main,
    )


@lru_cache
def _get_bot() -> Bot:
    return Bot(token=get_app_config().bot_api_token__prod)


@request_response_converter
def main(request: RequestWrapper, *args: Any, **kwargs: Any) -> ResponseWrapper:
    """Main function to orchestrate the whole script"""

    if request.method != 'POST':
        logging.error(f'non-post request identified {request}')
        return ResponseWrapper(data='it was not post request', status_code=400)

    bot = _get_bot()
    if request.json_ is None:
        return ResponseWrapper(data='no request data', status_code=400)

    update = Update.de_json(request.json_, bot)
    if update is None:
        return ResponseWrapper(data='failed to parse update', status_code=400)

    with db().connect():
        result = process_update(update)
        return ResponseWrapper(data=result)
