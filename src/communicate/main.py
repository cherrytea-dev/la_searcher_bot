# ToDo later: user_callback["action"] == "search_follow_mode" заменить на "sfmw", "sfmb"

"""receives telegram messages from users, acts accordingly and sends back the reply"""

import datetime
import logging
from typing import Union

import requests
from flask import Request
from telegram import (
    Bot,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)

from _dependencies.commons import (
    Topics,
    get_app_config,
    publish_to_pubsub,
    setup_google_logging,
)
from _dependencies.misc import (
    notify_admin,
    process_sending_message_async,
)
from communicate._utils.buttons import (
    Commands,
    CoordinateSettingsMenu,
    DistanceSettings,
    HelpNeeded,
    MainSettingsMenu,
    NotificationSettingsMenu,
    RoleChoice,
    UrgencySettings,
    b_act_titles,
    b_admin_menu,
    b_back_to_start,
    b_fed_dist_pick_other,
    b_goto_community,
    b_goto_first_search,
    b_goto_photos,
    b_map,
    b_menu_set_region,
    b_no_its_not_me,
    b_orders_done,
    b_orders_tbd,
    b_other,
    b_reg_moscow,
    b_reg_not_moscow,
    b_settings,
    b_test_menu,
    b_test_search_follow_mode_off,
    b_test_search_follow_mode_on,
    b_view_act_searches,
    b_view_latest_searches,
    b_yes_its_me,
    c_start,
    dict_of_fed_dist,
    fed_okr_dict,
    folder_dict,
    full_buttons_dict,
    full_dict_of_regions,
    keyboard_fed_dist_set,
    reply_markup_main,
)
from communicate._utils.common import (
    AllButtons,
    UpdateBasicParams,
    get_coordinates_from_string,
    get_default_age_period_list,
    save_onboarding_step,
)
from communicate._utils.compose_messages import (
    compose_full_message_on_list_of_searches,
    compose_full_message_on_list_of_searches_ikb,
)
from communicate._utils.database import db
from communicate._utils.handlers import (
    handle_admin_experimental_settings,
    handle_age_settings,
    handle_coordinates,
    handle_goto_community,
    handle_goto_first_search,
    handle_goto_photos,
    handle_help_needed,
    handle_main_settings,
    handle_notification_settings,
    handle_show_map,
    handle_user_coordinates,
    handle_user_role,
    manage_if_moscow,
    manage_linking_to_forum,
    manage_radius,
    manage_search_follow_mode,
    manage_search_whiteness,
    manage_topic_type,
    process_unneeded_messages,
)
from communicate._utils.message_sending import (
    make_api_call,
    process_response_of_api_call,
)

setup_google_logging()

# To get rid of telegram "Retrying" Warning logs, which are shown in GCP Log Explorer as Errors.
# Important – these are not errors, but jest informational warnings that there were retries, that's why we exclude them
logging.getLogger('telegram.vendor.ptb_urllib3.urllib3').setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


# issue#425
def update_and_download_list_of_regions(
    user_id: int, got_message: str, b_menu_set_region: str, b_fed_dist_pick_other: str
) -> str:
    """Upload, download and compose a message on the list of user's regions"""

    msg = ''
    is_first_entry = None
    region_was_in_db = None
    region_is_the_only = None

    # Reversed dict is needed on the last step
    rev_reg_dict = {value[0]: key for (key, value) in folder_dict.items()}

    # TODO - get the list of regions from PSQL
    # TODO ^^^

    # case for the first entry to the screen of Reg Settings
    if got_message == b_menu_set_region:
        is_first_entry = 'yes'
    elif got_message in fed_okr_dict or got_message == b_fed_dist_pick_other:
        pass
    else:
        try:
            list_of_regs_to_upload = folder_dict[got_message]

            # any region
            user_curr_regs = db().get_user_regions_from_db(user_id)

            for user_reg in user_curr_regs:
                if list_of_regs_to_upload[0] == user_reg:
                    region_was_in_db = 'yes'
                    break
            if region_was_in_db:
                if len(user_curr_regs) - len(list_of_regs_to_upload) < 1:
                    region_is_the_only = 'yes'

            # Scenario: this setting WAS in place, and now we need to DELETE it
            if region_was_in_db == 'yes' and not region_is_the_only:
                for region in list_of_regs_to_upload:
                    db().delete_folder_from_user_regional_preference(user_id, region)

            # Scenario: this setting WAS in place, but now it's the last one - we cannot delete it
            elif region_was_in_db == 'yes' and region_is_the_only:
                pass

            # Scenario: it's a NEW setting, we need to ADD it
            else:
                for region in list_of_regs_to_upload:
                    db().add_folder_to_user_regional_preference(user_id, region)

        except Exception as e:
            logging.exception("failed to upload & download the list of user's regions")

    # Get the list of resulting regions
    user_curr_regs_list = db().get_user_regions(user_id)

    for reg in user_curr_regs_list:
        if reg in rev_reg_dict:
            msg += ',\n &#8226; ' + rev_reg_dict[reg]

    msg = msg[1:]

    if is_first_entry:
        pre_msg = 'Бот может показывать поиски в любом регионе работы ЛА.\n'
        pre_msg += (
            'Вы можете подписаться на несколько регионов – просто кликните на соответствующие кнопки регионов.'
            '\nЧтобы ОТПИСАТЬСЯ от ненужных регионов – нажмите на соответствующую кнопку региона еще раз.\n\n'
        )
        pre_msg += 'Текущий список ваших регионов:'
        msg = pre_msg + msg
    elif region_is_the_only:
        msg = (
            'Ваш регион поисков настроен' + msg + '\n\nВы можете продолжить добавлять регионы, либо нажмите '
            'кнопку "в начало", чтобы продолжить работу с ботом.'
        )
    elif got_message in fed_okr_dict or got_message == b_fed_dist_pick_other:
        if user_curr_regs_list:
            msg = 'Текущий список ваших регионов:' + msg
        else:
            msg = 'Пока список выбранных регионов пуст. Выберите хотя бы один.'
    else:
        msg = (
            'Записали. Обновленный список ваших регионов:' + msg + '\n\nВы можете продолжить добавлять регионы, '
            'либо нажмите кнопку "в начало", чтобы '
            'продолжить работу с ботом.'
        )

    return msg


