# ToDo later: user_callback["action"] == "search_follow_mode" заменить на "sfmw", "sfmb"

"""receives telegram messages from users, acts accordingly and sends back the reply"""

import datetime
import logging
import re
from typing import Tuple, Union

import requests
from flask import Request
from telegram import (
    Bot,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
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
    NotificationSettingsMenu,
    RoleChoice,
    MainSettingsMenu,
    b_act_titles,
    b_back_to_start,
    b_coords_auto_def,
    b_coords_check,
    b_coords_del,
    b_coords_man_def,
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
    b_pref_urgency_high,
    b_pref_urgency_highest,
    b_pref_urgency_low,
    b_pref_urgency_medium,
    b_reg_moscow,
    b_reg_not_moscow,
    b_settings,
    b_view_act_searches,
    b_view_latest_searches,
    b_yes_its_me,
    c_start,
    dict_of_fed_dist,
    fed_okr_dict,
    folder_dict,
    full_dict_of_regions,
    keyboard_fed_dist_set,
    reply_markup_main,
)
from communicate._utils.common import AllButtons, save_onboarding_step
from communicate._utils.compose_messages import (
    compose_full_message_on_list_of_searches,
    compose_full_message_on_list_of_searches_ikb,
    compose_msg_on_user_setting_fullness,
)
from communicate._utils.database import db
from communicate._utils.handlers import (
    get_default_age_period_list,
    handle_notification_settings,
    manage_age,
    manage_if_moscow,
    manage_linking_to_forum,
    manage_radius,
    manage_search_follow_mode,
    manage_search_whiteness,
    manage_topic_type,
)
from communicate._utils.message_sending import (
    make_api_call,
    process_leaving_chat_async,
    process_response_of_api_call,
)

setup_google_logging()

# To get rid of telegram "Retrying" Warning logs, which are shown in GCP Log Explorer as Errors.
# Important – these are not errors, but jest informational warnings that there were retries, that's why we exclude them
logging.getLogger('telegram.vendor.ptb_urllib3.urllib3').setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


standard_modifier = {'on': '✅ ', 'off': '☐ '}
full_buttons_dict = {
    'topic_types': {
        'regular': {'text': 'стандартные активные поиски', 'id': 0},
        'resonance': {'text': 'резонансные поиски', 'id': 5, 'hide': False},
        'info_support': {'text': 'информационная поддержка', 'id': 4, 'hide': False},
        'reverse': {'text': 'обратные поиски', 'id': 1},
        'training': {'text': 'учебные поиски', 'id': 3},
        'patrol': {'text': 'ночной патруль', 'id': 2, 'hide': False},
        'event': {'text': 'мероприятия', 'id': 10},
        'info': {'text': 'полезная информация', 'id': 20, 'hide': True},
        'about': {'text': '💡 справка по типам поисков 💡', 'id': None},
    },
    'roles': {
        'member': {'text': 'я состою в ЛизаАлерт', 'id': 'member'},
        'new_member': {'text': 'я хочу помогать ЛизаАлерт', 'id': 'new_member'},
        'relative': {'text': 'я ищу человека', 'id': 'relative'},
        'other': {'text': 'у меня другая задача', 'id': 'other'},
        'no_answer': {'text': 'не хочу говорить', 'id': 'no_answer'},
        'about': {'text': '💡 справка по ролям 💡', 'id': None},
    },
    'set': {'topic_type': {'text': 'настроить вид поисков', 'id': 'topic_type'}},
    'core': {'to_start': {'text': 'в начало', 'id': 'to_start'}},
}


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


def generate_yandex_maps_place_link(lat: Union[float, str], lon: Union[float, str], param: str) -> str:
    """Compose a link to yandex map with the given coordinates"""

    coordinates_format = '{0:.5f}'

    if param == 'coords':
        display = str(coordinates_format.format(float(lat))) + ', ' + str(coordinates_format.format(float(lon)))
    else:
        display = 'Карта'

    msg = f'<a href="https://yandex.ru/maps/?pt={lon},{lat}&z=11&l=map">{display}</a>'

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


