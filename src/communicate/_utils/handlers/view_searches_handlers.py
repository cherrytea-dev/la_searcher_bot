import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from _dependencies.common.misc import age_writer, time_counter_since_search_start
from _dependencies.common.telegram_message import TelegramMessage

from ..buttons import Commands, MainMenu, OtherOptionsMenu, reply_markup_main
from ..common import (
    FORUM_FOLDER_PREFIX,
    LA_BOT_CHAT_URL,
    NOT_FOLLOWING_MARK,
    SEARCH_URL_PREFIX,
    InlineButtonCallbackData,
    SearchSummary,
    define_dist_and_dir_to_search,
)
from ..decorators import tg_handle
from ..handler_context import TGHandlerContext

if TYPE_CHECKING:
    from ..database import DBClient

InlineKeyboardRow = list[InlineKeyboardButton]  # type alias


class SearchListType(Enum):
    ALL = 1
    ACTIVE = 2


@dataclass
class SearchesIKBData:
    title: str
    folder_url: str
    rows: list[InlineKeyboardRow]


def _search_button_row_ikb(search: SearchSummary, search_status: str) -> list[InlineKeyboardRow]:
    search_following_mark = search.following_mode if search.following_mode else NOT_FOLLOWING_MARK
    url = f'{SEARCH_URL_PREFIX}{search.topic_id}'

    callback_data = InlineButtonCallbackData(action='search_follow_mode', hash=search.topic_id).as_str()
    ikb_row = [
        [
            InlineKeyboardButton(text=f'{search_following_mark} {search_status}', callback_data=str(callback_data)),
            InlineKeyboardButton(text=search.display_name, url=url),  # right button - link to the search on the forum
        ]
    ]
    return ikb_row


def _get_region_name(folders_list: list[tuple[int, str]], forum_folder_num: int) -> str:
    for region_id, region_name in folders_list:
        if region_id == forum_folder_num:
            return region_name

    return ''


def _format_searches_for_display(searches: list[SearchSummary]) -> None:
    for search in searches:
        if not search.display_name:
            age_string = f' {age_writer(search.age)}' if search.age and search.age != 0 else ''
            search.display_name = f'{search.name}{age_string}'

        if not search.new_status:
            search.new_status = search.status

        if search.new_status in {'Ищем', 'Возобновлен'}:
            search.new_status = f'Ищем {time_counter_since_search_start(search.start_time)[0]}'


def _compose_ikb_of_last_searches(
    db_client: 'DBClient', user_id: int, forum_folder_num: int, region_name: str, only_followed: bool
) -> SearchesIKBData:
    """Compose a Final message on the list of searches in the given region"""
    # issue#425 This variant of the above function returns data in format used to compose inline keyboard
    # 1st element is caption
    # rest elements are searches in format to be showed as inline buttons

    folder_url = f'{FORUM_FOLDER_PREFIX}{forum_folder_num}'

    searches = db_client.get_all_last_searches_in_region_limit_20(forum_folder_num, user_id, only_followed)
    if not searches:
        msg = _get_message_last_searches_not_found(region_name, forum_folder_num)
        return SearchesIKBData(msg, folder_url, [])

    rows: list[InlineKeyboardRow] = []

    _format_searches_for_display(searches)

    rows = [_search_button_row_ikb(search, search.new_status)[0] for search in searches]

    logging.info('ikb += compose_msg_on_all_last_searches_ikb == ' + str(rows))

    msg = f'Посл. 20 поисков в {region_name}'
    return SearchesIKBData(msg, folder_url, rows)


def _get_message_last_searches_not_found(region_name: str, folder_id: int) -> str:
    folder_url = f'{FORUM_FOLDER_PREFIX}{folder_id}'

    msg = (
        'Не получается отобразить последние поиски в разделе '
        f'<a href="{folder_url}">{region_name}</a>,'
        ' что-то пошло не так, простите. Напишите об этом разработчику '
        f'в <a href="{LA_BOT_CHAT_URL}">Специальном Чате в телеграм</a>, пожалуйста.'
    )

    return msg


