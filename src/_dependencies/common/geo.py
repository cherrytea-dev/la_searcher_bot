"""Shared geography / region-selection primitives across all messengers.

Centralises:

1.  **Federal district constants** — single source of truth for labels
    and normalised names used by VK and MAX (and eventually Telegram).
2.  **Region name compaction** — converts verbose subtype suffixes
    (e.g. `` – Активные поиски``) to short emoji markers (e.g. ``🔍``).
3.  **Navigation button labels** — ``← назад``, ``ещё →``, ``Завершить``,
    ``в начало``, etc.
4.  **Callback payload schema** — ``RegionCallbackPayload`` dataclass
    with JSON serialisation, shared by VK and MAX inline keyboards.
5.  **Pagination helpers** — split a region list into pages, compute
    navigation metadata.
6.  **Common text messages** — prompts shown during region selection.
7.  **Emoji legend** — explaining what each emoji marker means.

Usage::

    from _dependencies.common.geo import (
        FEDERAL_DISTRICTS,
        compact_region_name,
        REGION_EMOJI_LEGEND,
        RegionCallbackPayload,
        paginate_regions,
        NavButton,
    )
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NamedTuple

# ═══════════════════════════════════════════════════════════════════════════════
# Navigation button labels
# ═══════════════════════════════════════════════════════════════════════════════


class NavButton:
    """Shared navigation button labels used by region-selection keyboards."""

    BACK: str = '← назад'
    NEXT: str = 'ещё →'
    FINISH: str = 'Завершить'
    BACK_TO_START: str = 'в начало'
    CHOOSE_OTHER: str = 'выбрать другой регион'
    FED_DIST_PICK_OTHER: str = 'выбрать другой Федеральный Округ'


# ═══════════════════════════════════════════════════════════════════════════════
# Federal districts — single source of truth
# ═══════════════════════════════════════════════════════════════════════════════

#: (display_label, normalised_name) pairs.
#: ``normalised_name`` is used internally for DB lookups and callback payloads.
FEDERAL_DISTRICTS: tuple[tuple[str, str], ...] = (
    ('Центральный ФО', 'Центральный'),
    ('Северо-Западный ФО', 'Северо-Западный'),
    ('Южный ФО', 'Южный'),
    ('Северо-Кавказский ФО', 'Северо-Кавказский'),
    ('Приволжский ФО', 'Приволжский'),
    ('Уральский ФО', 'Уральский'),
    ('Сибирский ФО', 'Сибирский'),
    ('Дальневосточный ФО', 'Дальневосточный'),
    ('Прочие поиски по РФ', 'Прочие поиски по РФ'),
)

# Normalised names by label (for lookup)
_FED_DISTRICT_BY_LABEL: dict[str, str] = {label: norm for label, norm in FEDERAL_DISTRICTS}
# Labels by normalised name (for reverse lookup)
_FED_DISTRICT_LABEL: dict[str, str] = {norm: label for label, norm in FEDERAL_DISTRICTS}


def get_fed_district_normalised(label: str) -> str | None:
    """Return the normalised district name for a display label, or *None*.

    Example: ``'Центральный ФО'`` → ``'Центральный'``.
    """
    return _FED_DISTRICT_BY_LABEL.get(label.strip())


def get_fed_district_label(normalised: str) -> str | None:
    """Return the display label for a normalised district name, or *None*.

    Example: ``'Центральный'`` → ``'Центральный ФО'``.
    """
    return _FED_DISTRICT_LABEL.get(normalised.strip())


# ═══════════════════════════════════════════════════════════════════════════════
# Region name compaction (emoji suffixes)
# ═══════════════════════════════════════════════════════════════════════════════

_SUFFIX_TO_EMOJI: dict[str, str] = {
    ' – Активные поиски': '🔍',
    ' – Завершенные поиски': '✅',
    ' – Инфо поддержка': 'ℹ️',
    ' – Мероприятия': '📅',
}
# Build a regex once for efficient matching
_COMPACT_REGION_RE = re.compile('(' + '|'.join(re.escape(s) for s in _SUFFIX_TO_EMOJI) + ')$')

# Emoji legend shown above region selection keyboards so users understand
# what each emoji marker means.
REGION_EMOJI_LEGEND: str = (
    '🔍 — активные поиски\n' '✅ — завершённые поиски\n' 'ℹ️ — инфорг / поддержка\n' '📅 — мероприятия'
)


def compact_region_name(name: str) -> str:
    """Replace verbose subtype suffix with a short emoji marker at the beginning.

    ``"Москва – Активные поиски"`` → ``"🔍 Москва"``

    If no suffix matches, the original name is returned unchanged.
    """
    match = _COMPACT_REGION_RE.search(name)
    if match:
        suffix = match.group(1)
        region_part = name[: match.start()].strip()
        return _SUFFIX_TO_EMOJI[suffix] + ' ' + region_part
    return name


# ═══════════════════════════════════════════════════════════════════════════════
# Callback payload — shared by VK and MAX inline keyboards
# ═══════════════════════════════════════════════════════════════════════════════

# All possible ``cmd`` values used in region-selection callbacks.
CMD_DISTRICT_SELECT: str = 'district_select'
CMD_PAGINATE_TOGGLE: str = 'paginate_toggle'
CMD_PAGINATE_NAV: str = 'paginate_nav'
CMD_PAGINATE_FINISH: str = 'paginate_finish'


@dataclass(frozen=True)
class RegionCallbackPayload:
    """Structured payload for inline region-selection callbacks.

    Serialised as JSON for VK and MAX callback systems.
    """

    cmd: str
    district: str | None = None
    region: str | None = None
    page: int | None = None

    def to_dict(self) -> dict[str, object]:
        d: dict[str, object] = {'cmd': self.cmd}
        if self.district is not None:
            d['district'] = self.district
        if self.region is not None:
            d['region'] = self.region
        if self.page is not None:
            d['page'] = self.page
        return d


# ═══════════════════════════════════════════════════════════════════════════════
# Pagination helpers
# ═══════════════════════════════════════════════════════════════════════════════


class PageRange(NamedTuple):
    """Start (inclusive) and end (exclusive) indices for a page slice."""

    start: int
    end: int


class PageInfo(NamedTuple):
    """Metadata for a single pagination page."""

    items: list[str]
    page: int
    total_pages: int
    has_prev: bool
    has_next: bool
    slice: PageRange


def paginate_regions(regions: list[str], page: int, page_size: int = 6) -> PageInfo:
    """Split *regions* into pages and return metadata for *page* (zero-based).

    Args:
        regions: Full list of region display names.
        page: Zero-based page index.
        page_size: Number of items per page.

    Returns:
        A :class:`PageInfo` with the slice of items for the requested page.
    """
    total_pages = max(1, (len(regions) + page_size - 1) // page_size)
    start = page * page_size
    end = min(start + page_size, len(regions))
    return PageInfo(
        items=regions[start:end],
        page=page,
        total_pages=total_pages,
        has_prev=page > 0,
        has_next=page < total_pages - 1,
        slice=PageRange(start, end),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Common text messages
# ═══════════════════════════════════════════════════════════════════════════════

REGION_SELECTION_INTRO: str = (
    'Выберите федеральный округ, чтобы увидеть список регионов.\n\n'
    'Нажмите на регион, чтобы подписаться или отписаться.'
)

REGION_LIST_PROMPT: str = (
    '{district_text}\n\n' '{emoji_legend}\n\n' 'Нажмите на регион, чтобы подписаться или отписаться.'
)

REGION_SELECTION_DONE: str = '✅ Выбор региона завершён.'
REGION_CANNOT_REMOVE_LAST: str = 'Нельзя удалить последний регион.'
REGION_TOGGLED_ON: str = 'Регион добавлен!'
REGION_TOGGLED_OFF: str = 'Регион удалён.'
REGION_TOGGLED_ON_FMT: str = 'Регион "{}" добавлен!'
REGION_TOGGLED_OFF_FMT: str = 'Регион "{}" удалён.'
REGION_NOT_FOUND: str = 'Регион не найден.'
REGION_ERROR: str = 'Произошла ошибка. Попробуйте позже.'


def district_prompt(district_normalised: str) -> str:
    """Return the full prompt for region selection within a district.

    Args:
        district_normalised: Normalised district name (e.g. ``'Центральный'``).

    Returns:
        A user-facing message including the district name and emoji legend.
    """
    label = get_fed_district_label(district_normalised) or district_normalised
    return (
        f'Выберите регион в округе "{label}":\n\n'
        f'{REGION_EMOJI_LEGEND}\n\n'
        'Нажмите на регион, чтобы подписаться или отписаться.'
    )
