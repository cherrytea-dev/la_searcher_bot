"""Platform-independent text templates and formatter functions.

This module contains all text messages used by the bot, extracted from
messenger-specific handler code. Both Telegram and VK bots use these
functions to compose user-facing messages, ensuring consistency.

All functions return plain text (str) without any platform-specific
formatting (no HTML, no Markdown). The calling bot is responsible for
applying its own formatting (e.g., HTML tags for Telegram, links for VK).
"""

from dataclasses import dataclass
from typing import Sequence


# ─── Constants ───────────────────────────────────────────────────────────────

SEARCH_URL_PREFIX = 'https://lizaalert.org/forum/viewtopic.php?t='
FORUM_FOLDER_PREFIX = 'https://lizaalert.org/forum/viewforum.php?f='
LA_BOT_CHAT_URL = 'https://t.me/joinchat/2J-kV0GaCgwxY2Ni'
LA_PHOTOS_CHANNEL_URL = 'https://t.me/+6LYNNEy8BeI1NGUy'
LA_DEV_CHAT_URL = 'https://t.me/+2J-kV0GaCgwxY2Ni'
LA_HOTLINE_PHONE = '8 800 700-54-52'
LA_WEBSITE = 'https://lizaalert.org'
LA_FORUM_URL = 'https://lizaalert.org/forum/'
LA_NEWBIE_ARTICLE = 'https://lizaalert.org/dvizhenie/novichkam/'
LA_HOW_TO_HELP_ARTICLE = 'https://takiedela.ru/news/2019/05/25/instrukciya-liza-alert/'
LA_SEARCH_REQUEST_FORM = 'https://lizaalert.org/zayavka-na-poisk/'
LA_NEWBIE_FORUM_TOPIC = 'https://lizaalert.org/forum/viewtopic.php?t=56934'
LA_BOT_DEV_CHAT = 'https://t.me/MikeMikeT'


# ─── Data Models ─────────────────────────────────────────────────────────────


@dataclass
class SearchDisplayItem:
    """Formatted search item for display in search listings."""

    topic_id: int
    display_name: str
    status_text: str  # e.g., "Ищем 3 дня" or "НЖ"
    distance_text: str  # e.g., "15 км ↗️" or empty
    following_mark: str  # e.g., "👀" or "❌" or "  "


# ─── Welcome & Onboarding ────────────────────────────────────────────────────


def welcome_new_user() -> str:
    """Message for a brand new user who just started the bot."""
    return (
        'Привет! Это Бот Поисковика ЛизаАлерт. Он помогает Поисковикам '
        'оперативно получать информацию о новых поисках или об изменениях '
        'в текущих поисках.'
        '\n\nБот управляется кнопками, которые заменяют обычную клавиатуру. '
        'Если кнопки не отображаются, справа от поля ввода сообщения '
        'есть специальный значок, чтобы отобразить кнопки управления ботом.'
        '\n\nДавайте настроим бот индивидуально под вас. Пожалуйста, '
        'укажите вашу роль сейчас?'
    )


def welcome_back_user() -> str:
    """Message for a returning user (already completed onboarding)."""
    return 'Привет! Бот управляется кнопками, которые заменяют обычную клавиатуру.'


