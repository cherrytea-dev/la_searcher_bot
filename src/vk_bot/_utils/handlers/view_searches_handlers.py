"""
Phase 2B: VK Bot search viewing handlers.

Handles:
- Viewing active searches (per region)
- Viewing latest 20 searches
- Follow/unfollow searches via text commands (+12345 / -12345)
- Search follow mode toggle
"""

import logging
import re
from datetime import datetime, timedelta

import sqlalchemy as sa

from _dependencies.common.commons import SearchFollowingMode
from _dependencies.common.misc import age_writer, time_counter_since_search_start

from ..common import SEARCH_URL_PREFIX, VKHandlerResult, VKMessage
from ..database import DialogState, db
from ..keyboards import VKKeyboardButtons, VKKeyboardPresets
from ..services.message_formatter import (
    no_active_searches_found,
    search_follow_intro,
    search_follow_mode_off,
    search_follow_mode_on,
)

# Status emoji mapping for VK
STATUS_EMOJI = {
    'Ищем': '🟠',
    'Возобновлен': '🟠',
    'НЖ': '⚫',
    'НП': '✅',
    'СТОП': '⏹️',
}


def _fetch_active_searches(user_id: int) -> list[dict]:
    """Fetch active searches for user's subscribed regions.

    Returns list of dicts with keys: search_forum_num, display_name, status,
    search_start_time, age, latitude, longitude, forum_folder_id.
    """
    regions = db().get_user_regions(user_id)
    if not regions:
        return []

    # regions is a list of folder_id values from user_regional_preferences
    folder_ids = list(regions)
    if not folder_ids:
        return []

    sixty_days_ago = datetime.now() - timedelta(days=60)

    with db().connect() as conn:
        stmt = sa.text("""
            SELECT s.search_forum_num, s.display_name, s.status,
                   s.search_start_time, s.age,
                   sc.latitude, sc.longitude,
                   s.forum_folder_id
            FROM searches s
            LEFT JOIN search_coordinates sc ON sc.search_forum_num = s.search_forum_num
            WHERE s.forum_folder_id IN :folder_ids
              AND s.search_start_time >= :cutoff
              AND (s.status = 'Ищем' OR s.status = 'Возобновлен')
            ORDER BY s.search_start_time DESC
            LIMIT 50
        """)
        result = conn.execute(stmt, folder_ids=tuple(folder_ids), cutoff=sixty_days_ago)
        rows = result.fetchall()

    return [
        {
            'search_forum_num': row[0],
            'display_name': row[1] or f'Поиск #{row[0]}',
            'status': row[2] or '',
            'search_start_time': row[3],
            'age': row[4],
            'latitude': row[5],
            'longitude': row[6],
            'forum_folder_id': row[7],
        }
        for row in rows
    ]


def _fetch_latest_searches(user_id: int) -> list[dict]:
    """Fetch latest 20 searches across all user's regions."""
    regions = db().get_user_regions(user_id)
    if not regions:
        return []

    folder_ids = list(regions)
    if not folder_ids:
        return []

    with db().connect() as conn:
        stmt = sa.text("""
            SELECT s.search_forum_num, s.display_name, s.status,
                   s.search_start_time, s.age,
                   sc.latitude, sc.longitude,
                   s.forum_folder_id
            FROM searches s
            LEFT JOIN search_coordinates sc ON sc.search_forum_num = s.search_forum_num
            WHERE s.forum_folder_id IN :folder_ids
            ORDER BY s.search_start_time DESC
            LIMIT 20
        """)
        result = conn.execute(stmt, folder_ids=tuple(folder_ids))
        rows = result.fetchall()

    return [
        {
            'search_forum_num': row[0],
            'display_name': row[1] or f'Поиск #{row[0]}',
            'status': row[2] or '',
            'search_start_time': row[3],
            'age': row[4],
            'latitude': row[5],
            'longitude': row[6],
            'forum_folder_id': row[7],
        }
        for row in rows
    ]


def _get_user_followed_ids(user_id: int) -> set[int]:
    """Get set of search IDs that user follows or blacklists."""
    followed = set()
    try:
        with db().connect() as conn:
            stmt = sa.text("""
                SELECT search_id, search_following_mode
                FROM user_pref_search_whitelist
                WHERE user_id = :user_id
            """)
            result = conn.execute(stmt, user_id=user_id)
            for row in result:
                if row[1] in (SearchFollowingMode.ON, SearchFollowingMode.OFF):
                    followed.add(row[0])
    except Exception:
        logging.exception('Error fetching followed searches')
    return followed