def get_basic_update_parameters(update: Update):
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

    return (
        user_new_status,
        timer_changed,
        photo,
        document,
        voice,
        contact,
        inline_query,
        sticker,
        user_latitude,
        user_longitude,
        got_message,
        channel_type,
        username,
        user_id,
        got_hash,
        got_callback,
        callback_query_id,
        callback_query,
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


def process_unneeded_messages(
    update, user_id, timer_changed, photo, document, voice, sticker, channel_type, contact, inline_query
):
    """process messages which are not a part of designed dialogue"""

    # CASE 2 – when user changed auto-delete setting in the bot
    if timer_changed:
        logging.info('user changed auto-delete timer settings')

    # CASE 3 – when user sends a PHOTO or attached DOCUMENT or VOICE message
    elif photo or document or voice or sticker:
        logging.debug('user sends photos to bot')

        bot_message = (
            'Спасибо, интересное! Однако, бот работает только с текстовыми командами. '
            'Пожалуйста, воспользуйтесь текстовыми кнопками бота, находящимися на '
            'месте обычной клавиатуры телеграм.'
        )
        data = {'text': bot_message}
        process_sending_message_async(user_id=user_id, data=data)

    # CASE 4 – when some Channel writes to bot
    elif channel_type and user_id < 0:
        notify_admin('[comm]: INFO: CHANNEL sends messages to bot!')

        try:
            process_leaving_chat_async(user_id)
            notify_admin(f'[comm]: INFO: we have left the CHANNEL {user_id}')

        except Exception as e:
            logging.exception(f'[comm]: Leaving channel was not successful: {user_id}')
            notify_admin(f'[comm]: Leaving channel was not successful: {user_id}')

    # CASE 5 – when user sends Contact
    elif contact:
        bot_message = (
            'Спасибо, буду знать. Вот только бот не работает с контактами и отвечает '
            'только на определенные текстовые команды.'
        )
        data = {'text': bot_message}
        process_sending_message_async(user_id=user_id, data=data)

    # CASE 6 – when user mentions bot as @LizaAlert_Searcher_Bot in another telegram chat. Bot should do nothing
    elif inline_query:
        notify_admin('[comm]: User mentioned bot in some chats')
        logging.info(f'bot was mentioned in other chats: {update}')


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


def get_coordinates_from_string(got_message: str, lat_placeholder, lon_placeholder) -> Tuple[float, float]:
    """gets coordinates from string"""

    user_latitude, user_longitude = None, None
    # Check if user input is in format of coordinates
    # noinspection PyBroadException
    try:
        numbers = [float(s) for s in re.findall(r'-?\d+\.?\d*', got_message)]
        if numbers and len(numbers) > 1 and 30 < numbers[0] < 80 and 10 < numbers[1] < 190:
            user_latitude = numbers[0]
            user_longitude = numbers[1]
    except Exception:
        logging.info(f'manual coordinates were not identified from string {got_message}')

    if not (user_latitude and user_longitude):
        user_latitude = lat_placeholder
        user_longitude = lon_placeholder

    return user_latitude, user_longitude


def process_user_coordinates(
    user_id: int,
    user_latitude: float,
    user_longitude: float,
    b_coords_check: str,
    b_coords_del: str,
    b_back_to_start: str,
    bot_request_aft_usr_msg: str,
) -> None:
    """process coordinates which user sent to bot"""

    db().save_user_coordinates(user_id, user_latitude, user_longitude)

    bot_message = 'Ваши "домашние координаты" сохранены:\n'
    bot_message += generate_yandex_maps_place_link(user_latitude, user_longitude, 'coords')
    bot_message += (
        '\nТеперь для всех поисков, где удастся распознать координаты штаба или '
        'населенного пункта, будет указываться направление и расстояние по '
        'прямой от ваших "домашних координат".'
    )

    keyboard_settings = [[b_coords_check], [b_coords_del], [b_back_to_start]]
    reply_markup = ReplyKeyboardMarkup(keyboard_settings, resize_keyboard=True)

    data = {'text': bot_message, 'reply_markup': reply_markup, 'parse_mode': 'HTML', 'disable_web_page_preview': True}
    process_sending_message_async(user_id=user_id, data=data)
    # msg_sent_by_specific_code = True

    # saving the last message from bot
    if not bot_request_aft_usr_msg:
        bot_request_aft_usr_msg = 'not_defined'

    try:
        db().save_last_user_message_in_db(user_id, bot_request_aft_usr_msg)

    except Exception as e:
        logging.exception('failed to update the last saved message from bot')

    db().save_bot_reply_to_user(user_id, bot_message)


def run_onboarding(user_id: int, username: str, onboarding_step_id: int, got_message: str) -> int:
    """part of the script responsible for orchestration of activities for non-finally-onboarded users"""

    if onboarding_step_id == 21:  # region_set
        # mark that onboarding is finished
        if got_message:
            save_onboarding_step(user_id, username, 'finished')
            onboarding_step_id = 80

    return onboarding_step_id


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

    (
        user_new_status,
        timer_changed,
        photo,
        document,
        voice,
        contact,
        inline_query,
        sticker,
        user_latitude,
        user_longitude,
        got_message,
        channel_type,
        username,
        user_id,
        got_hash,
        got_callback,
        callback_query_id,
        callback_query,
    ) = get_basic_update_parameters(update)

    logging.info(f'after get_basic_update_parameters:  {got_callback=}')

    if (
        timer_changed
        or photo
        or document
        or voice
        or sticker
        or (channel_type and user_id < 0)
        or contact
        or inline_query
    ):
        process_unneeded_messages(
            update, user_id, timer_changed, photo, document, voice, sticker, channel_type, contact, inline_query
        )
        return 'finished successfully. it was useless message for bot'

    if user_new_status in {'kicked', 'member'}:
        process_block_unblock_user(user_id, user_new_status)
        return 'finished successfully. it was a system message on bot block/unblock'

    b = AllButtons(full_buttons_dict)

    # Admin - specially keep it for Admin, regular users unlikely will be interested in it

    b_admin_menu = 'admin'
    b_test_menu = 'test'
    b_test_search_follow_mode_on = 'test search follow mode on'  # noqa
    b_test_search_follow_mode_off = 'test search follow mode off'

    age_buttons = []
    for period in get_default_age_period_list():
        age_buttons.append(f'отключить: {period.description}')
        age_buttons.append(f'включить: {period.description}')

    b_pref_radius_act = 'включить ограничение по расстоянию'
    b_pref_radius_deact = 'отключить ограничение по расстоянию'
    b_pref_radius_change = 'изменить ограничение по расстоянию'

    b_help_yes = 'да, помогите мне настроить бот'
    b_help_no = 'нет, помощь не требуется'

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
        process_user_coordinates(
            user_id,
            user_latitude,
            user_longitude,
            b_coords_check,
            b_coords_del,
            b_back_to_start,
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
                if got_message in RoleChoice.list():
                    user_role = db().save_user_pref_role(user_id, got_message)
                    save_onboarding_step(user_id, username, 'role_set')

                # get user role = relatives looking for a person
                if got_message == RoleChoice.b_role_looking_for_person:
                    bot_message = (
                        'Тогда вам следует:\n\n'
                        '1. Подайте заявку на поиск в ЛизаАлерт ОДНИМ ИЗ ДВУХ способов:\n'
                        '  1.1. САМОЕ БЫСТРОЕ – звоните на 88007005452 (бесплатная горячая '
                        'линия ЛизаАлерт). Вам зададут ряд вопросов, который максимально '
                        'ускорит поиск, и посоветуют дальнейшие действия. \n'
                        '  1.2. Заполните форму поиска https://lizaalert.org/zayavka-na-poisk/ \n'
                        'После заполнения формы на сайте нужно ожидать звонка от ЛизаАлерт. На '
                        'обработку может потребоваться более часа. Если нет возможности ждать, '
                        'после заполнения заявки следует позвонить на горячую линию отряда '
                        '88007005452, сообщив, что вы уже оформили заявку на сайте.\n\n'
                        '2. Подать заявление в Полицию. Если иное не посоветовали на горячей линии,'
                        'заявка в Полицию – поможет ускорить и упростить поиск. Самый быстрый '
                        'способ – позвонить на 102.\n\n'
                        '3. Отслеживайте ход поиска.\n'
                        'Когда заявки в ЛизаАлерт и Полицию сделаны, отряд начнет первые '
                        'мероприятия для поиска человека: уточнение деталей, прозвоны '
                        'в госучреждения, формирование плана и команды поиска и т.п. Весь этот'
                        'процесс вам не будет виден, но часто люди находятся именно на этой стадии'
                        'поиска. Если первые меры не помогут и отряд примет решение проводить'
                        'выезд "на место поиска" – тогда вы сможете отслеживать ход поиска '
                        'через данный Бот, для этого продолжите настройку бота: вам нужно будет'
                        'указать ваш регион и выбрать, какие уведомления от бота вы будете '
                        'получать. '
                        'Как альтернатива, вы можете зайти на форум https://lizaalert.org/forum/, '
                        'и отслеживать статус поиска там.\n'
                        'Отряд сделает всё возможное, чтобы найти вашего близкого как можно '
                        'скорее.\n\n'
                        'Сообщите, подали ли вы заявки в ЛизаАлерт и Полицию?'
                    )

                    keyboard_orders = [[b_orders_done], [b_orders_tbd]]
                    reply_markup = ReplyKeyboardMarkup(keyboard_orders, resize_keyboard=True)

                # get user role = potential LA volunteer
                elif got_message == RoleChoice.b_role_want_to_be_la:
                    bot_message = (
                        'Супер! \n'
                        'Знаете ли вы, как можно помогать ЛизаАлерт? Определились ли вы, как '
                        'вы готовы помочь? Если еще нет – не беда – рекомендуем '
                        'ознакомиться со статьёй: '
                        'https://takiedela.ru/news/2019/05/25/instrukciya-liza-alert/\n\n'
                        'Задачи, которые можно выполнять даже без специальной подготовки, '
                        'выполняют Поисковики "на месте поиска". Этот Бот как раз старается '
                        'помогать именно Поисковикам. '
                        'Есть хороший сайт, рассказывающий, как начать участвовать в поиске: '
                        'https://lizaalert.org/dvizhenie/novichkam/\n\n'
                        'В случае любых вопросов – не стесняйтесь, обращайтесь на общий телефон, '
                        '8 800 700-54-52, где вам помогут с любыми вопросами при вступлении в отряд.\n\n'
                        'А если вы "из мира IT" и готовы помогать развитию этого Бота,'
                        'пишите нам в специальный чат https://t.me/+2J-kV0GaCgwxY2Ni\n\n'
                        'Надеемся, эта информацию оказалась полезной. '
                        'Если вы готовы продолжить настройку Бота, уточните, пожалуйста: '
                        'ваш основной регион – это Москва и Московская Область?'
                    )
                    keyboard_coordinates_admin = [[b_reg_moscow], [b_reg_not_moscow]]
                    reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)

                # get user role = all others
                elif got_message in {
                    RoleChoice.b_role_iam_la,
                    RoleChoice.b_role_other,
                    RoleChoice.b_role_secret,
                    b_orders_done,
                    b_orders_tbd,
                }:
                    bot_message = (
                        'Спасибо. Теперь уточните, пожалуйста, ваш основной регион – это '
                        'Москва и Московская Область?'
                    )
                    keyboard_coordinates_admin = [[b_reg_moscow], [b_reg_not_moscow]]
                    reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)

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

            elif got_message == b_help_no:
                bot_message = (
                    'Спасибо, понятно. Мы записали. Тогда бот более не будет вас беспокоить, '
                    'пока вы сами не напишите в бот.\n\n'
                    'На прощание, бот хотел бы посоветовать следующие вещи, делающие мир лучше:\n\n'
                    '1. Посмотреть <a href="https://t.me/+6LYNNEy8BeI1NGUy">позитивные фото '
                    'с поисков ЛизаАлерт</a>.\n\n'
                    '2. <a href="https://lizaalert.org/otryadnye-nuzhdy/">Помочь '
                    'отряду ЛизаАлерт, пожертвовав оборудование для поисков людей</a>.\n\n'
                    '3. Помочь создателям данного бота, присоединившись к группе разработчиков'
                    'или оплатив облачную инфраструктуру для бесперебойной работы бота. Для этого'
                    '<a href="https://t.me/MikeMikeT">просто напишите разработчику бота</a>.\n\n'
                    'Бот еще раз хотел подчеркнуть, что как только вы напишите что-то в бот – он'
                    'сразу же "забудет", что вы ранее просили вас не беспокоить:)\n\n'
                    'Обнимаем:)'
                )
                keyboard = [[b_back_to_start]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            elif got_message == b_help_yes:
                bot_message = (
                    'Супер! Тогда давайте посмотрим, что у вас не настроено.\n\n'
                    'У вас не настроен Регион поисков – без него Бот не может определить, '
                    'какие поиски вас интересуют. Вы можете настроить регион двумя способами:\n'
                    '1. Либо автоматически на основании ваших координат – нужно будет отправить '
                    'вашу геолокацию (работает только с мобильных устройств),\n'
                    '2. Либо выбрав регион вручную: для этого нужно сначала выбрать ФО = '
                    'Федеральный Округ, где находится ваш регион, а потом кликнуть на сам регион. '
                    '\n\n'
                )

            # set user pref: urgency
            elif got_message in {
                b_pref_urgency_highest,
                b_pref_urgency_high,
                b_pref_urgency_medium,
                b_pref_urgency_low,
            }:
                db().save_user_pref_urgency(
                    user_id,
                    got_message,
                    b_pref_urgency_highest,
                    b_pref_urgency_high,
                    b_pref_urgency_medium,
                    b_pref_urgency_low,
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

            # Admin mode
            elif got_message.lower() == b_admin_menu:
                bot_message = 'Вы вошли в специальный тестовый админ-раздел'

                # keyboard for Home Coordinates sharing
                keyboard_coordinates_admin = [[b_back_to_start], [b_back_to_start]]
                reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_admin, resize_keyboard=True)

            # FIXME - WIP
            elif got_message.lower() == b_test_menu:
                db().add_user_sys_role(user_id, 'tester')
                bot_message = (
                    'Вы в секретном тестовом разделе, где всё может работать не так :) '
                    'Если что – пишите, пожалуйста, в телеграм-чат '
                    'https://t.me/joinchat/2J-kV0GaCgwxY2Ni'
                    '\n💡 А еще Вам добавлена роль tester - некоторые тестовые функции включены автоматически.'
                    '\nДля отказа от роли tester нужно отправить команду notest'
                )
                # keyboard_coordinates_admin = [[b_set_topic_type], [b_back_to_start]]
                # [b_set_pref_urgency], [b_set_forum_nick]

                map_button = {'text': 'Открыть карту поисков', 'web_app': {'url': get_app_config().web_app_url_test}}
                keyboard = [[map_button]]
                reply_markup = InlineKeyboardMarkup(keyboard)
            # FIXME ^^^

            elif got_message.lower() == 'notest':
                db().delete_user_sys_role(user_id, 'tester')
                bot_message = 'Роль tester удалена. Приходите еще! :-) Возвращаемся в главное меню.'
                reply_markup = reply_markup_main

            elif got_message.lower() == b_test_search_follow_mode_on:  # issue425
                db().set_search_follow_mode(user_id, True)
                bot_message = 'Возможность отслеживания поисков включена. Возвращаемся в главное меню.'
                reply_markup = reply_markup_main

            elif got_message.lower() == b_test_search_follow_mode_off:  ##remains for some time for emrgency case
                db().set_search_follow_mode(user_id, False)
                bot_message = 'Возможность отслеживания поисков вЫключена. Возвращаемся в главное меню.'
                reply_markup = reply_markup_main

            elif got_message in {b_map, Commands.c_map}:
                bot_message = (
                    'В Боте Поисковика теперь можно посмотреть 🗺️Карту Поисков📍.\n\n'
                    'На карте вы сможете увидеть все активные поиски, '
                    'построить к каждому из них маршрут с учетом пробок, '
                    'а также открыть этот маршрут в сервисах Яндекс.\n\n'
                    'Карта работает в тестовом режиме.\n'
                    'Если карта будет работать некорректно, или вы видите, как ее необходимо '
                    'доработать – напишите в '
                    '<a href="https://t.me/joinchat/2J-kV0GaCgwxY2Ni">чат разработчиков</a>.'
                    ''
                )

                map_button = {'text': 'Открыть карту поисков', 'web_app': {'url': get_app_config().web_app_url}}
                keyboard = [[map_button]]
                reply_markup = InlineKeyboardMarkup(keyboard)

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
                input_data = None if got_message == MainSettingsMenu.b_set_pref_age else got_message
                keyboard, first_visit = manage_age(user_id, input_data)
                keyboard.append([b_back_to_start])
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

                if got_message.lower() == MainSettingsMenu.b_set_pref_age:
                    # TODO never True
                    bot_message = (
                        'Чтобы включить или отключить уведомления по определенной возрастной '
                        'группе, нажмите на неё. Настройку можно изменить в любой момент.'
                    )
                    if first_visit:
                        bot_message = (
                            'Данное меню позволяет выбрать возрастные категории БВП '
                            '(без вести пропавших), по которым вы хотели бы получать уведомления. '
                            'Важно, что если бот не сможет распознать возраст БВП, тогда вы '
                            'всё равно получите уведомление.\nТакже данная настройка не влияет на '
                            'разделы Актуальные Поиски и Последние Поиски – в них вы всё также '
                            'сможете увидеть полный список поисков.\n\n' + bot_message
                        )
                else:
                    bot_message = 'Спасибо, записали.'

            elif (
                got_message
                in {MainSettingsMenu.b_set_pref_radius, b_pref_radius_act, b_pref_radius_deact, b_pref_radius_change}
                or bot_request_bfr_usr_msg == 'radius_input'
            ):
                bot_message, reply_markup, bot_request_aft_usr_msg = manage_radius(
                    user_id,
                    got_message,
                    MainSettingsMenu.b_set_pref_radius,
                    b_pref_radius_act,
                    b_pref_radius_deact,
                    b_pref_radius_change,
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

            elif got_message == MainSettingsMenu.b_set_pref_urgency:
                bot_message = (
                    'Очень многие поисковики пользуются этим Ботом. При любой рассылке нотификаций'
                    ' Бот ставит все сообщения в очередь, и они обрабатываются '
                    'со скоростью, ограниченной технологиями Телеграма. Иногда, в случае нескольких'
                    ' больших поисков, очередь вырастает и кто-то получает сообщения практически '
                    'сразу, а кому-то они приходят с задержкой.\n'
                    'Вы можете помочь сделать рассылки уведомлений более "нацеленными", обозначив '
                    'с какой срочностью вы бы хотели получать уведомления от Бота. В скобках '
                    'указаны примерные сроки задержки относительно появления информации на форуме. '
                    'Выберите наиболее подходящий Вам вариант'
                )
                keyboard = [
                    [b_pref_urgency_highest],
                    [b_pref_urgency_high],
                    [b_pref_urgency_medium],
                    [b_pref_urgency_low],
                    [b_back_to_start],
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

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
                bot_message = (
                    'Это раздел с настройками. Здесь вы можете выбрать удобные для вас '
                    'уведомления, а также ввести свои "домашние координаты", на основе которых '
                    'будет рассчитываться расстояние и направление до места поиска. Вы в любой '
                    'момент сможете изменить эти настройки.'
                )

                message_prefix = compose_msg_on_user_setting_fullness(user_id)
                if message_prefix:
                    bot_message = f'{bot_message}\n\n{message_prefix}'

                keyboard_settings = [
                    [MainSettingsMenu.b_set_pref_notif_type],
                    [b_menu_set_region],
                    [MainSettingsMenu.b_set_topic_type],
                    [MainSettingsMenu.b_set_pref_coords],
                    [MainSettingsMenu.b_set_pref_radius],
                    [MainSettingsMenu.b_set_pref_age],
                    [MainSettingsMenu.b_set_forum_nick],
                    [b_back_to_start],
                ]  # #AK added b_set_forum_nick for issue #6
                reply_markup = ReplyKeyboardMarkup(keyboard_settings, resize_keyboard=True)

            elif got_message == MainSettingsMenu.b_set_pref_coords:
                bot_message = (
                    'АВТОМАТИЧЕСКОЕ ОПРЕДЕЛЕНИЕ координат работает только для носимых устройств'
                    ' (для настольных компьютеров – НЕ работает: используйте, пожалуйста, '
                    'кнопку ручного ввода координат). '
                    'При автоматическом определении координат – нажмите на кнопку и '
                    'разрешите определить вашу текущую геопозицию. '
                    'Координаты, загруженные вручную или автоматически, будут считаться '
                    'вашим "домом", откуда будут рассчитаны расстояние и '
                    'направление до поисков.'
                )
                keyboard_coordinates_1 = [
                    [b_coords_auto_def],
                    [b_coords_man_def],
                    [b_coords_check],
                    [b_coords_del],
                    [b_back_to_start],
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)

            elif got_message == b_coords_del:
                db().delete_user_coordinates(user_id)
                bot_message = (
                    'Ваши "домашние координаты" удалены. Теперь расстояние и направление '
                    'до поисков не будет отображаться.\n'
                    'Вы в любой момент можете заново ввести новые "домашние координаты". '
                    'Функция Автоматического определения координат работает только для '
                    'носимых устройств, для настольного компьютера – воспользуйтесь '
                    'ручным вводом.'
                )
                keyboard_coordinates_1 = [[b_coords_auto_def], [b_coords_man_def], [b_coords_check], [b_back_to_start]]
                reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)

            elif got_message == b_coords_man_def:
                bot_message = (
                    'Введите координаты вашего дома вручную в теле сообщения и просто '
                    'отправьте. Формат: XX.XXXХХ, XX.XXXХХ, где количество цифр после точки '
                    'может быть различным. Широта (первое число) должна быть между 30 '
                    'и 80, Долгота (второе число) – между 10 и 190.'
                )
                bot_request_aft_usr_msg = 'input_of_coords_man'
                reply_markup = ReplyKeyboardRemove()

            elif got_message == b_coords_check:
                lat, lon = db().show_user_coordinates(user_id)
                if lat and lon:
                    bot_message = 'Ваши "домашние координаты" '
                    bot_message += generate_yandex_maps_place_link(lat, lon, 'coords')

                else:
                    bot_message = 'Ваши координаты пока не сохранены. Введите их автоматически или вручную.'

                keyboard_coordinates_1 = [
                    [b_coords_auto_def],
                    [b_coords_man_def],
                    [b_coords_check],
                    [b_coords_del],
                    [b_back_to_start],
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard_coordinates_1, resize_keyboard=True)

            elif got_message == b_back_to_start:
                bot_message = 'возвращаемся в главное меню'
                reply_markup = reply_markup_main

            elif got_message == b_goto_community:
                bot_message = (
                    'Бот можно обсудить с соотрядниками в '
                    '<a href="https://t.me/joinchat/2J-kV0GaCgwxY2Ni">Специальном Чате '
                    'в телеграм</a>. Там можно предложить свои идеи, указать на проблемы '
                    'и получить быструю обратную связь от разработчика.'
                )
                keyboard_other = [
                    [b_view_latest_searches],
                    [b_goto_first_search],
                    [b_goto_photos],
                    [b_back_to_start],
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)

            elif got_message == b_goto_first_search:
                bot_message = (
                    'Если вы хотите стать добровольцем ДПСО «ЛизаАлерт», пожалуйста, '
                    '<a href="https://lizaalert.org/forum/viewtopic.php?t=56934">'
                    'посетите страницу форума</a>, там можно ознакомиться с базовой информацией '
                    'для новичков и задать свои вопросы.'
                    'Если вы готовитесь к своему первому поиску – приглашаем '
                    '<a href="https://lizaalert.org/dvizhenie/novichkam/">ознакомиться с основами '
                    'работы ЛА</a>. Всю теорию работы ЛА необходимо получать от специально '
                    'обученных волонтеров ЛА. Но если у вас еще не было возможности пройти '
                    'официальное обучение, а вы уже готовы выехать на поиск – этот ресурс '
                    'для вас.'
                )
                keyboard_other = [
                    [b_view_latest_searches],
                    [b_goto_community],
                    [b_goto_photos],
                    [b_back_to_start],
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)

            elif got_message == b_goto_photos:
                bot_message = (
                    'Если вам хочется окунуться в атмосферу ПСР, приглашаем в замечательный '
                    '<a href="https://t.me/+6LYNNEy8BeI1NGUy">телеграм-канал с красивыми фото с '
                    'поисков</a>. Все фото – сделаны поисковиками во время настоящих ПСР.'
                )
                keyboard_other = [
                    [b_view_latest_searches],
                    [b_goto_community],
                    [b_goto_first_search],
                    [b_back_to_start],
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard_other, resize_keyboard=True)

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
                bot_message = (
                    'не понимаю такой команды, пожалуйста, используйте кнопки со стандартными ' 'командами ниже'
                )
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

                context_step = '01a1'
                context = f'if reply_markup and not isinstance(reply_markup, dict): {reply_markup=}, {context_step=}'
                logging.info(f'{context=}: {reply_markup=}')
                if reply_markup and not isinstance(reply_markup, dict):
                    reply_markup = reply_markup.to_dict()
                    context_step = '02a1'
                    context = f'After reply_markup.to_dict(): {reply_markup=}, {context_step=}'
                    logging.info(f'{context=}: {reply_markup=}')

                if got_hash and got_callback and got_callback['action'] != 'about':
                    user_used_inline_button = True
                else:
                    user_used_inline_button = False

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