def get_param_if_exists(upd: Update, func_input: str):
    """Return either value if exist or None. Used for messages with changing schema from telegram"""

    update = upd  # noqa

    try:
        func_output = eval(func_input)
    except:  # noqa
        func_output = None

    return func_output


# issue#425
def get_last_bot_message_id(response: requests.Response) -> int:
    """Get the message id of the bot's message that was just sent"""

    try:
        message_id = response.json()['result']['message_id']

    except Exception as e:  # noqa
        message_id = None

    return message_id


def inline_processing(response, params) -> None:
    """process the response got from inline buttons interactions"""

    if not response or 'chat_id' not in params.keys():
        return None

    chat_id = params['chat_id']
    sent_message_id = get_last_bot_message_id(response)

    if 'reply_markup' in params.keys() and 'inline_keyboard' in params['reply_markup'].keys():
        prev_message_id = db().get_last_user_inline_dialogue(chat_id)
        logging.info(f'{prev_message_id=}')
        db().save_last_user_inline_dialogue(chat_id, sent_message_id)

    return None


def get_the_update(bot: Bot, request: Request) -> Update | None:
    """converts a request to an update"""

    try:
        update = Update.de_json(request.get_json(force=True), bot)
    except Exception as e:
        logging.exception(e)
        logging.error('request received has no update')
        update = None

    logging.info(f'update received: {request.get_json(force=True)}')

    return update


def get_basic_update_parameters(update: Update) -> UpdateBasicParams:
    """decompose the incoming update into the key parameters"""

    user_new_status = get_param_if_exists(update, 'update.my_chat_member.new_chat_member.status')
    timer_changed = get_param_if_exists(update, 'update.message.message_auto_delete_timer_changed')
    photo = get_param_if_exists(update, 'update.message.photo')
    document = get_param_if_exists(update, 'update.message.document')
    voice = get_param_if_exists(update, 'update.message.voice')
    contact = get_param_if_exists(update, 'update.message.contact')
    inline_query = get_param_if_exists(update, 'update.inline_query')
    sticker = get_param_if_exists(update, 'update.message.sticker.file_id')
    user_latitude = get_param_if_exists(update, 'update.effective_message.location.latitude')
    user_longitude = get_param_if_exists(update, 'update.effective_message.location.longitude')
    got_message = get_param_if_exists(update, 'update.effective_message.text')

    channel_type = get_param_if_exists(update, 'update.edited_channel_post.chat.type')
    if not channel_type:
        channel_type = get_param_if_exists(update, 'update.channel_post.chat.type')
    if not channel_type:
        channel_type = get_param_if_exists(update, 'update.my_chat_member.chat.type')

    # the purpose of this bot - sending messages to unique users, this way
    # chat_id is treated as user_id and vice versa (which is not true in general)

    username = get_param_if_exists(update, 'update.effective_user.username')
    if not username:
        username = get_param_if_exists(update, 'update.effective_message.from_user.username')

    user_id = get_param_if_exists(update, 'update.effective_user.id')
    if not user_id:
        logging.exception('EFFECTIVE USER.ID IS NOT GIVEN!')
        user_id = get_param_if_exists(update, 'update.effective_message.from_user.id')
    if not user_id:
        user_id = get_param_if_exists(update, 'update.effective_message.chat.id')
    if not user_id:
        user_id = get_param_if_exists(update, 'update.edited_channel_post.chat.id')
    if not user_id:
        user_id = get_param_if_exists(update, 'update.my_chat_member.chat.id')
    if not user_id:
        user_id = get_param_if_exists(update, 'update.inline_query.from.id')
    if not user_id:
        logging.info('failed to define user_id')

    # FIXME – 17.11.2023 – playing with getting inline buttons interactions
    callback_query = get_param_if_exists(update, 'update.callback_query')
    callback_query_id = get_param_if_exists(update, 'update.callback_query.id')

    logging.info(f'get_basic_update_parameters..callback_query==, {str(callback_query)}')
    got_hash = None
    got_callback = None
    if callback_query:
        callback_data_text = callback_query.data
        try:
            got_callback = eval(callback_data_text)
            got_hash = got_callback.get('hash')
        except Exception as e:
            logging.exception(e)
            notify_admin(f'callback dict was not recognized for {callback_data_text=}')
        logging.info(f'get_basic_update_parameters..{got_callback=}, {got_hash=} from {callback_data_text=}')
    # FIXME ^^^

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
        got_message=got_message,
        channel_type=channel_type,
        username=username,
        user_id=user_id,
        got_hash=got_hash,
        got_callback=got_callback,
        callback_query_id=callback_query_id,
        callback_query=callback_query,
    )


