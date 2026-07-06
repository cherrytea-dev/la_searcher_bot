"""VK Bot search viewing handlers.

Handles:
- Viewing active searches (per region)
- Viewing latest 20 searches
- Follow/unfollow searches via text commands (+12345 / -12345)
- Search follow mode toggle

Each handler takes a VKHandlerContext and returns None.
Uses ctx.reply() to send responses and ctx.is_consumed to signal handling.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

import sqlalchemy as sa

from _dependencies.common.commons import SearchFollowingMode
from _dependencies.common.misc import age_writer, time_counter_since_search_start

from ..common import VKHandlerContext
from ..decorators import vk_handle
from ..keyboards import VKKeyboardButtons, VKKeyboardPresets
from ..services.message_formatter import (
    SEARCH_URL_PREFIX,
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


def _fetch_active_searches(ctx: VKHandlerContext) -> list[dict]:
    """Fetch active searches for user's subscribed regions."""
    regions = ctx.db.get_user_regions(ctx.user_id)
    if not regions:
        return []

    folder_ids = list(regions)
    if not folder_ids:
        return []

    sixty_days_ago = datetime.now() - timedelta(days=60)

    with ctx.db.connect() as conn:
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
        result = conn.execute(stmt, dict(folder_ids=tuple(folder_ids), cutoff=sixty_days_ago))
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


def _fetch_latest_searches(ctx: VKHandlerContext) -> list[dict]:
    """Fetch latest 20 searches across all user's regions."""
    regions = ctx.db.get_user_regions(ctx.user_id)
    if not regions:
        return []

    folder_ids = list(regions)
    if not folder_ids:
        return []

    with ctx.db.connect() as conn:
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
        result = conn.execute(stmt, dict(folder_ids=tuple(folder_ids)))
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


def _get_user_followed_ids(ctx: VKHandlerContext) -> set[int]:
    """Get set of search IDs that user follows or blacklists."""
    followed = set()
    try:
        with ctx.db.connect() as conn:
            stmt = sa.text("""
                SELECT search_id, search_following_mode
                FROM user_pref_search_whitelist
                WHERE user_id = :user_id
            """)
            result = conn.execute(stmt, dict(user_id=ctx.user_id))
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


# ═══════════════════════════════════════════════════════════════════════
# Search view handlers
# ═══════════════════════════════════════════════════════════════════════


@vk_handle(text='посмотреть актуальные поиски')
def handle_view_search_menu(ctx: VKHandlerContext) -> None:
    """Handle 'посмотреть актуальные поиски' main menu button — show search view menu."""
    ctx.reply(
        text='Выберите режим просмотра поисков:',
        keyboard=VKKeyboardPresets.search_view_menu(),
    )


@vk_handle(text=[VKKeyboardButtons.BTN_SEARCH_ACTIVE])
def handle_active_searches(ctx: VKHandlerContext) -> None:
    """Show active searches for user's subscribed regions."""
    searches = _fetch_active_searches(ctx)
    followed_ids = _get_user_followed_ids(ctx)

    if not searches:
        ctx.reply(
            text=no_active_searches_found(),
            keyboard=VKKeyboardPresets.main_menu(),
        )
        return

    groups = _group_searches_by_folder(searches)

    lines = ['🔍 Активные поиски:', '']
    for fid, folder_searches in groups.items():
        lines.append(f'📁 Регион #{fid}:')
        for s in folder_searches:
            is_followed = s['search_forum_num'] in followed_ids
            lines.append(_format_search_text(s, is_followed, False))
        lines.append('')

    text_result = '\n'.join(lines)

    if len(text_result) > 4000:
        text_result = text_result[:3997] + '...'

    ctx.reply(
        text=text_result,
        keyboard=VKKeyboardPresets.search_navigation(),
    )


@vk_handle(text=VKKeyboardButtons.BTN_SEARCH_LAST_20)
def handle_latest_searches(ctx: VKHandlerContext) -> None:
    """Show latest 20 searches across all regions."""
    searches = _fetch_latest_searches(ctx)
    followed_ids = _get_user_followed_ids(ctx)

    if not searches:
        ctx.reply(
            text='В ваших регионах пока нет завершенных поисков.',
            keyboard=VKKeyboardPresets.main_menu(),
        )
        return

    lines = ['📋 Последние 20 поисков:', '']
    for s in searches:
        is_followed = s['search_forum_num'] in followed_ids
        lines.append(_format_search_text(s, is_followed, False))

    text_result = '\n'.join(lines)

    if len(text_result) > 4000:
        text_result = text_result[:3997] + '...'

    ctx.reply(
        text=text_result,
        keyboard=VKKeyboardPresets.search_navigation(),
    )


@vk_handle(text=[VKKeyboardButtons.BTN_FOLLOW_MANAGE, VKKeyboardButtons.BTN_SEARCH_FOLLOW_MGMT])
def handle_search_follow_menu(ctx: VKHandlerContext) -> None:
    """Handle 'управление отслеживанием' or 'отслеживание поисков' button."""
    follow_mode = ctx.db.get_search_follow_mode(ctx.user_id)
    status = search_follow_mode_on() if follow_mode else search_follow_mode_off()

    ctx.reply(
        text=f'{search_follow_intro()}\n\n{status}',
        keyboard=VKKeyboardPresets.search_follow_menu(),
    )