def onboarding_completed_message() -> str:
    """Message shown after user completes basic onboarding."""
    return (
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


# ─── Role Selection ──────────────────────────────────────────────────────────


def ask_role() -> str:
    """Ask user to select their role."""
    return 'Пожалуйста, укажите вашу роль сейчас?'


def role_relative_instructions() -> str:
    """Instructions for a user who is looking for a missing person."""
    return (
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


def role_volunteer_instructions() -> str:
    """Instructions for a potential LA volunteer."""
    return (
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


def role_other_ask_region() -> str:
    """Ask about Moscow region after role selection (non-relative, non-volunteer)."""
    return 'Спасибо. Теперь уточните, пожалуйста, ваш основной регион – это ' 'Москва и Московская Область?'


# ─── Region Selection ────────────────────────────────────────────────────────


def region_selection_intro() -> str:
    """Intro message when entering region selection."""
    return 'Бот может показывать поиски в любом регионе работы ЛА.\n' 'Вы можете подписаться на несколько регионов'


def region_selection_help() -> str:
    """Help text shown above the region selection keyboard."""
    return (
        'Выберите регионы, по которым хотите видеть поиски. '
        'Можно фильтровать регионы по первой букве.\n'
        'Чтобы ОТПИСАТЬСЯ от какого-либо региона – нажмите на его кнопку еще раз.'
    )


def force_set_region() -> str:
    """Message when user is forced to set a region before using the bot."""
    return (
        'Для корректной работы бота, пожалуйста, задайте свой регион. Для этого '
        'с помощью кнопок меню выберите сначала ФО (федеральный округ), а затем и '
        'регион. Можно выбирать несколько регионов из разных ФО. Выбор региона '
        'также можно отменить, повторно нажав на кнопку с названием региона. '
        'Функционал бота не будет активирован, пока не выбран хотя бы один регион.'
    )


def region_selection_closed() -> str:
    """Message when user closes region selection."""
    return 'Выбор завершен'


def region_selection_cant_remove_last() -> str:
    """Flash message when user tries to remove the last region."""
    return 'Требуется хотя бы 1 регион'


# ─── Settings Menu ───────────────────────────────────────────────────────────


def settings_menu_intro() -> str:
    """Intro message for the main settings menu."""
    return (
        'Это раздел с настройками. Здесь вы можете выбрать удобные для вас '
        'уведомления, а также ввести свои "домашние координаты", на основе которых '
        'будет рассчитываться расстояние и направление до места поиска. Вы в любой '
        'момент сможете изменить эти настройки.'
    )


def compose_settings_completeness_message(
    has_notif_type: bool,
    has_region: bool,
    has_coords: bool,
    has_radius: bool,
    has_age: bool,
    has_forum: bool,
) -> str | None:
    """Compose a message about which settings the user hasn't configured yet.

    Returns None if all settings are configured (100% completeness).
    """
    configured = [has_notif_type, has_region, has_coords, has_radius, has_age, has_forum]
    user_score = int(round(sum(configured) / len(configured) * 100, 0))

    if user_score == 100:
        return None

    message_parts = [
        f'Вы настроили бот на {user_score}%.',
        '',
        'Чтобы сделать бот максимально эффективным именно для вас, рекомендуем настроить следующие параметры:',
    ]
    if not has_notif_type:
        message_parts.append(' - Тип уведомлений,')
    if not has_region:
        message_parts.append(' - Регион,')
    if not has_coords:
        message_parts.append(' - Домашние координаты,')
    if not has_radius:
        message_parts.append(' - Максимальный радиус,')
    if not has_age:
        message_parts.append(' - Возрастные группы БВП,')
    if not has_forum:
        message_parts.append(' - Связать бот с форумом ЛА,')

    return '\n'.join(message_parts)


# ─── Notification Settings ───────────────────────────────────────────────────


def notif_settings_intro() -> str:
    """Intro message for notification settings."""
    return 'Выберите, какие уведомления вы бы хотели получать'


def notif_settings_current_prefs(prefs_text: str) -> str:
    """Message showing current notification preferences."""
    return f'Сейчас у вас включены следующие виды уведомлений:\n{prefs_text}'


def notif_settings_no_prefs() -> str:
    """Message when user has no notification preferences set."""
    return 'пока нет включенных уведомлений'


NOTIF_PREF_NAMES: dict[str, str] = {
    'all': 'все сообщения',
    'new_searches': 'о новых поисках',
    'status_changes': 'об изменении статуса',
    'title_changes': 'об изменении заголовка',
    'comments_changes': 'о всех комментариях',
    'inforg_comments': 'о комментариях Инфорга',
    'first_post_changes': 'об изменениях в первом посте',
    'all_in_followed_search': 'в отслеживаемом поиске - все уведомления',
    'field_trips_new': 'о новых выездах',
    'field_trips_change': 'об изменениях выездов',
    'coords_change': 'о смене координат штаба',
    'bot_news': '',
}


def format_notif_prefs_list(pref_names: list[str]) -> str:
    """Format a list of notification preference names into a readable string."""
    lines = [NOTIF_PREF_NAMES.get(p, 'неизвестная настройка') for p in pref_names]
    return '\n'.join(x for x in lines if x)


def notif_all_enabled() -> str:
    """Message when user enables all notifications."""
    return (
        'Супер! теперь вы будете получать уведомления в случаях: '
        'появление нового поиска, изменение статуса поиска (стоп, НЖ, НП), '
        'появление новых комментариев по всем поискам. Вы в любой момент '
        'можете изменить список уведомлений'
    )


def notif_all_disabled() -> str:
    """Message when user disables all notifications (switches to granular)."""
    return 'Вы можете настроить типы получаемых уведомлений более гибко'


def notif_new_search_enabled() -> str:
    return (
        'Отлично! Теперь вы будете получать уведомления при '
        'появлении нового поиска. Вы в любой момент можете изменить '
        'список уведомлений'
    )


def notif_status_change_enabled() -> str:
    return (
        'Отлично! теперь вы будете получать уведомления при '
        'изменении статуса поисков (НЖ, НП, СТОП и т.п.). Вы в любой момент '
        'можете изменить список уведомлений'
    )


def notif_title_change_enabled() -> str:
    return 'Отлично!'


def notif_all_comments_enabled() -> str:
    return 'Отлично! Теперь все новые комментарии будут у вас! ' 'Вы в любой момент можете изменить список уведомлений'


def notif_all_comments_disabled() -> str:
    return 'Записали. Мы только оставили вам включенными уведомления о ' 'комментариях Инфорга. Их тоже можно отключить'


def notif_inforg_comments_enabled() -> str:
    return (
        'Если вы не подписаны на уведомления по всем комментариям, то теперь '
        'вы будете получать уведомления о комментариях от Инфорга. Если же вы '
        'уже подписаны на все комментарии – то всё остаётся без изменений: бот '
        'уведомит вас по всем комментариям, включая от Инфорга'
    )


def notif_inforg_comments_disabled() -> str:
    return 'Вы отписались от уведомлений по новым комментариям от Инфорга'


def notif_field_trip_new_enabled() -> str:
    return (
        'Теперь вы будете получать уведомления о новых выездах по уже идущим '
        'поискам. Обратите внимание, что это не рассылка по новым темам на '
        'форуме, а именно о том, что в существующей теме в ПЕРВОМ посте '
        'появилась информация о новом выезде'
    )


def notif_field_trip_new_disabled() -> str:
    return 'Вы отписались от уведомлений по новым выездам'


def notif_field_trip_change_enabled() -> str:
    return (
        'Теперь вы будете получать уведомления о ключевых изменениях при '
        'выездах, в т.ч. изменение или завершение выезда. Обратите внимание, '
        'что эта рассылка отражает изменения только в ПЕРВОМ посте поиска.'
    )


def notif_field_trip_change_disabled() -> str:
    return 'Вы отписались от уведомлений по изменениям выездов'


def notif_coords_change_enabled() -> str:
    return (
        'Если у штаба поменяются координаты (и об этом будет написано в первом '
        'посте на форуме) – бот уведомит вас об этом'
    )


def notif_coords_change_disabled() -> str:
    return 'Вы отписались от уведомлений о смене места (координат) штаба'


def notif_first_post_change_enabled() -> str:
    return (
        'Теперь вы будете получать уведомления о важных изменениях в Первом Посте'
        ' Инфорга, где обозначено описание каждого поиска'
    )


def notif_first_post_change_disabled() -> str:
    return 'Вы отписались от уведомлений о важных изменениях в Первом Посте ' 'Инфорга c описанием каждого поиска'


def notif_all_in_followed_enabled() -> str:
    return 'Теперь во время отслеживания поиска будут все уведомления по нему.'


def notif_all_in_followed_disabled() -> str:
    return 'Теперь по отслеживаемым поискам будут уведомления как обычно (только настроенные).'


def notif_saved() -> str:
    return 'Записали'


# ─── Topic Type Settings ─────────────────────────────────────────────────────


def topic_type_intro() -> str:
    """Intro message for topic type selection."""
    return (
        'Вы можете выбрать и в любой момент поменять, по каким типам поисков или '
        'мероприятий бот должен присылать уведомления.'
    )


# ─── Age Settings ────────────────────────────────────────────────────────────


def age_settings_intro(first_visit: bool = False) -> str:
    """Intro message for age settings."""
    msg = (
        'Чтобы включить или отключить уведомления по определенной возрастной '
        'группе, нажмите на неё. Настройку можно изменить в любой момент.'
    )
    if first_visit:
        msg = (
            'Данное меню позволяет выбрать возрастные категории БВП '
            '(без вести пропавших), по которым вы хотели бы получать уведомления. '
            'Важно, что если бот не сможет распознать возраст БВП, тогда вы '
            'всё равно получите уведомление.\nТакже данная настройка не влияет на '
            'разделы Актуальные Поиски и Последние Поиски – в них вы всё также '
            'сможете увидеть полный список поисков.\n\n' + msg
        )
    return msg


def age_saved() -> str:
    return 'Спасибо, записали.'


# ─── Radius Settings ─────────────────────────────────────────────────────────


def radius_intro_no_radius() -> str:
    """Message when user has no radius set."""
    return (
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


def radius_intro_with_radius(saved_radius: int) -> str:
    """Message when user already has a radius set."""
    return (
        f'Сейчас вами установлено ограничение радиуса {saved_radius} км. '
        f'Вы в любой момент можете изменить или снять это ограничение.\n\n'
        'ВАЖНО! Вы всё равно будете проинформированы по всем поискам, по которым '
        'Бот не смог распознать никакие координаты.\n\n'
        'Также, бот в первую очередь '
        'проверяет расстояние от штаба, а если он не указан, то до ближайшего '
        'населенного пункта (или топонима), указанного в теме поиска. '
        'Расстояние считается по прямой.'
    )


def radius_ask_value(saved_radius: int | None = None) -> str:
    """Ask user to enter a radius value."""
    if saved_radius:
        return (
            f'У вас установлено максимальное расстояние до поиска {saved_radius}.'
            f'\n\nВведите обновлённое расстояние в километрах по прямой в формате простого '
            f'числа (например: 150) и нажмите обычную кнопку отправки сообщения'
        )
    return (
        'Введите расстояние в километрах по прямой в формате простого числа '
        '(например: 150) и нажмите обычную кнопку отправки сообщения'
    )


def radius_saved(radius: int) -> str:
    """Message after radius is saved."""
    return (
        f'Сохранили! Теперь поиски, у которых расстояние до штаба, '
        f'либо до ближайшего населенного пункта (топонима) превосходит '
        f'{radius} км по прямой, не будут вас больше беспокоить. '
        f'Настройку можно изменить в любое время.'
    )


def radius_deleted() -> str:
    """Message after radius is deleted."""
    return 'Ограничение на расстояние по поискам снято!'


def radius_parse_error() -> str:
    """Message when radius input could not be parsed."""
    return 'Не могу разобрать цифры. Давайте еще раз попробуем?'


# ─── Coordinates Settings ────────────────────────────────────────────────────


def coords_intro() -> str:
    """Intro message for coordinates settings."""
    return (
        'АВТОМАТИЧЕСКОЕ ОПРЕДЕЛЕНИЕ координат работает только для носимых устройств'
        ' (для настольных компьютеров – НЕ работает: используйте, пожалуйста, '
        'кнопку ручного ввода координат). '
        'При автоматическом определении координат – нажмите на кнопку и '
        'разрешите определить вашу текущую геопозицию. '
        'Координаты, загруженные вручную или автоматически, будут считаться '
        'вашим "домом", откуда будут рассчитаны расстояние и '
        'направление до поисков.'
    )


def coords_ask_manual_input() -> str:
    """Message asking user to enter coordinates manually."""
    return (
        'Введите координаты вашего дома вручную в теле сообщения и просто '
        'отправьте. Формат: XX.XXXХХ, XX.XXXХХ, где количество цифр после точки '
        'может быть различным. Широта (первое число) должна быть между 30 '
        'и 80, Долгота (второе число) – между 10 и 190.'
    )


def coords_saved() -> str:
    """Message after coordinates are saved."""
    return (
        'Ваши "домашние координаты" сохранены.\n'
        'Теперь для всех поисков, где удастся распознать координаты штаба или '
        'населенного пункта, будет указываться направление и расстояние по '
        'прямой от ваших "домашних координат".'
    )


def coords_deleted() -> str:
    """Message after coordinates are deleted."""
    return (
        'Ваши "домашние координаты" удалены. Теперь расстояние и направление '
        'до поисков не будет отображаться.\n'
        'Вы в любой момент можете заново ввести новые "домашние координаты". '
        'Функция Автоматического определения координат работает только для '
        'носимых устройств, для настольного компьютера – воспользуйтесь '
        'ручным вводом.'
    )


def coords_not_set() -> str:
    """Message when user has no coordinates saved."""
    return 'Ваши координаты пока не сохранены. Введите их автоматически или вручную.'


def coords_parse_error() -> str:
    """Message when coordinates could not be parsed."""
    return 'Координаты не распознаны.'


# ─── Forum Linking ───────────────────────────────────────────────────────────


def forum_link_intro() -> str:
    """Message asking user to enter their forum username."""
    return (
        'Бот сможет быть еще полезнее, эффективнее и быстрее, если указать ваш аккаунт на форуме '
        'lizaalert.org\n\n'
        'Для этого просто введите ответным сообщением своё имя пользователя (логин).\n\n'
        'Если возникнут ошибки при распознавании – просто скопируйте имя с форума и '
        'отправьте боту ответным сообщением.'
    )


def forum_link_checking() -> str:
    """Message while checking forum username."""
    return 'Сейчас посмотрю, это может занять до 10 секунд...'


def forum_link_invalid() -> str:
    """Message when forum username is invalid."""
    return 'Неправильный логин, попробуйте еще раз'


def forum_link_ask_retry() -> str:
    """Message asking user to re-enter forum username."""
    return (
        'Пожалуйста, тщательно проверьте написание вашего ника на форуме '
        '(кириллица/латиница, без пробела в конце) и введите его заново'
    )


def forum_link_verified() -> str:
    """Message after forum account is verified."""
    return (
        'Отлично, мы записали: теперь бот будет понимать, кто вы на форуме.\nЭто поможет '
        'вам более оперативно получать сообщения о поисках, по которым вы оставляли '
        'комментарии на форуме.'
    )


def forum_already_linked(forum_username: str, forum_user_id: int) -> str:
    """Message when forum is already linked."""
    return (
        f'Ваш телеграм уже привязан к аккаунту '
        f'{forum_username} '
        f'на форуме ЛизаАлерт. Больше никаких действий касательно аккаунта на форуме не требуется:)'
    )


# ─── VK Linking ──────────────────────────────────────────────────────────────


def vk_link_intro() -> str:
    """Message asking user to link VK account."""
    return (
        'После того, как вы отправите скопированный текст в чате VK,'
        ' бот начнет присылать вам уведомления по текущим настройкам.'
    )


def vk_already_linked() -> str:
    """Message when VK is already linked."""
    return 'Ваши аккаунты в Telegram и в VK уже связаны'


def vk_link_instructions(invite_text: str) -> str:
    """Instructions for linking VK account."""
    return f'Откройте чат в VK по кнопке ниже \n и вставьте туда следующий текст: `{invite_text}`'


# ─── Search Following ────────────────────────────────────────────────────────


def search_follow_mode_on() -> str:
    """Message when search follow mode is enabled."""
    return 'Возможность отслеживания поисков включена. Возвращаемся в главное меню.'


def search_follow_mode_off() -> str:
    """Message when search follow mode is disabled."""
    return 'Возможность отслеживания поисков вЫключена. Возвращаемся в главное меню.'


def search_follow_intro() -> str:
    """Message shown with the search follow mode toggle button."""
    return (
        'Вы можете включить возможность выбора поисков для отслеживания, '
        'чтобы получать уведомления не со всех актуальных поисков, '
        'а только с выбранных Вами.'
    )


def search_follow_experimental_intro() -> str:
    """Intro message for experimental search follow mode (inline keyboard view)."""
    return (
        'МЕНЮ АКТУАЛЬНЫХ ПОИСКОВ ДЛЯ ОТСЛЕЖИВАНИЯ.'
        'Каждый поиск ниже дан строкой из пары кнопок: кнопка пометки для отслеживания и кнопка перехода на форум.'
        '👀 - знак пометки поиска для отслеживания, уведомления будут приходить только по помеченным поискам. '
        'Если таких нет, то уведомления будут приходить по всем поискам согласно настройкам.'
        '❌ - пометка поиска для игнорирования ("черный список") - уведомления по таким поискам не будут приходить в любом случае.'
    )


def no_active_searches_found() -> str:
    """Message when no active searches match user's filters."""
    return 'Незавершенные поиски в соответствии с Вашей настройкой видов поисков не найдены.'


# ─── Search Listings ─────────────────────────────────────────────────────────


def active_searches_header(region_name: str) -> str:
    """Header for active searches in a region."""
    return f'Акт. поиски за 60 дней в {region_name}'


def active_searches_empty(region_name: str) -> str:
    """Message when no active searches in a region."""
    return f'Нет акт. поисков за 60 дней в {region_name}'


def active_searches_text_header(region_name: str) -> str:
    """Header for text-based active searches listing."""
    return f'Актуальные поиски за 60 дней в разделе {region_name}:'


def active_searches_all_completed(region_name: str) -> str:
    """Message when all searches in a region are completed."""
    return f'В разделе {region_name} все поиски за последние 60 дней завершены.'


def last_searches_header(region_name: str) -> str:
    """Header for last 20 searches in a region."""
    return f'Посл. 20 поисков в {region_name}'


def last_searches_text_header(region_name: str) -> str:
    """Header for text-based last searches listing."""
    return f'Последние 20 поисков в разделе {region_name}:'


def last_searches_error(region_name: str) -> str:
    """Error message when last searches cannot be displayed."""
    return (
        f'Не получается отобразить последние поиски в разделе {region_name},'
        ' что-то пошло не так, простите. Напишите об этом разработчику '
        'в чат, пожалуйста.'
    )


# ─── Other Menu ──────────────────────────────────────────────────────────────


def other_menu_intro() -> str:
    """Intro message for the 'Other' menu."""
    return (
        'Здесь можно посмотреть статистику по 20 последним поискам, перейти в '
        'канал Коммъюнити или Прочитать важную информацию для Новичка и посмотреть '
        'душевные фото с поисков'
    )


def photos_intro() -> str:
    """Message for the photos channel link."""
    return (
        'Если вам хочется окунуться в атмосферу ПСР, приглашаем в замечательный '
        'телеграм-канал с красивыми фото с '
        'поисков. Все фото – сделаны поисковиками во время настоящих ПСР.'
    )


def first_search_intro() -> str:
    """Message for first search info."""
    return (
        'Если вы хотите стать добровольцем ДПСО «ЛизаАлерт», пожалуйста, '
        'посетите страницу форума, там можно ознакомиться с базовой информацией '
        'для новичков и задать свои вопросы. '
        'Если вы готовитесь к своему первому поиску – приглашаем '
        'ознакомиться с основами работы ЛА. Всю теорию работы ЛА необходимо '
        'получать от специально обученных волонтеров ЛА. Но если у вас еще не '
        'было возможности пройти официальное обучение, а вы уже готовы выехать '
        'на поиск – этот ресурс для вас.'
    )


def community_intro() -> str:
    """Message for the community chat link."""
    return (
        'Бот можно обсудить с соотрядниками в Специальном Чате '
        'в телеграм. Там можно предложить свои идеи, указать на проблемы '
        'и получить быструю обратную связь от разработчика.'
    )


def map_intro() -> str:
    """Message for the map feature."""
    return (
        'В Боте Поисковика теперь можно посмотреть Карту Поисков.\n\n'
        'На карте вы сможете увидеть все активные поиски, '
        'построить к каждому из них маршрут с учетом пробок, '
        'а также открыть этот маршрут в сервисах Яндекс.\n\n'
        'Карта работает в тестовом режиме.\n'
        'Если карта будет работать некорректно, или вы видите, как ее необходимо '
        'доработать – напишите в чат разработчиков.'
    )


# ─── Help / Feedback ─────────────────────────────────────────────────────────


def help_no_thanks() -> str:
    """Message when user says they don't need help."""
    return (
        'Спасибо, понятно. Мы записали. Тогда бот более не будет вас беспокоить, '
        'пока вы сами не напишите в бот.\n\n'
        'На прощание, бот хотел бы посоветовать следующие вещи, делающие мир лучше:\n\n'
        '1. Посмотреть позитивные фото с поисков ЛизаАлерт.\n\n'
        '2. Помочь отряду ЛизаАлерт, пожертвовав оборудование для поисков людей.\n\n'
        '3. Помочь создателям данного бота, присоединившись к группе разработчиков '
        'или оплатив облачную инфраструктуру для бесперебойной работы бота. Для этого '
        'просто напишите разработчику бота.\n\n'
        'Бот еще раз хотел подчеркнуть, что как только вы напишите что-то в бот – он '
        'сразу же "забудет", что вы ранее просили вас не беспокоить:)\n\n'
        'Обнимаем:)'
    )


def help_yes_please() -> str:
    """Message when user says they need help with setup."""
    return (
        'Супер! Тогда давайте посмотрим, что у вас не настроено.\n\n'
        'У вас не настроен Регион поисков – без него Бот не может определить, '
        'какие поиски вас интересуют. Вы можете настроить регион двумя способами:\n'
        '1. Либо автоматически на основании ваших координат – нужно будет отправить '
        'вашу геолокацию (работает только с мобильных устройств),\n'
        '2. Либо выбрав регион вручную: для этого нужно сначала выбрать ФО = '
        'Федеральный Округ, где находится ваш регион, а потом кликнуть на сам регион. '
        '\n\n'
    )


# ─── Unsupported Messages ────────────────────────────────────────────────────


def unsupported_media() -> str:
    """Message when user sends a photo, document, voice, or sticker."""
    return (
        'Спасибо, интересное! Однако, бот работает только с текстовыми командами. '
        'Пожалуйста, воспользуйтесь текстовыми кнопками бота, находящимися на '
        'месте обычной клавиатуры.'
    )


def unsupported_contact() -> str:
    """Message when user sends a contact."""
    return (
        'Спасибо, буду знать. Вот только бот не работает с контактами и отвечает '
        'только на определенные текстовые команды.'
    )


# ─── Back to Main Menu ───────────────────────────────────────────────────────


def back_to_main_menu() -> str:
    """Message when returning to main menu."""
    return 'возвращаемся в главное меню'


def unknown_command() -> str:
    """Message for unknown commands."""
    return 'Неизвестная команда'


# ─── Admin / Test ────────────────────────────────────────────────────────────


def admin_menu_intro() -> str:
    """Message for admin menu entry."""
    return 'Вы вошли в специальный тестовый админ-раздел'


def tester_role_granted() -> str:
    """Message when tester role is granted."""
    return (
        'Вы в секретном тестовом разделе, где всё может работать не так :) '
        'Если что – пишите, пожалуйста, в телеграм-чат разработчиков.'
        '\nА еще Вам добавлена роль tester - некоторые тестовые функции включены автоматически.'
        '\nДля отказа от роли tester нужно отправить команду notest'
    )


def tester_role_removed() -> str:
    """Message when tester role is removed."""
    return 'Роль tester удалена. Приходите еще! :-) Возвращаемся в главное меню.'