def _compose_ikb_of_active_searches(
    db_client: 'DBClient', user_id: int, forum_folder_num: int, region_name: str
) -> SearchesIKBData:
    """Compose a Final message on the list of searches in the given region"""
    # Combine the list of the latest active searches
    folder_url = f'{FORUM_FOLDER_PREFIX}{forum_folder_num}'
    user_lat, user_lon = db_client.get_user_coordinates_or_none(user_id)

    searches = db_client.get_active_searches_in_region_limit_20(forum_folder_num, user_id)
    if not searches:
        msg = f'Нет акт. поисков за 60 дней в {region_name}'
        return SearchesIKBData(msg, folder_url, [])

    rows: list[InlineKeyboardRow] = []

    for search in searches:
        if time_counter_since_search_start(search.start_time)[1] >= 60 and not search.following_mode:
            continue

        time_since_start = time_counter_since_search_start(search.start_time)[0]

        if user_lat and user_lon and search.search_lat:
            dist = define_dist_and_dir_to_search(search.search_lat, search.search_lon, user_lat, user_lon, False)
            dist_and_dir = f' {dist[1]} {dist[0]} км'
        else:
            dist_and_dir = ''

        if not search.display_name:
            age_string = f' {age_writer(search.age)}' if search.age != 0 else ''
            search.display_name = f'{search.name}{age_string}'

        rows += _search_button_row_ikb(search, f'{time_since_start}{dist_and_dir}')

    logging.info(f'ikb += compose_msg_on_active_searches_in_one_reg_ikb == {rows}; ({forum_folder_num=})')

    msg = f'Акт. поиски за 60 дней в {region_name}'
    return SearchesIKBData(msg, folder_url, rows)


def _compose_text_message_of_all_searches(db_client: 'DBClient', forum_folder_num: int, region_name: str) -> str:
    """Compose a Final message on the list of ALL searches in the given region"""

    # download the list from SEARCHES sql table
    searches = db_client.get_all_searches_in_one_region_limit_20(forum_folder_num)

    _format_searches_for_display(searches)
    lines = [
        f'{search.new_status} <a href="{SEARCH_URL_PREFIX}{search.topic_id}">{search.display_name}</a>'
        for search in searches
    ]

    folder_url = f'{FORUM_FOLDER_PREFIX}{forum_folder_num}'
    # combine the list of last 20 searches

    if lines:
        lines.insert(0, f'Последние 20 поисков в разделе <a href="{folder_url}">{region_name}</a>:')
        return '\n'.join(lines)
    else:
        return _get_message_last_searches_not_found(region_name, forum_folder_num)


def _compose_text_message_on_active_searches(
    db_client: 'DBClient', forum_folder_num: int, region_name: str, user_id: int
) -> str:
    """Compose a Final message on the list of ACTIVE searches in the given region"""

    folder_url = f'{FORUM_FOLDER_PREFIX}{forum_folder_num}'
    user_lat, user_lon = db_client.get_user_coordinates_or_none(user_id)
    # Combine the list of the latest active searches

    lines: list[str] = []

    searches_list = db_client.get_active_searches_in_one_region(forum_folder_num)

    for search in searches_list:
        if time_counter_since_search_start(search.start_time)[1] >= 60:
            continue

        time_since_start = time_counter_since_search_start(search.start_time)[0]

        if user_lat and user_lon and search.search_lat:
            dist = define_dist_and_dir_to_search(search.search_lat, search.search_lon, user_lat, user_lon)
            dist_and_dir = f' {dist[1]} {dist[0]} км'
        else:
            dist_and_dir = ''

        if not search.display_name:
            age_string = f' {age_writer(search.age)}' if search.age != 0 else ''
            search.display_name = f'{search.name}{age_string}'

        lines.append(
            f'{time_since_start}{dist_and_dir} <a href="{SEARCH_URL_PREFIX}{search.topic_id}">{search.display_name}</a>'
        )

    msg = '\n'.join(lines)

    if msg:
        msg = f'Актуальные поиски за 60 дней в разделе <a href="{folder_url}">{region_name}</a>:\n{msg}'
    else:
        msg = f'В разделе <a href="{folder_url}">{region_name}</a> все поиски за последние 60 дней завершены.'

    return msg


def _handle_view_searches_usual_view(ctx: TGHandlerContext, search_list_type: SearchListType) -> None:
    user_id = ctx.user_id
    folders_list = ctx.db.get_geo_folders_db()

    for forum_folder_num in ctx.db.get_user_reg_folders_preferences(user_id):
        region_name = _get_region_name(folders_list, forum_folder_num)

        # check if region – is an archive folder: if so – it can be sent only to 'all'
        folder_is_archived = 'аверш' in region_name
        if folder_is_archived and search_list_type != SearchListType.ALL:
            continue

        if search_list_type == SearchListType.ALL:
            bot_message = _compose_text_message_of_all_searches(ctx.db, forum_folder_num, region_name)
        else:
            bot_message = _compose_text_message_on_active_searches(ctx.db, forum_folder_num, region_name, user_id)

        ctx.send_message(text=bot_message, reply_markup=reply_markup_main)

    _show_button_to_turn_on_following_searches(ctx)


def _show_button_to_turn_on_following_searches(ctx: TGHandlerContext) -> None:
    # issue425 add Button for turn on search following mode
    search_follow_mode_ikb = [
        [
            InlineKeyboardButton(
                text='Включить выбор поисков для отслеживания',
                callback_data=InlineButtonCallbackData(action='search_follow_mode_on').as_str(),
            )
        ]
    ]
    reply_markup = InlineKeyboardMarkup(search_follow_mode_ikb)
    ctx.tg_api.send_message(
        ctx.user_id,
        TelegramMessage(
            text=(
                'Вы можете включить возможность выбора поисков для отслеживания, '
                'чтобы получать уведомления не со всех актуальных поисков, '
                'а только с выбранных Вами.'
            ),
            reply_markup=reply_markup.to_dict(),
        ),
        f'{ctx.user_id=}, context_step=a01',
    )