@vk_handle(text=VKKeyboardButtons.BTN_FOLLOW_ENABLE)
def handle_follow_enable(ctx: VKHandlerContext) -> None:
    """Handle 'включить режим отслеживания' button."""
    ctx.db.set_search_follow_mode(ctx.user_id, True)
    ctx.reply(
        text=search_follow_mode_on(),
        keyboard=VKKeyboardPresets.search_follow_menu(),
    )


@vk_handle(text=VKKeyboardButtons.BTN_FOLLOW_DISABLE)
def handle_follow_disable(ctx: VKHandlerContext) -> None:
    """Handle 'выключить режим отслеживания' button."""
    ctx.db.set_search_follow_mode(ctx.user_id, False)
    ctx.reply(
        text=search_follow_mode_off(),
        keyboard=VKKeyboardPresets.search_follow_menu(),
    )


@vk_handle(text=VKKeyboardButtons.BTN_FOLLOW_SHOW)
def handle_follow_show(ctx: VKHandlerContext) -> None:
    """Handle 'показать отслеживаемые поиски' button."""
    followed_ids = _get_user_followed_ids(ctx)
    if not followed_ids:
        ctx.reply(
            text='У вас нет отслеживаемых поисков.\n\n'
            'Чтобы начать отслеживать поиск, отправьте:\n'
            '+<номер поиска>\n\n'
            'Например: +12345',
            keyboard=VKKeyboardPresets.search_follow_menu(),
        )
        return

    with ctx.db.connect() as conn:
        stmt = sa.text("""
            SELECT search_forum_num, display_name, status
            FROM searches
            WHERE search_forum_num IN :ids
            ORDER BY search_start_time DESC
        """)
        result = conn.execute(stmt, dict(ids=tuple(followed_ids)))
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

    ctx.reply(
        text=text_result,
        keyboard=VKKeyboardPresets.search_follow_menu(),
    )


@vk_handle(text_regex=r'^[+-]\d+$')
def handle_follow_unfollow_command(ctx: VKHandlerContext) -> None:
    """Handle +<topic_id> (follow) and -<topic_id> (unfollow/blacklist) commands.

    Pattern:
    - +12345 → follow search (👀)
    - -12345 → if followed → unfollow; if not followed → blacklist (❌)
    """
    text = ctx.message.text.strip()
    match = re.match(r'^([+-])(\d+)$', text)
    if not match:
        return

    action = match.group(1)
    topic_id = int(match.group(2))

    with ctx.db.connect() as conn:
        stmt = sa.text('SELECT search_forum_num FROM searches WHERE search_forum_num = :sid')
        result = conn.execute(stmt, dict(sid=topic_id))
        if not result.fetchone():
            ctx.reply(
                text=f'Поиск #{topic_id} не найден. Проверьте номер.',
                keyboard=VKKeyboardPresets.search_navigation(),
            )
            return

    current_mode = None
    try:
        with ctx.db.connect() as conn:
            stmt = sa.text("""
                SELECT search_following_mode FROM user_pref_search_whitelist
                WHERE user_id = :user_id AND search_id = :sid
            """)
            result = conn.execute(stmt, dict(user_id=ctx.user_id, sid=topic_id))
            row = result.fetchone()
            if row:
                current_mode = row[0]
    except Exception:
        logging.exception('Error checking follow state')

    if action == '+':
        if current_mode == SearchFollowingMode.ON:
            ctx.reply(
                text=f'Вы уже следите за поиском #{topic_id} 👀',
                keyboard=VKKeyboardPresets.search_navigation(),
            )
            return
        ctx.db.record_search_whiteness(ctx.user_id, topic_id, SearchFollowingMode.ON)
        ctx.reply(
            text=f'✅ Теперь вы следите за поиском #{topic_id}\n' f'Вы будете получать уведомления об изменениях.',
            keyboard=VKKeyboardPresets.search_navigation(),
        )
        return

    else:  # action == '-'
        if current_mode == SearchFollowingMode.OFF:
            ctx.db.record_search_whiteness(ctx.user_id, topic_id, '  ')
            ctx.reply(
                text=f'Отслеживание поиска #{topic_id} сброшено.',
                keyboard=VKKeyboardPresets.search_navigation(),
            )
            return
        elif current_mode == SearchFollowingMode.ON:
            ctx.db.record_search_whiteness(ctx.user_id, topic_id, SearchFollowingMode.OFF)
            ctx.reply(
                text=f'⛔ Вы больше не будете получать уведомления по поиску #{topic_id}.',
                keyboard=VKKeyboardPresets.search_navigation(),
            )
            return
        else:
            ctx.db.record_search_whiteness(ctx.user_id, topic_id, SearchFollowingMode.OFF)
            ctx.reply(
                text=f'⛔ Поиск #{topic_id} добавлен в игнорируемые.',
                keyboard=VKKeyboardPresets.search_navigation(),
            )
            return


@vk_handle(text=VKKeyboardButtons.BTN_MORE_SEARCHES)
def handle_more_searches(ctx: VKHandlerContext) -> None:
    """Handle 'еще поиски' button — return to search view menu."""
    ctx.reply(
        text='Выберите режим просмотра поисков:',
        keyboard=VKKeyboardPresets.search_view_menu(),
    )