def save_new_user(user_id: int, username: str) -> None:
    """send pubsub message to dedicated script to save new user"""
    # TODO remove pub/sub, create user directly

    username = username if username else 'unknown'
    message_for_pubsub = {
        'action': 'new',
        'info': {'user': user_id, 'username': username},
        'time': str(datetime.datetime.now()),
    }
    publish_to_pubsub(Topics.topic_for_user_management, message_for_pubsub)


def process_block_unblock_user(user_id, user_new_status):
    """processing of system message on user action to block/unblock the bot"""

    try:
        status_dict = {'kicked': 'block_user', 'member': 'unblock_user'}

        # mark user as blocked / unblocked in psql
        message_for_pubsub = {'action': status_dict[user_new_status], 'info': {'user': user_id}}
        publish_to_pubsub(Topics.topic_for_user_management, message_for_pubsub)

        if user_new_status == 'member':
            bot_message = (
                'С возвращением! Бот скучал:) Жаль, что вы долго не заходили. '
                'Мы постарались сохранить все ваши настройки с вашего прошлого визита. '
                'Если у вас есть трудности в работе бота или пожелания, как сделать бот '
                'удобнее – напишите, пожалуйста, свои мысли в'
                '<a href="https://t.me/joinchat/2J-kV0GaCgwxY2Ni">Специальный Чат'
                'в телеграм</a>. Спасибо:)'
            )

            keyboard_main = [['посмотреть актуальные поиски'], ['настроить бот'], ['другие возможности']]
            reply_markup = ReplyKeyboardMarkup(keyboard_main, resize_keyboard=True)

            data = {
                'text': bot_message,
                'reply_markup': reply_markup,
                'parse_mode': 'HTML',
                'disable_web_page_preview': True,
            }
            process_sending_message_async(user_id=user_id, data=data)

    except Exception as e:
        logging.exception('Error in finding basic data for block/unblock user in Communicate script')


def run_onboarding(user_id: int, username: str, onboarding_step_id: int, got_message: str) -> int:
    """part of the script responsible for orchestration of activities for non-finally-onboarded users"""

    if onboarding_step_id == 21:  # region_set
        # mark that onboarding is finished
        if got_message:
            save_onboarding_step(user_id, username, 'finished')
            onboarding_step_id = 80

    return onboarding_step_id


def _reply_to_user(
    bot_token: str, user_id: int, got_callback, callback_query, got_hash, reply_markup, bot_message: str
):
    context_step = '01a1'
    context = f'if reply_markup and not isinstance(reply_markup, dict): {reply_markup=}, {context_step=}'
    logging.info(f'{context=}: {reply_markup=}')
    if reply_markup and not isinstance(reply_markup, dict):
        reply_markup = reply_markup.to_dict()
        context_step = '02a1'
        context = f'After reply_markup.to_dict(): {reply_markup=}, {context_step=}'
        logging.info(f'{context=}: {reply_markup=}')

    user_used_inline_button = got_hash and got_callback and got_callback['action'] != 'about'

    if user_used_inline_button:
        # call editMessageText to edit inline keyboard
        # in the message where inline button was pushed
        last_user_message_id = callback_query.message.id  ##was get_last_user_inline_dialogue( user_id)
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
        response = make_api_call('editMessageText', bot_token, params, context)
        context_step = '1a2'
        context = f'main() if user_used_inline_button: {user_id=}, {context_step=}'
        logging.info(f'{response=}; {context=}')

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
        response = make_api_call('sendMessage', bot_token, params, context)
        context_step = '1b2'
        context = f'main() if user_used_inline_button: else: {user_id=}, {context_step=}'
        logging.info(f'{response=}; {context=}')

    context_step = '2'
    context = f'main() after if user_used_inline_button: {user_id=}, {context_step=}'
    logging.info(f'{response=}; {context=}')
    context_step = '3'
    context = f'main() after if user_used_inline_button: {user_id=}, {context_step=}'
    result = process_response_of_api_call(user_id, response)
    inline_processing(response, params)

    logging.info(f'RESPONSE {response}')
    logging.info(f'RESULT {result}')


def main(request: Request) -> str:
    """Main function to orchestrate the whole script"""

    if request.method != 'POST':
        logging.error(f'non-post request identified {request}')
        return 'it was not post request'

    bot_token = get_app_config().bot_api_token__prod
    bot = Bot(token=bot_token)
    update = get_the_update(bot, request)
    with db().connect():
        return process_update(update)