def _handle_view_searches_experimental_view(ctx: TGHandlerContext, search_list_type: SearchListType) -> None:
    # issue#425 make inline keyboard - list of searches
    user_id = ctx.user_id
    user_regions = ctx.db.get_user_reg_folders_preferences(user_id)

    region_keyboards: list[SearchesIKBData] = []  # to combine monolit ikb for all user's regions

    folders_with_user_followed_searches = ctx.db.get_folders_with_followed_searches(user_id)

    folders_list = ctx.db.get_geo_folders_db()
    for region in set(user_regions + folders_with_user_followed_searches):
        region_name = _get_region_name(folders_list, region)

        logging.info(f'Before if region_name.find...: ; {region_keyboards=}')
        folder_is_archived = 'аверш' in region_name
        if folder_is_archived and search_list_type != SearchListType.ALL:
            continue

        if search_list_type == SearchListType.ALL:
            only_followed = region not in user_regions
            region_data = _compose_ikb_of_last_searches(ctx.db, user_id, region, region_name, only_followed)
        else:
            region_data = _compose_ikb_of_active_searches(ctx.db, user_id, region, region_name)

        region_keyboards.append(region_data)
        logging.info(f'After += compose_full_message_on_list_of_searches_ikb: {region_keyboards=}')

    all_searches_count = sum(len(x.rows) for x in region_keyboards)

    if not all_searches_count:
        bot_message = 'Незавершенные поиски в соответствии с Вашей настройкой видов поисков не найдены.'
        ctx.send_message(text=bot_message, reply_markup=reply_markup_main)
        return

    # issue#425 show the inline keyboard
    for i, region_data in enumerate(region_keyboards):
        if i == 0:  # first iteration
            bot_message = (
                'МЕНЮ АКТУАЛЬНЫХ ПОИСКОВ ДЛЯ ОТСЛЕЖИВАНИЯ.'
                'Каждый поиск ниже дан строкой из пары кнопок: кнопка пометки для отслеживания и кнопка перехода на форум.'
                '👀 - знак пометки поиска для отслеживания, уведомления будут приходить только по помеченным поискам. '
                'Если таких нет, то уведомления будут приходить по всем поискам согласно настройкам.'
                '❌ - пометка поиска для игнорирования ("черный список") - уведомления по таким поискам не будут приходить в любом случае.'
            )
        else:
            bot_message = ''

        bot_message += '\n' if bot_message else ''
        bot_message += f'<a href="{region_data.folder_url}">{region_data.title}</a>'

        if i == (len(region_keyboards) - 1):  # last iteration
            region_data.rows.append(
                [
                    InlineKeyboardButton(
                        text='Сбросить все пометки отслеживания поисков',
                        callback_data=InlineButtonCallbackData(action='search_follow_clear').as_str(),
                    )
                ]
            )
            region_data.rows.append(
                [
                    InlineKeyboardButton(
                        text='Отключить выбор поисков для отслеживания',
                        callback_data=InlineButtonCallbackData(action='search_follow_mode_off').as_str(),
                    )
                ]
            )

        reply_markup_inline = InlineKeyboardMarkup(region_data.rows)
        logging.info(f'{bot_message=}; {region_data.rows=}; context_step=b00')

        ctx.tg_api.send_message(
            user_id,
            TelegramMessage(
                text=bot_message,
                reply_markup=reply_markup_inline,
            ),
            f'{user_id=}, context_step=b03',
        )


@tg_handle(
    text=[
        OtherOptionsMenu.b_view_latest_searches,
        MainMenu.b_view_act_searches,
        Commands.c_view_latest_searches,
        Commands.c_view_act_searches,
    ]
)
def handle_view_searches(ctx: TGHandlerContext) -> None:
    # issue#425

    temp_dict = {
        OtherOptionsMenu.b_view_latest_searches: SearchListType.ALL,
        MainMenu.b_view_act_searches: SearchListType.ACTIVE,
        Commands.c_view_latest_searches: SearchListType.ALL,
        Commands.c_view_act_searches: SearchListType.ACTIVE,
    }
    search_list_type = temp_dict[ctx.update_params.got_message]

    use_experimental_view = ctx.db.get_search_follow_mode(ctx.user_id) and (ctx.db.is_user_tester(ctx.user_id))
    if use_experimental_view:
        _handle_view_searches_experimental_view(ctx, search_list_type)
    else:
        _handle_view_searches_usual_view(ctx, search_list_type)
