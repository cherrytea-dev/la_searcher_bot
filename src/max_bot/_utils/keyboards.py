"""Keyboard presets for the MAX bot.

Uses ``maxapi``'s ``InlineKeyboardBuilder``, ``CallbackButton``,
and ``RequestGeoLocationButton`` to build inline keyboards.

All presets are methods on ``MaxKeyboardPresets``, mirroring the
structure of ``VKKeyboardPresets`` in the VK bot.
"""

import json

from maxapi.types.attachments.buttons.attachment_button import AttachmentButton
from maxapi.types.attachments.buttons.callback_button import CallbackButton
from maxapi.types.attachments.buttons.request_geo_location_button import (
    RequestGeoLocationButton,
)
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from _dependencies.common.geo import (
    CMD_DISTRICT_SELECT,
    CMD_PAGINATE_FINISH,
    CMD_PAGINATE_NAV,
    CMD_PAGINATE_TOGGLE,
    FEDERAL_DISTRICTS,
    NavButton,
    RegionCallbackPayload,
    compact_region_name,
    paginate_regions,
)


class MaxKeyboardButtons:
    """Button label constants — single source of truth for all button labels."""

    # Navigation

    # Main menu
    BTN_DISABLE_NOTIFICATIONS: str = 'полностью отключить уведомления'
    BTN_ENABLE_NOTIFICATIONS: str = 'включить уведомления'
    BTN_SETTINGS_REGION: str = 'настроить регион поисков'
    BTN_SETTINGS_COORDS: str = 'настроить "домашние координаты"'
    BTN_SETTINGS_RADIUS: str = 'настроить максимальный радиус'

    # Coordinates sub-menu
    BTN_COORDS_ENTER: str = 'ввести "домашние координаты" вручную'
    BTN_COORDS_SEND_GEO: str = 'отправить геолокацию'
    BTN_COORDS_VIEW: str = 'посмотреть сохраненные координаты'
    BTN_COORDS_DELETE: str = 'удалить "домашние координаты"'

    # Radius settings
    BTN_RADIUS_SET: str = 'установить радиус'
    BTN_RADIUS_VIEW: str = 'посмотреть радиус'
    BTN_RADIUS_DELETE: str = 'удалить радиус'



