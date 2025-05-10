import logging
import re

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)

from _dependencies.commons import add_tel_link, get_app_config
from _dependencies.pubsub import notify_admin

from ..buttons import (
    Commands,
    CoordinateSettingsMenu,
    DistanceSettings,
    HelpNeeded,
    IsMoscow,
    ItsMe,
    MainMenu,
    MainSettingsMenu,
    OrdersState,
    OtherOptionsMenu,
    RoleChoice,
    TopicTypeInlineKeyboardBuilder,
    b_admin_menu,
    b_back_to_start,
    b_coords_auto_def,
    b_fed_dist_pick_other,
    b_menu_set_region,
    b_test_menu,
    b_test_search_follow_mode_off,
    b_test_search_follow_mode_on,
    c_start,
    reply_markup_main,
)
from ..common import (
    LA_BOT_CHAT_URL,
    AgePeriod,
    HandlerResult,
    HandlerResultWithState,
    UpdateBasicParams,
    UpdateExtraParams,
    UserInputState,
    create_one_column_reply_markup,
    generate_yandex_maps_place_link,
    save_onboarding_step,
)
from ..database import db
from ..decorators import button_handler
from ..message_sending import tg_api
from ..regions import geography

WELCOME_MESSAGE_AFTER_ONBOARDING = (
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


@button_handler(buttons=['go'])
def handle_test_admin_check(update_params: UpdateBasicParams) -> HandlerResult:
    # DEBUG: for debugging purposes only
    notify_admin('test_admin_check')
    return '', reply_markup_main


@button_handler(buttons=[b_back_to_start])
def handle_back_to_main_menu(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    return 'возвращаемся в главное меню', reply_markup_main


@button_handler(buttons=[c_start])
def handle_command_start(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    if not extra_params.user_is_new:
        bot_message = 'Привет! Бот управляется кнопками, которые заменяют обычную клавиатуру.'
        return bot_message, reply_markup_main

    # FIXME – 02.12.2023 – hiding menu button for the newcomers
    #  (in the future it should be done in manage_user script)
    tg_api().set_my_commands(update_params.user_id, [], 'if user_is_new')
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
    reply_markup = create_one_column_reply_markup(RoleChoice.list())

    return bot_message, reply_markup


@button_handler(buttons=[MainMenu.b_other, Commands.c_other])
def handle_command_other(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    bot_message = (
        'Здесь можно посмотреть статистику по 20 последним поискам, перейти в '
        'канал Коммъюнити или Прочитать важную информацию для Новичка и посмотреть '
        'душевные фото с поисков'
    )
    keyboard_other = [
        OtherOptionsMenu.b_view_latest_searches,
        OtherOptionsMenu.b_goto_first_search,
        OtherOptionsMenu.b_goto_community,
        OtherOptionsMenu.b_goto_photos,
        b_back_to_start,
    ]
    return bot_message, create_one_column_reply_markup(keyboard_other)


def _update_and_download_list_of_regions(user_id: int, got_message: str) -> str:
    """Upload, download and compose a message on the list of user's regions"""

    # TODO - get the list of regions from PSQL
    # TODO ^^^

    # case for the first entry to the screen of Reg Settings
    if got_message == b_menu_set_region:
        pre_msg = (
            'Бот может показывать поиски в любом регионе работы ЛА.\n'
            'Вы можете подписаться на несколько регионов – просто кликните на соответствующие кнопки регионов.'
            '\nЧтобы ОТПИСАТЬСЯ от ненужных регионов – нажмите на соответствующую кнопку региона еще раз.\n\n'
        )
        pre_msg += 'Текущий список ваших регионов:'
        # Get the list of resulting regions
        msg = _get_user_selected_regions_text(user_id)
        return pre_msg + msg

    if got_message in geography.federal_district_names() or got_message == b_fed_dist_pick_other:
        msg = _get_user_selected_regions_text(user_id)
        if msg:
            return 'Текущий список ваших регионов:' + msg
        else:
            return 'Пока список выбранных регионов пуст. Выберите хотя бы один.'

    region_is_the_only = None
    region_was_in_db = None
    list_of_regs_to_upload = geography.folder_dict()[got_message]

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

    msg = _get_user_selected_regions_text(user_id)

    if region_is_the_only:
        msg = (
            'Ваш регион поисков настроен' + msg + '\n\nВы можете продолжить добавлять регионы, либо нажмите '
            'кнопку "в начало", чтобы продолжить работу с ботом.'
        )
    else:
        msg = (
            'Записали. Обновленный список ваших регионов:' + msg + '\n\nВы можете продолжить добавлять регионы, '
            'либо нажмите кнопку "в начало", чтобы '
            'продолжить работу с ботом.'
        )

    return msg


def _get_user_selected_regions_text(user_id: int) -> str:
    user_curr_regs_list = db().get_user_regions(user_id)

    rev_reg_dict = geography.reversed_folder_dict()
    msg: list[str] = []

    for user_region in user_curr_regs_list:
        if user_region in rev_reg_dict:
            msg.append(' &#8226; ' + rev_reg_dict[user_region])

    return '\n' + ',\n'.join(msg)


@button_handler(buttons=[b_menu_set_region, b_fed_dist_pick_other])
def handle_set_region(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    bot_message = _update_and_download_list_of_regions(update_params.user_id, update_params.got_message)
    reply_markup = ReplyKeyboardMarkup(geography.keyboard_federal_districts(), resize_keyboard=True)
    return bot_message, reply_markup


@button_handler(buttons=geography.all_federal_district_names())
def handle_message_is_district(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    updated_regions = _update_and_download_list_of_regions(update_params.user_id, update_params.got_message)
    # and there
    reply_markup = ReplyKeyboardMarkup(
        geography.get_keyboard_by_fed_district(update_params.got_message), resize_keyboard=True
    )
    return updated_regions, reply_markup


@button_handler(buttons=geography.all_region_names())
def handle_message_is_federal_region(
    update_params: UpdateBasicParams, extra_params: UpdateExtraParams
) -> HandlerResult:
    user_id = update_params.user_id
    got_message = update_params.got_message
    username = update_params.username

    if extra_params.onboarding_step_id == 20:
        # FIXME – 02.12.2023 – un-hiding menu button for the newcomers
        #  (in the future it should be done in manage_user script)

        user_role = db().get_user_role(user_id)
        tg_api().delete_my_commands(user_id)
        save_onboarding_step(user_id, username, 'region_set')
        db().save_user_pref_topic_type(user_id, user_role)

        keyboard_role = [
            MainSettingsMenu.b_set_pref_notif_type,
            MainSettingsMenu.b_set_pref_coords,
            MainSettingsMenu.b_set_pref_radius,
            MainSettingsMenu.b_set_pref_age,
            MainSettingsMenu.b_set_forum_nick,
            OtherOptionsMenu.b_view_latest_searches,
            MainMenu.b_view_act_searches,
            b_back_to_start,
        ]
        return WELCOME_MESSAGE_AFTER_ONBOARDING, create_one_column_reply_markup(keyboard_role)

    updated_regions = _update_and_download_list_of_regions(user_id, got_message)

    keyboard = geography.get_keyboard_by_region(got_message)

    return updated_regions, ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


@button_handler(
    buttons=[
        b_admin_menu,
        b_test_menu,
        'notest',
        b_test_search_follow_mode_on,
        b_test_search_follow_mode_off,
        'test msg 1',
        'test msg 2',
    ]
)
def handle_admin_experimental_settings(
    update_params: UpdateBasicParams, extra_params: UpdateExtraParams
) -> HandlerResult:
    # TODO split to separate handlers
    # FIXME - WIP
    got_message = update_params.got_message
    user_id = update_params.user_id

    # Admin mode
    if got_message.lower() == b_admin_menu:
        bot_message = 'Вы вошли в специальный тестовый админ-раздел'
        keyboard_coordinates_admin = [b_back_to_start, b_back_to_start]
        reply_markup = create_one_column_reply_markup(keyboard_coordinates_admin)
        return bot_message, reply_markup

    if got_message.lower() == b_test_menu:
        db().add_user_sys_role(user_id, 'tester')
        bot_message = (
            'Вы в секретном тестовом разделе, где всё может работать не так :) '
            'Если что – пишите, пожалуйста, в телеграм-чат '
            f'{LA_BOT_CHAT_URL}'
            '\n💡 А еще Вам добавлена роль tester - некоторые тестовые функции включены автоматически.'
            '\nДля отказа от роли tester нужно отправить команду notest'
        )

        map_button = InlineKeyboardButton(
            text='Открыть карту поисков', web_app=WebAppInfo(url=get_app_config().web_app_url_test)
        )

        keyboard = [[map_button]]
        return bot_message, InlineKeyboardMarkup(keyboard)

    if got_message.lower() == 'notest':
        db().delete_user_sys_role(user_id, 'tester')
        db().delete_search_whiteness(user_id)
        db().delete_search_follow_mode(user_id)
        bot_message = 'Роль tester удалена. Приходите еще! :-) Возвращаемся в главное меню.'
        return bot_message, reply_markup_main

    if got_message == 'test msg 1':
        bot_message = """Ответственные:\n &#8226; Инфорг: Арина (Арина) 89001234567 \n\n"""
        bot_message = add_tel_link(bot_message)
        return bot_message, reply_markup_main

    if got_message == 'test msg 2':
        bot_message = """🔀Изменения в первом посте по <a href="https://lizaalert.org/forum/viewtopic.php?t=94862">Иванов 33 года</a> (Москва и МО – Активные поиски):

➖Удалено:
<s>Координатор-консультант: Маркиза
СНМ: Дуглас
Инфорг: Герда (Арина) 89001234567 Написать Герда (Арина) в Telegram
</s>
➕Добавлено:
С 7 мая 2025 года нет данных о его местонахождении. 
рост 170 см,  худощавого телосложения, волосы седые, глаза карие.
Одежда: темно-синяя с лампасами на рукавах или темно-серая кофта, темно-синяя футболка, темно-синие брюки, темно-синие шлепанцы.
Внимание, выезд!
Штаб начинает работу 7 мая 2025 года в  23:00
Координаты штаба: <code>55.153047, 37.461095</code>
Адрес штаба: Московская обл, г Чехов, ул Московская, д 86
Форма одежды: город.  
Маркиза
Дуглас
Герда (Арина) 89001234567 """
        bot_message = add_tel_link(bot_message)
        return bot_message, reply_markup_main

    if got_message.lower() == b_test_search_follow_mode_on:  # issue425
        db().set_search_follow_mode(user_id, True)
        bot_message = 'Возможность отслеживания поисков включена. Возвращаемся в главное меню.'
        return bot_message, reply_markup_main

    if got_message.lower() == b_test_search_follow_mode_off:  ##remains for some time for emrgency case
        db().set_search_follow_mode(user_id, False)
        bot_message = 'Возможность отслеживания поисков вЫключена. Возвращаемся в главное меню.'
        return bot_message, reply_markup_main

    return 'Неизвестная команда', reply_markup_main


@button_handler(buttons=[MainMenu.b_map, Commands.c_map])
def handle_show_map(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    bot_message = (
        'В Боте Поисковика теперь можно посмотреть 🗺️Карту Поисков📍.\n\n'
        'На карте вы сможете увидеть все активные поиски, '
        'построить к каждому из них маршрут с учетом пробок, '
        'а также открыть этот маршрут в сервисах Яндекс.\n\n'
        'Карта работает в тестовом режиме.\n'
        'Если карта будет работать некорректно, или вы видите, как ее необходимо '
        'доработать – напишите в '
        f'<a href="{LA_BOT_CHAT_URL}">чат разработчиков</a>.'
        ''
    )

    map_button = InlineKeyboardButton(
        text='Открыть карту поисков', web_app=WebAppInfo(url=get_app_config().web_app_url)
    )

    keyboard = [[map_button]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    return bot_message, reply_markup


def _get_default_age_period_list() -> list[AgePeriod]:
    return [
        AgePeriod(description='Маленькие Дети 0-6 лет', name='0-6', min_age=0, max_age=6, order=0),
        AgePeriod(description='Подростки 7-13 лет', name='7-13', min_age=7, max_age=13, order=1),
        AgePeriod(description='Молодежь 14-20 лет', name='14-20', min_age=14, max_age=20, order=2),
        AgePeriod(description='Взрослые 21-50 лет', name='21-50', min_age=21, max_age=50, order=3),
        AgePeriod(description='Старшее Поколение 51-80 лет', name='51-80', min_age=51, max_age=80, order=4),
        AgePeriod(description='Старцы более 80 лет', name='80-on', min_age=80, max_age=120, order=5),
    ]


def _manage_age(user_id: int, got_message: str | None) -> tuple[list[list[str]], bool]:
    """Save user Age preference and generate the list of updated Are preferences"""

    if got_message:
        user_want_activate = bool(re.search(r'(?i)включить', got_message))
        user_new_setting = re.sub(r'.*чить: ', '', got_message)

        for line in _get_default_age_period_list():
            if user_new_setting == line.description:
                if user_want_activate:
                    db().save_user_age_prefs(user_id, line)
                else:
                    db().delete_user_age_pref(user_id, line)
                break

    return _get_user_age_prefs_params(user_id)


def _get_user_age_prefs_params(user_id: int) -> tuple[list[list[str]], bool]:
    # Block for Generating a list of Buttons
    age_list = _get_default_age_period_list()

    raw_list_of_periods = db().get_age_prefs(user_id)
    first_visit = False

    if raw_list_of_periods and str(raw_list_of_periods) != 'None':
        for line_raw in raw_list_of_periods:
            got_min, got_max = int(list(line_raw)[0]), int(list(line_raw)[1])
            for line_a in age_list:
                if int(line_a.min_age) == got_min and int(line_a.max_age) == got_max:
                    line_a.active = True
    else:
        first_visit = True
        for line in age_list:
            line.active = True
            db().save_user_age_prefs(user_id, line)

    list_of_buttons = []

    for line in age_list:
        button_text = f'отключить: {line.description}' if line.active else f'включить: {line.description}'
        list_of_buttons.append([button_text])

    return list_of_buttons, first_visit


def _get_age_buttons() -> list[str]:
    age_buttons = []
    for period in _get_default_age_period_list():
        age_buttons.append(f'отключить: {period.description}')
        age_buttons.append(f'включить: {period.description}')
    return age_buttons


@button_handler(buttons=[MainSettingsMenu.b_set_pref_age, *_get_age_buttons()])
def handle_age_settings(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    got_message = update_params.got_message
    input_data = None if got_message == MainSettingsMenu.b_set_pref_age else got_message
    keyboard, first_visit = _manage_age(update_params.user_id, input_data)
    keyboard.append([b_back_to_start])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    if got_message == MainSettingsMenu.b_set_pref_age:
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
    return bot_message, reply_markup


@button_handler(buttons=HelpNeeded.list())
def handle_help_needed(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    if update_params.got_message == HelpNeeded.b_help_no:
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
        keyboard = [b_back_to_start]
        return bot_message, create_one_column_reply_markup(keyboard)

    if update_params.got_message == HelpNeeded.b_help_yes:
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
        return bot_message, reply_markup_main

    return '', reply_markup_main


def _compose_msg_on_user_setting_fullness(user_id: int) -> str | None:
    """Create a text of message, which describes the degree on how complete user's profile is.
    More settings set – more complete profile it. It's done to motivate users to set the most tailored settings."""

    if not user_id:
        return None

    settings_summary = db().get_user_settings_summary(user_id)

    if not settings_summary:
        return None

    list_of_settings = [
        settings_summary.pref_notif_type,
        settings_summary.pref_region_old,
        settings_summary.pref_coords,
        settings_summary.pref_radius,
        settings_summary.pref_age,
        settings_summary.pref_forum,
    ]
    user_score = int(round(sum(list_of_settings) / len(list_of_settings) * 100, 0))

    logging.info(f'List of user settings activation: {list_of_settings=}')
    logging.info(f'User settings completeness score is {user_score}')

    if user_score == 100:
        return None

    user_score_emoji = (
        f'{user_score // 10}\U0000fe0f\U000020e3{user_score - (user_score // 10) * 10}\U0000fe0f\U000020e3'
    )
    message_parts = [
        f'Вы настроили бот на {user_score_emoji}%.',
        '',
        'Чтобы сделать бот максимально эффективным именно для вас, рекомендуем настроить следующие параметры:',
    ]
    if not settings_summary.pref_notif_type:
        message_parts.append(' - Тип уведомлений,')
    if not settings_summary.pref_region_old:
        message_parts.append(' - Регион,')
    if not settings_summary.pref_coords:
        message_parts.append(' - Домашние координаты,')
    if not settings_summary.pref_radius:
        message_parts.append(' - Максимальный радиус,')
    if not settings_summary.pref_age:
        message_parts.append(' - Возрастные группы БВП,')
    if not settings_summary.pref_forum:
        message_parts.append(' - Связать бот с форумом ЛА,')

    return '\n'.join(message_parts)


@button_handler(buttons=[MainMenu.b_settings, Commands.c_settings])
def handle_main_settings(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    bot_message = (
        'Это раздел с настройками. Здесь вы можете выбрать удобные для вас '
        'уведомления, а также ввести свои "домашние координаты", на основе которых '
        'будет рассчитываться расстояние и направление до места поиска. Вы в любой '
        'момент сможете изменить эти настройки.'
    )

    message_prefix = _compose_msg_on_user_setting_fullness(update_params.user_id)
    if message_prefix:
        bot_message = f'{bot_message}\n\n{message_prefix}'

    keyboard = [
        MainSettingsMenu.b_set_pref_notif_type,
        b_menu_set_region,
        MainSettingsMenu.b_set_topic_type,
        MainSettingsMenu.b_set_pref_coords,
        MainSettingsMenu.b_set_pref_radius,
        MainSettingsMenu.b_set_pref_age,
        MainSettingsMenu.b_set_forum_nick,
        b_back_to_start,
    ]  # #AK added b_set_forum_nick for issue #6
    return bot_message, create_one_column_reply_markup(keyboard)


@button_handler(buttons=[MainSettingsMenu.b_set_topic_type])
def handle_topic_type_show_menu(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    """Save user Topic Type preference and generate the actual topic type preference message"""

    # when user just enters the MENU for topic types
    bot_message = (
        'Вы можете выбрать и в любой момент поменять, по каким типам поисков или '
        'мероприятий бот должен присылать уведомления.'
    )

    list_of_current_setting_ids = db().check_saved_topic_types(update_params.user_id)

    keyboard = TopicTypeInlineKeyboardBuilder.get_keyboard(list_of_current_setting_ids, [])
    reply_markup = InlineKeyboardMarkup(keyboard)

    return bot_message, reply_markup


@button_handler(buttons=IsMoscow.b_reg_not_moscow.list())
def handle_if_moscow(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    """act if user replied either user from Moscow region or from another one"""

    got_message = update_params.got_message
    user_id = update_params.user_id
    username = update_params.username

    if got_message == IsMoscow.b_reg_moscow:
        save_onboarding_step(user_id, username, 'moscow_replied')
        save_onboarding_step(user_id, username, 'region_set')
        user_role = db().get_user_role(user_id)
        db().save_user_pref_topic_type(user_id, user_role)

        if db().check_if_user_has_no_regions(user_id):
            # add the New User into table user_regional_preferences
            # region is Moscow for Active Searches & InfoPod
            db().add_folder_to_user_regional_preference(user_id, 276)
            db().add_folder_to_user_regional_preference(user_id, 41)
            db().add_region_to_user_settings(user_id, 1)

        return WELCOME_MESSAGE_AFTER_ONBOARDING, reply_markup_main

    if got_message == IsMoscow.b_reg_not_moscow:
        save_onboarding_step(user_id, username, 'moscow_replied')

        bot_message = (
            'Спасибо, тогда для корректной работы Бота, пожалуйста, выберите свой регион: '
            'сначала обозначьте Федеральный Округ, '
            'а затем хотя бы один Регион поисков, чтобы отслеживать поиски в этом регионе. '
            'Вы в любой момент сможете изменить '
            'список регионов через настройки бота.'
        )
        reply_markup = ReplyKeyboardMarkup(geography.keyboard_federal_districts(), resize_keyboard=True)
        return bot_message, reply_markup

    return bot_message, reply_markup_main


@button_handler(buttons=[MainSettingsMenu.b_set_pref_radius])
def handle_radius_menu_show(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    """Show menu for radius setting"""

    saved_radius = db().check_saved_radius(update_params.user_id)
    if saved_radius:
        list_of_buttons = [
            DistanceSettings.b_pref_radius_change,
            DistanceSettings.b_pref_radius_deact,
            MainSettingsMenu.b_set_pref_coords,
            b_back_to_start,
        ]
        bot_message = (
            f'Сейчас вами установлено ограничение радиуса {saved_radius} км. '
            f'Вы в любой момент можете изменить или снять это ограничение.\n\n'
            'ВАЖНО! Вы всё равно будете проинформированы по всем поискам, по которым '
            'Бот не смог распознать никакие координаты.\n\n'
            'Также, бот в первую очередь '
            'проверяет расстояние от штаба, а если он не указан, то до ближайшего '
            'населенного пункта (или топонима), указанного в теме поиска. '
            'Расстояние считается по прямой.'
        )
    else:
        list_of_buttons = [
            DistanceSettings.b_pref_radius_act,
            MainSettingsMenu.b_set_pref_coords,
            b_back_to_start,
        ]
        bot_message = (
            'Данная настройка позволяет вам ограничить уведомления от бота только теми поисками, '
            'для которых расстояние от ваших "домашних координат" до штаба/города '
            'не превышает указанного вами Радиуса.\n\n'
            'ВАЖНО! Вы всё равно будете проинформированы по всем поискам, по которым '
            'Бот не смог распознать никакие координаты.\n\n'
            'Также, Бот в первую очередь '
            'проверяет расстояние от штаба, а если он не указан, то до ближайшего '
            'населенного пункта (или топонима), указанного в теме поиска. '
            'Расстояние считается по прямой.'
        )
    return bot_message, create_one_column_reply_markup(list_of_buttons)


@button_handler(buttons=[*DistanceSettings.list()])
def handle_radius_menu(
    update_params: UpdateBasicParams, extra_params: UpdateExtraParams
) -> tuple[str, ReplyKeyboardMarkup | ReplyKeyboardRemove, UserInputState | None]:
    """Save user Radius preference and generate the actual radius preference"""

    if update_params.got_message in {DistanceSettings.b_pref_radius_act, DistanceSettings.b_pref_radius_change}:
        saved_radius = db().check_saved_radius(update_params.user_id)
        if saved_radius:
            bot_message = (
                f'У вас установлено максимальное расстояние до поиска {saved_radius}.'
                f'\n\nВведите обновлённое расстояние в километрах по прямой в формате простого '
                f'числа (например: 150) и нажмите обычную кнопку отправки сообщения'
            )
        else:
            bot_message = (
                'Введите расстояние в километрах по прямой в формате простого числа '
                '(например: 150) и нажмите обычную кнопку отправки сообщения'
            )
        return bot_message, ReplyKeyboardRemove(), UserInputState.radius_input

    else:
        list_of_buttons = [
            DistanceSettings.b_pref_radius_act,
            MainSettingsMenu.b_set_pref_radius,
            b_back_to_start,
        ]
        db().delete_user_saved_radius(update_params.user_id)
        bot_message = 'Ограничение на расстояние по поискам снято!'
        return bot_message, create_one_column_reply_markup(list_of_buttons), None


@button_handler(buttons=[*RoleChoice.list(), OrdersState.b_orders_done, OrdersState.b_orders_tbd])
def handle_user_role(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    got_message = update_params.got_message
    user_id = update_params.user_id
    username = update_params.username

    if got_message in RoleChoice.list():
        db().save_user_pref_role(user_id, got_message)
        save_onboarding_step(user_id, username, 'role_set')

    if got_message == RoleChoice.b_role_looking_for_person:
        # get user role = relatives looking for a person
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

        keyboard_orders = [OrdersState.b_orders_done, OrdersState.b_orders_tbd]
        return bot_message, create_one_column_reply_markup(keyboard_orders)

    if got_message == RoleChoice.b_role_want_to_be_la:
        # get user role = potential LA volunteer
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
        keyboard_coordinates_admin = [IsMoscow.b_reg_moscow, IsMoscow.b_reg_not_moscow]
        return bot_message, create_one_column_reply_markup(keyboard_coordinates_admin)

    # all other cases
    bot_message = 'Спасибо. Теперь уточните, пожалуйста, ваш основной регион – это ' 'Москва и Московская Область?'
    keyboard_coordinates_admin = [IsMoscow.b_reg_moscow, IsMoscow.b_reg_not_moscow]
    return bot_message, create_one_column_reply_markup(keyboard_coordinates_admin)


@button_handler(buttons=[OtherOptionsMenu.b_goto_photos])
def handle_goto_photos(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    bot_message = (
        'Если вам хочется окунуться в атмосферу ПСР, приглашаем в замечательный '
        '<a href="https://t.me/+6LYNNEy8BeI1NGUy">телеграм-канал с красивыми фото с '
        'поисков</a>. Все фото – сделаны поисковиками во время настоящих ПСР.'
    )
    keyboard = [
        OtherOptionsMenu.b_view_latest_searches,
        OtherOptionsMenu.b_goto_community,
        OtherOptionsMenu.b_goto_first_search,
        b_back_to_start,
    ]
    return bot_message, create_one_column_reply_markup(keyboard)


@button_handler(buttons=[OtherOptionsMenu.b_goto_first_search])
def handle_goto_first_search(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
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
    keyboard = [
        OtherOptionsMenu.b_view_latest_searches,
        OtherOptionsMenu.b_goto_community,
        OtherOptionsMenu.b_goto_photos,
        b_back_to_start,
    ]
    return bot_message, create_one_column_reply_markup(keyboard)


@button_handler(buttons=[OtherOptionsMenu.b_goto_community])
def handle_goto_community(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    bot_message = (
        'Бот можно обсудить с соотрядниками в '
        f'<a href="{LA_BOT_CHAT_URL}">Специальном Чате '
        'в телеграм</a>. Там можно предложить свои идеи, указать на проблемы '
        'и получить быструю обратную связь от разработчика.'
    )
    keyboard = [
        OtherOptionsMenu.b_view_latest_searches,
        OtherOptionsMenu.b_goto_first_search,
        OtherOptionsMenu.b_goto_photos,
        b_back_to_start,
    ]
    return bot_message, create_one_column_reply_markup(keyboard)


@button_handler(buttons=[MainSettingsMenu.b_set_pref_coords])
def handle_coordinates_show_menu(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
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
    keyboard: list[str | KeyboardButton] = [
        b_coords_auto_def,
        CoordinateSettingsMenu.b_coords_man_def,
        CoordinateSettingsMenu.b_coords_check,
        CoordinateSettingsMenu.b_coords_del,
        b_back_to_start,
    ]
    return bot_message, create_one_column_reply_markup(keyboard)


@button_handler(buttons=[CoordinateSettingsMenu.b_coords_del])
def handle_coordinates_delete(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    db().delete_user_coordinates(update_params.user_id)
    bot_message = (
        'Ваши "домашние координаты" удалены. Теперь расстояние и направление '
        'до поисков не будет отображаться.\n'
        'Вы в любой момент можете заново ввести новые "домашние координаты". '
        'Функция Автоматического определения координат работает только для '
        'носимых устройств, для настольного компьютера – воспользуйтесь '
        'ручным вводом.'
    )
    keyboard: list[str | KeyboardButton] = [
        b_coords_auto_def,
        CoordinateSettingsMenu.b_coords_man_def,
        CoordinateSettingsMenu.b_coords_check,
        b_back_to_start,
    ]
    return bot_message, create_one_column_reply_markup(keyboard)


@button_handler(buttons=[CoordinateSettingsMenu.b_coords_check])
def handle_coordinates_show_saved(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    lat, lon = db().get_user_coordinates_or_none(update_params.user_id)

    if lat and lon:
        bot_message = f'Ваши "домашние координаты" {generate_yandex_maps_place_link(lat, lon, "coords")}'
    else:
        bot_message = 'Ваши координаты пока не сохранены. Введите их автоматически или вручную.'

    keyboard: list[str | KeyboardButton] = [
        b_coords_auto_def,
        CoordinateSettingsMenu.b_coords_man_def,
        CoordinateSettingsMenu.b_coords_check,
        CoordinateSettingsMenu.b_coords_del,
        b_back_to_start,
    ]

    return bot_message, create_one_column_reply_markup(keyboard)


@button_handler(buttons=[CoordinateSettingsMenu.b_coords_man_def])
def handle_coordinates_menu_manual_input(
    update_params: UpdateBasicParams, extra_params: UpdateExtraParams
) -> HandlerResultWithState:
    bot_message = (
        'Введите координаты вашего дома вручную в теле сообщения и просто '
        'отправьте. Формат: XX.XXXХХ, XX.XXXХХ, где количество цифр после точки '
        'может быть различным. Широта (первое число) должна быть между 30 '
        'и 80, Долгота (второе число) – между 10 и 190.'
    )
    return bot_message, ReplyKeyboardRemove(), UserInputState.input_of_coords_man


@button_handler(buttons=[ItsMe.b_yes_its_me])
def handle_linking_to_forum_its_me(update_params: UpdateBasicParams, extra_params: UpdateExtraParams) -> HandlerResult:
    """Write "verified" for user"""

    db().write_user_forum_attributes_db(update_params.user_id)

    bot_message = (
        'Отлично, мы записали: теперь бот будет понимать, кто вы на форуме.\nЭто поможет '
        'вам более оперативно получать сообщения о поисках, по которым вы оставляли '
        'комментарии на форуме.'
    )
    keyboard = [MainMenu.b_settings, b_back_to_start]
    return bot_message, create_one_column_reply_markup(keyboard)


@button_handler(buttons=[ItsMe.b_no_its_not_me])
def handle_linking_to_forum_not_me(
    update_params: UpdateBasicParams, extra_params: UpdateExtraParams
) -> HandlerResultWithState:
    """suggest user to correct nicname"""
    bot_message = (
        'Пожалуйста, тщательно проверьте написание вашего ника на форуме '
        '(кириллица/латиница, без пробела в конце) и введите его заново'
    )
    keyboard = [MainSettingsMenu.b_set_forum_nick, b_back_to_start]
    return bot_message, create_one_column_reply_markup(keyboard), UserInputState.input_of_forum_username


@button_handler(buttons=[MainSettingsMenu.b_set_forum_nick])
def handle_linking_to_forum_show_menu(
    update_params: UpdateBasicParams, extra_params: UpdateExtraParams
) -> HandlerResult | HandlerResultWithState:
    """manage all interactions regarding connection of telegram and forum user accounts"""

    # TODO: if user_is linked to forum so
    saved_forum_user = db().get_user_forum_attributes_db(update_params.user_id)

    if not saved_forum_user:
        bot_message = (
            'Бот сможет быть еще полезнее, эффективнее и быстрее, если указать ваш аккаунт на форуме '
            'lizaalert.org\n\n'
            'Для этого просто введите ответным сообщением своё имя пользователя (логин).\n\n'
            'Если возникнут ошибки при распознавании – просто скопируйте имя с форума и '
            'отправьте боту ответным сообщением.'
        )
        keyboard = [b_back_to_start]
        reply_markup = create_one_column_reply_markup(keyboard)
        return bot_message, reply_markup, UserInputState.input_of_forum_username

    else:
        saved_forum_username, saved_forum_user_id = list(saved_forum_user)

        bot_message = (
            f'Ваш телеграм уже привязан к аккаунту '
            f'<a href="https://lizaalert.org/forum/memberlist.php?mode=viewprofile&u='
            f'{saved_forum_user_id}">{saved_forum_username}</a> '
            f'на форуме ЛизаАлерт. Больше никаких действий касательно аккаунта на форуме не требуется:)'
        )
        keyboard = [MainMenu.b_settings, b_back_to_start]
        return bot_message, create_one_column_reply_markup(keyboard)