def process_update(update: Update) -> str:
    bot_token = get_app_config().bot_api_token__prod

    update_params = get_basic_update_parameters(update)

    logging.info(f'after get_basic_update_parameters:  {update_params.got_callback=}')

    if process_unneeded_messages(update, update_params):
        return 'finished successfully. it was useless message for bot'

    user_id = update_params.user_id
    got_message = update_params.got_message
    got_callback = update_params.got_callback
    username = update_params.username
    callback_query = update_params.callback_query
    callback_query_id = update_params.callback_query_id
    got_hash = update_params.got_hash
    user_latitude = update_params.user_latitude
    user_longitude = update_params.user_longitude

    if update_params.user_new_status in {'kicked', 'member'}:
        process_block_unblock_user(update_params.user_id, update_params.user_new_status)
        return 'finished successfully. it was a system message on bot block/unblock'

    b = AllButtons(full_buttons_dict)

    # Admin - specially keep it for Admin, regular users unlikely will be interested in it

    age_buttons = []
    for period in get_default_age_period_list():
        age_buttons.append(f'отключить: {period.description}')
        age_buttons.append(f'включить: {period.description}')

    # basic markup which will be substituted for all specific cases
    reply_markup = reply_markup_main

    logging.info(f'Before if got_message and not got_callback: {got_message=}')

    if got_message and not got_callback:
        last_inline_message_ids = db().get_last_user_inline_dialogue(user_id)
        if last_inline_message_ids:
            for last_inline_message_id in last_inline_message_ids:
                params = {'chat_id': user_id, 'message_id': last_inline_message_id}
                make_api_call('editMessageReplyMarkup', bot_token, params, 'main() if got_message and not got_callback')
            db().delete_last_user_inline_dialogue(user_id)

    if got_message:
        db().save_user_message_to_bot(user_id, got_message)

    bot_request_aft_usr_msg = ''
    msg_sent_by_specific_code = False

    user_is_new = db().check_if_new_user(user_id)
    logging.info(f'After check_if_new_user: {user_is_new=}')
    if user_is_new:
        save_new_user(user_id, username)

    onboarding_step_id, onboarding_step_name = db().check_onboarding_step(user_id, user_is_new)
    user_regions = db().get_user_reg_folders_preferences(user_id)
    user_role = db().get_user_role(user_id)

    # Check what was last request from bot and if bot is expecting user's input
    bot_request_bfr_usr_msg = db().get_last_bot_msg(user_id)

    # placeholder for the New message from bot as reply to "update". Placed here – to avoid errors of GCF
    bot_message = ''

    # ONBOARDING PHASE
    if onboarding_step_id < 80:
        onboarding_step_id = run_onboarding(user_id, username, onboarding_step_id, got_message)

    # get coordinates from the text
    if bot_request_bfr_usr_msg == 'input_of_coords_man':
        user_latitude, user_longitude = get_coordinates_from_string(got_message, user_latitude, user_longitude)

    # if there is any coordinates from user
    if user_latitude and user_longitude:
        handle_user_coordinates(
            user_id,
            user_latitude,
            user_longitude,
            CoordinateSettingsMenu.b_coords_check,
            CoordinateSettingsMenu.b_coords_del,
            bot_request_aft_usr_msg,
        )

        return 'finished successfully. in was a message with user coordinates'

    try:
        # if there is a text message from user
        if got_message:
            # if pushed \start
            if got_message == c_start:
                if user_is_new:
                    # FIXME – 02.12.2023 – hiding menu button for the newcomers
                    #  (in the future it should be done in manage_user script)
                    method = 'setMyCommands'
                    params = {'commands': [], 'scope': {'type': 'chat', 'chat_id': user_id}}
                    response = make_api_call(
                        method=method, bot_api_token=bot_token, params=params, call_context='if user_is_new'
                    )
                    result = process_response_of_api_call(user_id, response)
                    logging.info(f'hiding user {user_id} menu status = {result}')
                    # FIXME ^^^

                    bot_message = (
                        'Привет! Это Бот Поисковика ЛизаАлерт. Он помогает Поисковикам '
                        'оперативно получать информацию о новых поисках или об изменениях '
                        'в текущих поисках.'
                        '\n\nБот управляется кнопками, которые заменяют обычную клавиатуру. '
                        'Если кнопки не отображаются, справа от поля ввода сообщения '
                        'есть специальный значок, чтобы отобразить кнопки управления ботом.'
                        '\n\nДавайте настроим бот индивидуально под вас. Пожалуйста, '
                        'укажите вашу роль сейчас?'
                    )
                    keyboard_role = [[role] for role in RoleChoice.list()]
                    reply_markup = ReplyKeyboardMarkup(keyboard_role, resize_keyboard=True)

                else:
                    bot_message = 'Привет! Бот управляется кнопками, которые заменяют обычную клавиатуру.'
                    reply_markup = reply_markup_main

            elif (
                onboarding_step_id == 20 and got_message in full_dict_of_regions
            ) or got_message == b_reg_moscow:  # "moscow_replied"
                # FIXME – 02.12.2023 – un-hiding menu button for the newcomers
                #  (in the future it should be done in manage_user script)
                method = 'deleteMyCommands'
                params = {'scope': {'type': 'chat', 'chat_id': user_id}}
                response = make_api_call(method=method, bot_api_token=bot_token, params=params)
                result = process_response_of_api_call(user_id, response)
                # FIXME ^^^

                bot_message = (
                    '🎉 Отлично, вы завершили базовую настройку Бота.\n\n'
                    'Список того, что сейчас умеет бот:\n'
                    '- Высылает сводку по идущим поискам\n'
                    '- Высылает сводку по последним поисками\n'
                    '- Информирует о новых поисках с указанием расстояния до поиска\n'
                    '- Информирует об изменении Статуса / Первого поста Инфорга\n'
                    '- Информирует о новых комментариях Инфорга или пользователей\n'
                    '- Позволяет гибко настроить информирование на основе удаленности от '
                    'вас, возраста пропавшего и т.п.\n\n'
                    'С этого момента вы начнёте получать основные уведомления в '
                    'рамках выбранного региона, как только появятся новые изменения. '
                    'Или же вы сразу можете просмотреть списки Активных и Последних поисков.\n\n'
                    'Бот приглашает вас настроить дополнительные параметры (можно пропустить):\n'
                    '- Настроить виды уведомлений\n'
                    '- Указать домашние координаты\n'
                    '- Указать максимальный радиус до поиска\n'
                    '- Указать возрастные группы пропавших\n'
                    '- Связать бот с Форумом\n\n'
                    'Создатели Бота надеются, что Бот сможет помочь вам в ваших задачах! Удачи!'
                )

                keyboard_role = [
                    [MainSettingsMenu.b_set_pref_notif_type],
                    [MainSettingsMenu.b_set_pref_coords],
                    [MainSettingsMenu.b_set_pref_radius],
                    [MainSettingsMenu.b_set_pref_age],
                    [MainSettingsMenu.b_set_forum_nick],
                    [b_view_latest_searches],
                    [b_view_act_searches],
                    [b_back_to_start],
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard_role, resize_keyboard=True)

                if got_message == b_reg_moscow:
                    bot_message, reply_markup = manage_if_moscow(
                        user_id,
                        username,
                        got_message,
                        b_reg_moscow,
                        b_reg_not_moscow,
                        reply_markup,
                        keyboard_fed_dist_set,
                        bot_message,
                        user_role,
                    )
                else:
                    save_onboarding_step(user_id, username, 'region_set')
                    db().save_user_pref_topic_type(user_id, 'default', user_role)
                    updated_regions = update_and_download_list_of_regions(
                        user_id, got_message, b_menu_set_region, b_fed_dist_pick_other
                    )

            elif got_message in {
                *RoleChoice.list(),
                b_orders_done,
                b_orders_tbd,
            }:
                # save user role & onboarding stage
                bot_message, reply_markup = handle_user_role(user_id, got_message, username)

            elif got_message in {b_reg_not_moscow}:
                bot_message, reply_markup = manage_if_moscow(
                    user_id,
                    username,
                    got_message,
                    b_reg_moscow,
                    b_reg_not_moscow,
                    reply_markup_main,
                    keyboard_fed_dist_set,
                    None,
                    user_role,
                )
            elif got_message in HelpNeeded.list():
                bot_message, reply_markup = handle_help_needed(got_message)

            # set user pref: urgency
            elif got_message in UrgencySettings.list():
                db().save_user_pref_urgency(
                    user_id,
                    got_message,
                    UrgencySettings.b_pref_urgency_highest,
                    UrgencySettings.b_pref_urgency_high,
                    UrgencySettings.b_pref_urgency_medium,
                    UrgencySettings.b_pref_urgency_low,
                )
                bot_message = 'Хорошо, спасибо. Бот запомнил ваш выбор.'

            # force user to input a region
            elif not user_regions and not (
                got_message in full_dict_of_regions
                or got_message in dict_of_fed_dist
                or got_message in {b_menu_set_region, c_start, b_settings, Commands.c_settings}
            ):
                bot_message = (
                    'Для корректной работы бота, пожалуйста, задайте свой регион. Для этого '
                    'с помощью кнопок меню выберите сначала ФО (федеральный округ), а затем и '
                    'регион. Можно выбирать несколько регионов из разных ФО. Выбор региона '
                    'также можно отменить, повторно нажав на кнопку с названием региона. '
                    'Функционал бота не будет активирован, пока не выбран хотя бы один регион.'
                )

                keyboard_coordinates_admin = [[b_menu_set_region]]
                reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)

                logging.info(f'user {user_id} is forced to fill in the region')

            elif got_callback and got_callback['action'] == 'search_follow_mode':  # issue#425
                bot_message, reply_markup = manage_search_whiteness(
                    user_id, got_callback, callback_query_id, callback_query, bot_token
                )

            elif got_callback and got_callback['action'] in [
                'search_follow_mode_on',
                'search_follow_mode_off',
            ]:  # issue#425
                bot_message = manage_search_follow_mode(
                    user_id, got_callback, callback_query_id, callback_query, bot_token
                )
                reply_markup = reply_markup_main

            # Send summaries
            elif got_message in {
                b_view_latest_searches,
                b_view_act_searches,
                Commands.c_view_latest_searches,
                Commands.c_view_act_searches,
            }:
                msg_sent_by_specific_code = True

                temp_dict = {
                    b_view_latest_searches: 'all',
                    b_view_act_searches: 'active',
                    Commands.c_view_latest_searches: 'all',
                    Commands.c_view_act_searches: 'active',
                }

                folders_list = db().get_geo_folders_db()

                if db().get_search_follow_mode(user_id) and 'tester' in db().get_user_sys_roles(user_id):
                    # issue#425 make inline keyboard - list of searches
                    keyboard = []  # to combine monolit ikb for all user's regions
                    ikb_searches_count = 0

                    folder_ids = db().get_folders_with_followed_searches(user_id)

                    user_regions_plus_followed = user_regions
                    followed_regions_not_in_preffs = []
                    for folder_id in folder_ids:
                        if folder_id not in user_regions:
                            followed_regions_not_in_preffs.append(folder_id)
                            user_regions_plus_followed.append(folder_id)

                    region_name = ''
                    for region in user_regions_plus_followed:
                        for line in folders_list:
                            if line[0] == region:
                                region_name = line[1]
                                break

                        logging.info(f'Before if region_name.find...: {bot_message=}; {keyboard=}')
                        # check if region – is an archive folder: if so – it can be sent only to 'all'
                        if region_name.find('аверш') == -1 or temp_dict[got_message] == 'all':
                            new_region_ikb_list = compose_full_message_on_list_of_searches_ikb(
                                temp_dict[got_message],
                                user_id,
                                region,
                                region_name,
                                only_followed=(region in followed_regions_not_in_preffs),
                            )
                            keyboard.append(new_region_ikb_list)
                            ikb_searches_count += len(new_region_ikb_list) - 1  ##number of searches in the region
                            logging.info(f'After += compose_full_message_on_list_of_searches_ikb: {keyboard=}')

                    ##msg_sent_by_specific_code for combined ikb start
                    if ikb_searches_count == 0:
                        bot_message = 'Незавершенные поиски в соответствии с Вашей настройкой видов поисков не найдены.'
                        params = {
                            'parse_mode': 'HTML',
                            'disable_web_page_preview': True,
                            'reply_markup': reply_markup,
                            'chat_id': user_id,
                            'text': bot_message,
                        }
                        context = f'{user_id=}, context_step=b1'
                        response = make_api_call('sendMessage', bot_token, params, context)
                        logging.info(f'{response=}; {user_id=}; context_step=b2')
                        result = process_response_of_api_call(user_id, response)
                        logging.info(f'{result=}; {user_id=}; context_step=b3')
                        inline_processing(response, params)
                    else:
                        # issue#425 show the inline keyboard

                        for i, region_keyboard in enumerate(keyboard):
                            if i == 0:
                                bot_message = """МЕНЮ АКТУАЛЬНЫХ ПОИСКОВ ДЛЯ ОТСЛЕЖИВАНИЯ.
Каждый поиск ниже дан строкой из пары кнопок: кнопка пометки для отслеживания и кнопка перехода на форум.
👀 - знак пометки поиска для отслеживания, уведомления будут приходить только по помеченным поискам. 
Если таких нет, то уведомления будут приходить по всем поискам согласно настройкам.
❌ - пометка поиска для игнорирования ("черный список") - уведомления по таким поискам не будут приходить в любом случае."""
                            else:
                                bot_message = ''

                            # Pop region caption from the region_keyboard and put it into bot-message
                            bot_message += '\n' if len(bot_message) > 0 else ''
                            bot_message += (
                                f'<a href="{region_keyboard[0][0]["url"]}">{region_keyboard[0][0]["text"]}</a>'
                            )
                            region_keyboard.pop(0)

                            if i == (len(keyboard) - 1):
                                region_keyboard += [
                                    [
                                        {
                                            'text': 'Отключить выбор поисков для отслеживания',
                                            'callback_data': '{"action":"search_follow_mode_off"}',
                                        }
                                    ]
                                ]

                            reply_markup = InlineKeyboardMarkup(region_keyboard)
                            logging.info(f'{bot_message=}; {region_keyboard=}; context_step=b00')
                            # process_sending_message_async(user_id=user_id, data=data)
                            context = f'Before if reply_markup and not isinstance(reply_markup, dict): {reply_markup=}, context_step=b01'
                            logging.info(f'{context=}: {reply_markup=}')
                            if reply_markup and not isinstance(reply_markup, dict):
                                reply_markup = reply_markup.to_dict()
                                context = (
                                    f'After reply_markup.to_dict(): {reply_markup=}; {user_id=}; context_step=b02a'
                                )
                                logging.info(f'{context=}: {reply_markup=}')

                            params = {
                                'parse_mode': 'HTML',
                                'disable_web_page_preview': True,
                                'reply_markup': reply_markup,
                                'chat_id': user_id,
                                'text': bot_message,
                            }
                            context = f'{user_id=}, context_step=b03'
                            response = make_api_call('sendMessage', bot_token, params, context)
                            logging.info(f'{response=}; {user_id=}; context_step=b04')
                            result = process_response_of_api_call(user_id, response)
                            logging.info(f'{result=}; {user_id=}; context_step=b05')
                            inline_processing(response, params)
                    ##msg_sent_by_specific_code for combined ikb end

                    # saving the last message from bot
                    try:
                        db().save_last_user_message_in_db(user_id, 'report')
                    except Exception as e:
                        logging.exception('failed to save the last message from bot')

                else:
                    region_name = ''
                    for region in user_regions:
                        for line in folders_list:
                            if line[0] == region:
                                region_name = line[1]
                                break

                        # check if region – is an archive folder: if so – it can be sent only to 'all'
                        if region_name.find('аверш') == -1 or temp_dict[got_message] == 'all':
                            bot_message = compose_full_message_on_list_of_searches(
                                temp_dict[got_message], user_id, region, region_name
                            )
                            reply_markup = reply_markup_main
                            data = {
                                'text': bot_message,
                                'reply_markup': reply_markup,
                                'parse_mode': 'HTML',
                                'disable_web_page_preview': True,
                            }
                            process_sending_message_async(user_id=user_id, data=data)

                            # saving the last message from bot
                            try:
                                db().save_last_user_message_in_db(user_id, 'report')
                            except Exception as e:
                                logging.exception('failed to save the last message from bot')

                    # issue425 Button for turn on search following mode
                    if 'tester' in db().get_user_sys_roles(user_id):
                        try:
                            search_follow_mode_ikb = [
                                [
                                    {
                                        'text': 'Включить выбор поисков для отслеживания',
                                        'callback_data': '{"action":"search_follow_mode_on"}',
                                    }
                                ]
                            ]
                            reply_markup = InlineKeyboardMarkup(search_follow_mode_ikb)
                            if reply_markup and not isinstance(reply_markup, dict):
                                reply_markup = reply_markup.to_dict()
                                context = f'After reply_markup.to_dict(): {reply_markup=}; {user_id=}; context_step=a00'
                                logging.info(f'{context=}: {reply_markup=}')
                            params = {
                                'parse_mode': 'HTML',
                                'disable_web_page_preview': True,
                                'reply_markup': reply_markup,
                                'chat_id': user_id,
                                'text': """Вы можете включить возможность выбора поисков для отслеживания, 
    чтобы получать уведомления не со всех актуальных поисков, 
    а только с выбранных Вами.""",
                            }
                            context = f'{user_id=}, context_step=a01'
                            response = make_api_call('sendMessage', bot_token, params, context)
                            logging.info(f'{response=}; {user_id=}; context_step=a02')
                            result = process_response_of_api_call(user_id, response)
                            logging.info(f'{result=}; {user_id=}; context_step=a03')
                            inline_processing(response, params)
                        except Exception as e:
                            logging.exception('failed to show button for turn on search following mode')

            # Perform individual replies

            # FIXME - WIP
            elif got_message.lower() in {
                b_admin_menu,
                b_test_menu,
                'notest',
                b_test_search_follow_mode_on,
                b_test_search_follow_mode_off,
            }:
                bot_message, reply_markup = handle_admin_experimental_settings(
                    user_id, got_message, b_test_menu, b_test_search_follow_mode_on, b_test_search_follow_mode_off
                )

            elif got_message in {b_map, Commands.c_map}:
                bot_message, reply_markup = handle_show_map()

            elif (
                got_message == b.set.topic_type.text
                or b.topic_types.contains(got_message)
                or (got_hash and b.topic_types.contains(got_hash))
            ):  # noqa
                callback_query_message_id = callback_query.message.id if callback_query else None
                bot_message, reply_markup = manage_topic_type(
                    user_id, got_message, b, got_callback, callback_query_id, bot_token, callback_query_message_id
                )

            elif got_message in {MainSettingsMenu.b_set_pref_age, *age_buttons}:
                bot_message, reply_markup = handle_age_settings(user_id, got_message)

            elif (
                got_message in {MainSettingsMenu.b_set_pref_radius, *DistanceSettings.list()}
                or bot_request_bfr_usr_msg == 'radius_input'
            ):
                bot_message, reply_markup, bot_request_aft_usr_msg = manage_radius(
                    user_id,
                    got_message,
                    MainSettingsMenu.b_set_pref_radius,
                    DistanceSettings.b_pref_radius_act,
                    DistanceSettings.b_pref_radius_deact,
                    DistanceSettings.b_pref_radius_change,
                    b_back_to_start,
                    MainSettingsMenu.b_set_pref_coords,
                    bot_request_bfr_usr_msg,
                )

            elif (
                got_message in {MainSettingsMenu.b_set_forum_nick, b_yes_its_me, b_no_its_not_me}
                or bot_request_bfr_usr_msg == 'input_of_forum_username'
            ):
                bot_message, reply_markup, bot_request_aft_usr_msg = manage_linking_to_forum(
                    got_message,
                    user_id,
                    MainSettingsMenu.b_set_forum_nick,
                    b_back_to_start,
                    bot_request_bfr_usr_msg,
                    b_admin_menu,
                    b_test_menu,
                    b_yes_its_me,
                    b_no_its_not_me,
                    b_settings,
                    reply_markup_main,
                )

            # DEBUG: for debugging purposes only
            elif got_message.lower() == 'go':
                publish_to_pubsub(Topics.topic_notify_admin, 'test_admin_check')

            elif got_message in {b_other, Commands.c_other}:
                bot_message = (
                    'Здесь можно посмотреть статистику по 20 последним поискам, перейти в '
                    'канал Коммъюнити или Прочитать важную информацию для Новичка и посмотреть '
                    'душевные фото с поисков'
                )
                keyboard_other = [
                    [b_view_latest_searches],
                    [b_goto_first_search],
                    [b_goto_community],
                    [b_goto_photos],
                    [b_back_to_start],
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)

            elif got_message in {b_menu_set_region, b_fed_dist_pick_other}:
                bot_message = update_and_download_list_of_regions(
                    user_id, got_message, b_menu_set_region, b_fed_dist_pick_other
                )
                reply_markup = ReplyKeyboardMarkup(keyboard_fed_dist_set, resize_keyboard=True)

            elif got_message in dict_of_fed_dist:
                updated_regions = update_and_download_list_of_regions(
                    user_id, got_message, b_menu_set_region, b_fed_dist_pick_other
                )
                bot_message = updated_regions
                reply_markup = ReplyKeyboardMarkup(dict_of_fed_dist[got_message], resize_keyboard=True)

            elif got_message in full_dict_of_regions:
                updated_regions = update_and_download_list_of_regions(
                    user_id, got_message, b_menu_set_region, b_fed_dist_pick_other
                )
                bot_message = updated_regions
                keyboard = keyboard_fed_dist_set
                for fed_dist in dict_of_fed_dist:
                    for region in dict_of_fed_dist[fed_dist]:
                        if region[0] == got_message:
                            keyboard = dict_of_fed_dist[fed_dist]
                            break
                    else:
                        continue
                    break
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                if onboarding_step_id == 20:  # "moscow_replied"
                    save_onboarding_step(user_id, username, 'region_set')
                    db().save_user_pref_topic_type(user_id, 'default', user_role)

            elif got_message in {b_settings, Commands.c_settings}:
                bot_message, reply_markup = handle_main_settings(user_id)

            elif got_message in {
                MainSettingsMenu.b_set_pref_coords,
                CoordinateSettingsMenu.b_coords_del,
                CoordinateSettingsMenu.b_coords_man_def,
                CoordinateSettingsMenu.b_coords_check,
            }:
                bot_message, reply_markup, bot_request_aft_usr_msg = handle_coordinates(user_id, got_message)

            elif got_message == b_back_to_start:
                bot_message = 'возвращаемся в главное меню'
                reply_markup = reply_markup_main

            elif got_message == b_goto_community:
                bot_message, reply_markup = handle_goto_community()

            elif got_message == b_goto_first_search:
                bot_message, reply_markup = handle_goto_first_search()

            elif got_message == b_goto_photos:
                bot_message, reply_markup = handle_goto_photos()

            # special block for flexible menu on notification preferences
            elif got_message in {
                b_act_titles,
                MainSettingsMenu.b_set_pref_notif_type,
                *NotificationSettingsMenu.list(),
            }:
                # save preference for +ALL
                bot_message, reply_markup = handle_notification_settings(got_message, user_id)

            # in case of other user messages:
            else:
                # If command in unknown
                bot_message = 'не понимаю такой команды, пожалуйста, используйте кнопки со стандартными командами ниже'
                reply_markup = reply_markup_main

            if not msg_sent_by_specific_code:
                # FIXME – 17.11.2023 – migrating from async to pure api call
                """
                admin_id = get_app_config().my_telegram_id
                if user_id != admin_id:
                    data = {'text': bot_message, 'reply_markup': reply_markup,
                            'parse_mode': 'HTML', 'disable_web_page_preview': True}
                    process_sending_message_async(user_id=user_id, data=data)
                else:"""

                _reply_to_user(bot_token, user_id, got_callback, callback_query, got_hash, reply_markup, bot_message)
                # FIXME ^^^

            # saving the last message from bot
            if not bot_request_aft_usr_msg:
                bot_request_aft_usr_msg = 'not_defined'

            try:
                db().save_last_user_message_in_db(user_id, bot_request_aft_usr_msg)
            except Exception as e:
                logging.exception(f'failed updates of table msg_from_bot for user={user_id}')

        # all other cases when bot was not able to understand the message from user
        else:
            logging.info('DBG.C.6. THERE IS a COMM SCRIPT INVOCATION w/O MESSAGE:')
            logging.info(str(update))
            text_for_admin = (
                f'[comm]: Empty message in Comm, user={user_id}, username={username}, '
                f'got_message={got_message}, update={update}, '
                f'bot_request_bfr_usr_msg={bot_request_bfr_usr_msg}'
            )
            logging.info(text_for_admin)
            notify_admin(text_for_admin)

    except Exception as e:
        logging.exception('GENERAL COMM CRASH:')
        notify_admin('[comm] general script fail')

    if bot_message:
        db().save_bot_reply_to_user(user_id, bot_message)

    return 'finished successfully. in was a regular conversational message'