class MaxKeyboardPresets(MaxKeyboardButtons):
    """Preset keyboard builders for the MAX bot."""

    # ─── Main Menu ────────────────────────────────────────────────────────

    @classmethod
    def main_menu(cls, notifications_disabled: bool = False) -> AttachmentButton:
        """Main menu with settings options."""
        delivery_status_button = (
            cls.BTN_ENABLE_NOTIFICATIONS if notifications_disabled else cls.BTN_DISABLE_NOTIFICATIONS
        )
        delivery_status_cmd = 'enable_notifications' if notifications_disabled else 'disable_notifications'
        return (
            InlineKeyboardBuilder()
            .row(CallbackButton(text=cls.BTN_SETTINGS_REGION, payload=json.dumps({'cmd': 'region'})))
            .row(CallbackButton(text=cls.BTN_SETTINGS_RADIUS, payload=json.dumps({'cmd': 'radius'})))
            .row(CallbackButton(text=cls.BTN_SETTINGS_COORDS, payload=json.dumps({'cmd': 'coords'})))
            .row(CallbackButton(text=delivery_status_button, payload=json.dumps({'cmd': delivery_status_cmd})))
            .as_markup()
        )

    # ─── Region Selection ─────────────────────────────────────────────────

    @classmethod
    def fed_districts_inline(cls) -> AttachmentButton:
        """Federal districts selection as inline callback buttons."""
        builder = InlineKeyboardBuilder()
        for label, district in FEDERAL_DISTRICTS:
            payload = RegionCallbackPayload(CMD_DISTRICT_SELECT, district=district)
            builder.add(CallbackButton(text=label, payload=json.dumps(payload.to_dict())))
        builder.adjust(2)
        finish_payload = RegionCallbackPayload(CMD_PAGINATE_FINISH)
        builder.row(CallbackButton(text=NavButton.FINISH, payload=json.dumps(finish_payload.to_dict())))
        return builder.as_markup()

    @classmethod
    def paginated_regions_inline(
        cls,
        region_buttons: list[str],
        page: int,
        district: str,
        page_size: int = 6,
        subscribed_ids: set[str] | None = None,
    ) -> AttachmentButton:
        """Inline keyboard with paginated region selection callback buttons.

        Region names are compacted via ``compact_region_name()`` — verbose
        subtype suffixes (e.g., " – Активные поиски") are replaced with short
        emoji markers (e.g., "🔍") to keep buttons readable.

        Uses two-column layout with *page_size*=6 (3 rows of 2 + 1 nav row).

        Args:
            region_buttons: Full list of region button labels.
            page: Zero-based page index.
            district: Normalized district name (e.g., 'Центральный').
            page_size: Number of items per page (default: 6).
            subscribed_ids: Set of region names that are already subscribed.
        """
        p = paginate_regions(region_buttons, page, page_size)

        if subscribed_ids is None:
            subscribed_ids = set()

        builder = InlineKeyboardBuilder()
        for region_name in p.items:
            compact_name = compact_region_name(region_name)
            display_name = f'✓ {compact_name}' if region_name in subscribed_ids else compact_name
            payload = RegionCallbackPayload(CMD_PAGINATE_TOGGLE, district=district, region=region_name, page=page)
            builder.add(CallbackButton(text=display_name, payload=json.dumps(payload.to_dict())))
        builder.adjust(2)

        # Navigation row
        nav_builder = InlineKeyboardBuilder()
        if p.has_prev:
            payload = RegionCallbackPayload(CMD_PAGINATE_NAV, district=district, page=page - 1)
            nav_builder.add(CallbackButton(text=NavButton.BACK, payload=json.dumps(payload.to_dict())))
        if p.has_next:
            payload = RegionCallbackPayload(CMD_PAGINATE_NAV, district=district, page=page + 1)
            nav_builder.add(CallbackButton(text=NavButton.NEXT, payload=json.dumps(payload.to_dict())))
        finish_payload = RegionCallbackPayload(CMD_PAGINATE_FINISH)
        nav_builder.add(CallbackButton(text=NavButton.FINISH, payload=json.dumps(finish_payload.to_dict())))
        builder.row(*nav_builder.payload[0])
        return builder.as_markup()

    # ─── Radius Settings ──────────────────────────────────────────────────

    @classmethod
    def radius_menu(cls) -> AttachmentButton:
        """Radius settings menu."""
        return (
            InlineKeyboardBuilder()
            .row(CallbackButton(text=cls.BTN_RADIUS_SET, payload=json.dumps({'cmd': 'radius_set'})))
            .row(CallbackButton(text=cls.BTN_RADIUS_VIEW, payload=json.dumps({'cmd': 'radius_view'})))
            .row(CallbackButton(text=cls.BTN_RADIUS_DELETE, payload=json.dumps({'cmd': 'radius_delete'})))
            .row(CallbackButton(text=NavButton.BACK, payload=json.dumps({'cmd': 'back_to_main'})))
            .as_markup()
        )

    # ─── Coordinates Settings ─────────────────────────────────────────────

    @classmethod
    def coords_menu(cls) -> AttachmentButton:
        """Coordinate settings menu."""
        return (
            InlineKeyboardBuilder()
            .row(CallbackButton(text=cls.BTN_COORDS_ENTER, payload=json.dumps({'cmd': 'coords_enter'})))
            .row(RequestGeoLocationButton(text=cls.BTN_COORDS_SEND_GEO))
            .row(CallbackButton(text=cls.BTN_COORDS_VIEW, payload=json.dumps({'cmd': 'coords_view'})))
            .row(CallbackButton(text=cls.BTN_COORDS_DELETE, payload=json.dumps({'cmd': 'coords_delete'})))
            .row(CallbackButton(text=NavButton.BACK, payload=json.dumps({'cmd': 'back_to_main'})))
            .as_markup()
        )

    # ─── Utility ──────────────────────────────────────────────────────────

    @classmethod
    def back_to_main(cls) -> AttachmentButton:
        """Single 'back to main menu' button."""
        return (
            InlineKeyboardBuilder()
            .row(CallbackButton(text=NavButton.BACK, payload=json.dumps({'cmd': 'back_to_main'})))
            .as_markup()
        )