def _format_search_text(search: dict, is_followed: bool, is_blacklisted: bool) -> str:
    """Format a single search for display."""
    status_emoji = STATUS_EMOJI.get(search['status'], '❓')
    time_text = ''
    if search['search_start_time']:
        phrase, days = time_counter_since_search_start(search['search_start_time'])
        time_text = f' ({phrase})'

    age_text = ''
    if search['age']:
        age_text = f', {search["age"]} {age_writer(search["age"])}'

    follow_mark = ''
    if is_followed:
        follow_mark = ' 👀'
    elif is_blacklisted:
        follow_mark = ' ❌'

    link = f'{SEARCH_URL_PREFIX}{search["search_forum_num"]}'

    name = search['display_name'] or f'Поиск #{search["search_forum_num"]}'

    return f'{status_emoji}{follow_mark} {name}{age_text}{time_text}\n' f'{link}\n'


def _group_searches_by_folder(searches: list[dict]) -> dict[int, list[dict]]:
    """Group searches by forum_folder_id."""
    groups: dict[int, list[dict]] = {}
    for s in searches:
        fid = s['forum_folder_id']
        if fid not in groups:
            groups[fid] = []
        groups[fid].append(s)
    return groups


def handle_view_search_menu(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle 'посмотреть актуальные поиски' main menu button — show search view menu."""
    text = vk_message.text.strip().lower()
    if text != 'посмотреть актуальные поиски':
        return None

    return VKHandlerResult(
        text='Выберите режим просмотра поисков:',
        keyboard=VKKeyboardPresets.search_view_menu(),
    )


def handle_active_searches(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Show active searches for user's subscribed regions."""
    text = vk_message.text.strip().lower()
    if text != VKKeyboardButtons.BTN_SEARCH_ACTIVE.lower():
        # Also check if it's the main menu "🔥 карта поисков 🔥" button
        if 'карта поисков' not in text:
            return None

    searches = _fetch_active_searches(user_id)
    followed_ids = _get_user_followed_ids(user_id)

    if not searches:
        return VKHandlerResult(
            text=no_active_searches_found(),
            keyboard=VKKeyboardPresets.main_menu(),
        )

    # Group by folder and format
    groups = _group_searches_by_folder(searches)

    # Format message
    lines = ['🔍 Активные поиски:', '']
    for fid, folder_searches in groups.items():
        lines.append(f'📁 Регион #{fid}:')
        for s in folder_searches:
            is_followed = s['search_forum_num'] in followed_ids
            is_blacklisted = False  # We only track followed set for simplicity
            lines.append(_format_search_text(s, is_followed, is_blacklisted))
        lines.append('')

    text_result = '\n'.join(lines)

    # If too long, truncate
    if len(text_result) > 4000:
        text_result = text_result[:3997] + '...'

    return VKHandlerResult(
        text=text_result,
        keyboard=VKKeyboardPresets.search_navigation(),
    )


def handle_latest_searches(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Show latest 20 searches across all regions."""
    text = vk_message.text.strip().lower()
    if text != VKKeyboardButtons.BTN_SEARCH_LAST_20.lower():
        return None

    searches = _fetch_latest_searches(user_id)
    followed_ids = _get_user_followed_ids(user_id)

    if not searches:
        return VKHandlerResult(
            text='В ваших регионах пока нет завершенных поисков.',
            keyboard=VKKeyboardPresets.main_menu(),
        )

    lines = ['📋 Последние 20 поисков:', '']
    for s in searches:
        is_followed = s['search_forum_num'] in followed_ids
        lines.append(_format_search_text(s, is_followed, False))

    text_result = '\n'.join(lines)

    if len(text_result) > 4000:
        text_result = text_result[:3997] + '...'

    return VKHandlerResult(
        text=text_result,
        keyboard=VKKeyboardPresets.search_navigation(),
    )


def handle_search_follow_menu(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle 'управление отслеживанием' or 'отслеживание поисков' button."""
    text = vk_message.text.strip().lower()
    if text not in (VKKeyboardButtons.BTN_FOLLOW_MANAGE.lower(), VKKeyboardButtons.BTN_SEARCH_FOLLOW_MGMT.lower()):
        return None

    follow_mode = db().get_search_follow_mode(user_id)
    status = search_follow_mode_on() if follow_mode else search_follow_mode_off()

    return VKHandlerResult(
        text=f'{search_follow_intro()}\n\n{status}',
        keyboard=VKKeyboardPresets.search_follow_menu(),
    )


def handle_follow_mode_toggle(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Toggle search follow mode on/off."""
    text = vk_message.text.strip().lower()

    if text == VKKeyboardButtons.BTN_FOLLOW_ENABLE.lower():
        db().set_search_follow_mode(user_id, True)
        return VKHandlerResult(
            text=search_follow_mode_on(),
            keyboard=VKKeyboardPresets.search_follow_menu(),
        )

    elif text == VKKeyboardButtons.BTN_FOLLOW_DISABLE.lower():
        db().set_search_follow_mode(user_id, False)
        return VKHandlerResult(
            text=search_follow_mode_off(),
            keyboard=VKKeyboardPresets.search_follow_menu(),
        )

    elif text == VKKeyboardButtons.BTN_FOLLOW_SHOW.lower():
        # Get searches that user follows
        followed_ids = _get_user_followed_ids(user_id)
        if not followed_ids:
            return VKHandlerResult(
                text='У вас нет отслеживаемых поисков.\n\n'
                'Чтобы начать отслеживать поиск, отправьте:\n'
                '+<номер поиска>\n\n'
                'Например: +12345',
                keyboard=VKKeyboardPresets.search_follow_menu(),
            )

        with db().connect() as conn:
            stmt = sa.text("""
                SELECT search_forum_num, display_name, status
                FROM searches
                WHERE search_forum_num IN :ids
                ORDER BY search_start_time DESC
            """)
            result = conn.execute(stmt, ids=tuple(followed_ids))
            rows = result.fetchall()

        lines = ['👀 Отслеживаемые поиски:', '']
        for row in rows:
            sid, name, status = row
            name = name or f'Поиск #{sid}'
            link = f'{SEARCH_URL_PREFIX}{sid}'
            lines.append(f'{STATUS_EMOJI.get(status, "❓")} {name}')
            lines.append(link)
            lines.append(f'  Чтобы отписаться: -{sid}')
            lines.append('')

        text_result = '\n'.join(lines)
        if len(text_result) > 4000:
            text_result = text_result[:3997] + '...'

        return VKHandlerResult(
            text=text_result,
            keyboard=VKKeyboardPresets.search_follow_menu(),
        )

    return None


def handle_follow_unfollow_command(
    vk_message: VKMessage, state: DialogState | None, user_id: int
) -> VKHandlerResult | None:
    """Handle +<topic_id> (follow) and -<topic_id> (unfollow/blacklist) commands.

    Pattern:
    - +12345 → follow search (👀)
    - -12345 → if followed → unfollow; if not followed → blacklist (❌)
    """
    text = vk_message.text.strip()

    # Match +<number> or -<number>
    match = re.match(r'^([+-])(\d+)$', text)
    if not match:
        return None

    action = match.group(1)  # '+' or '-'
    topic_id = int(match.group(2))

    # Check if search exists
    with db().connect() as conn:
        stmt = sa.text('SELECT search_forum_num FROM searches WHERE search_forum_num = :sid')
        result = conn.execute(stmt, sid=topic_id)
        if not result.fetchone():
            return VKHandlerResult(
                text=f'Поиск #{topic_id} не найден. Проверьте номер.',
                keyboard=VKKeyboardPresets.search_navigation(),
            )

    # Get current follow state for this search
    current_mode = None
    try:
        with db().connect() as conn:
            stmt = sa.text("""
                SELECT search_following_mode FROM user_pref_search_whitelist
                WHERE user_id = :user_id AND search_id = :sid
            """)
            result = conn.execute(stmt, user_id=user_id, sid=topic_id)
            row = result.fetchone()
            if row:
                current_mode = row[0]
    except Exception:
        logging.exception('Error checking follow state')

    if action == '+':
        # Follow
        if current_mode == SearchFollowingMode.ON:
            return VKHandlerResult(
                text=f'Вы уже следите за поиском #{topic_id} 👀',
                keyboard=VKKeyboardPresets.search_navigation(),
            )
        db().record_search_whiteness(user_id, topic_id, SearchFollowingMode.ON)
        return VKHandlerResult(
            text=f'✅ Теперь вы следите за поиском #{topic_id}\n' f'Вы будете получать уведомления об изменениях.',
            keyboard=VKKeyboardPresets.search_navigation(),
        )

    else:  # action == '-'
        if current_mode == SearchFollowingMode.OFF:
            # Already blacklisted — remove from whitelist entirely (cycle back to neutral)
            db().record_search_whiteness(user_id, topic_id, '  ')
            return VKHandlerResult(
                text=f'Отслеживание поиска #{topic_id} сброшено.',
                keyboard=VKKeyboardPresets.search_navigation(),
            )
        elif current_mode == SearchFollowingMode.ON:
            # Was following → blacklist
            db().record_search_whiteness(user_id, topic_id, SearchFollowingMode.OFF)
            return VKHandlerResult(
                text=f'⛔ Вы больше не будете получать уведомления по поиску #{topic_id}.',
                keyboard=VKKeyboardPresets.search_navigation(),
            )
        else:
            # Not followed → blacklist
            db().record_search_whiteness(user_id, topic_id, SearchFollowingMode.OFF)
            return VKHandlerResult(
                text=f'⛔ Поиск #{topic_id} добавлен в игнорируемые.',
                keyboard=VKKeyboardPresets.search_navigation(),
            )


def handle_more_searches(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle 'еще поиски' button — return to search view menu."""
    text = vk_message.text.strip().lower()
    if text != VKKeyboardButtons.BTN_MORE_SEARCHES.lower():
        return None

    return VKHandlerResult(
        text='Выберите режим просмотра поисков:',
        keyboard=VKKeyboardPresets.search_view_menu(),
    )


router: list = [
    handle_view_search_menu,
    handle_active_searches,
    handle_latest_searches,
    handle_search_follow_menu,
    handle_follow_mode_toggle,
    handle_follow_unfollow_command,
    handle_more_searches,
]
