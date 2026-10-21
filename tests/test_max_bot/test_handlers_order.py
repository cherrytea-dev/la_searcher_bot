"""Guards for the max_bot handlers package registration.

maxapi executes the FIRST matching handler description and stops, so the
import order in ``handlers/__init__.py`` is behavior: the catch-all
``on_unknown_text`` must be registered after ``/start``, the DB-state text
handlers and the geo-location handler.

The full-set assertion mirrors the Telegram-side guard
(``tests/test_communicate/test_handlers/test_registry_complete.py``): if a
domain module is dropped from ``handlers/__init__.py``, its handlers vanish
silently and every other test still passes.
"""

from max_bot._utils import handlers

EXPECTED_HANDLER_NAMES = {
    'on_bot_started',
    'on_start',
    'on_back_to_main',
    'on_disable_notifications',
    'on_enable_notifications',
    'on_reset_settings',
    'on_reset_confirm',
    'on_reset_cancel',
    'on_region_menu',
    'on_district_select',
    'on_paginate_nav',
    'on_paginate_toggle',
    'on_paginate_finish',
    'on_radius_menu',
    'on_radius_set',
    'on_radius_view',
    'on_radius_delete',
    'on_radius_text',
    'on_coords_menu',
    'on_coords_enter',
    'on_coords_view',
    'on_coords_delete',
    'on_coords_text',
    'on_geo_location',
    'on_unknown_text',
}


def _handler_index(name: str) -> int:
    for index, handler in enumerate(handlers.router.event_handlers):
        if handler.func_event.__qualname__ == name:
            return index
    raise AssertionError(f'Handler {name!r} is not registered on the shared router')


def test_all_handlers_registered() -> None:
    names = {handler.func_event.__qualname__ for handler in handlers.router.event_handlers}
    assert names == EXPECTED_HANDLER_NAMES


def test_fallback_is_registered_last() -> None:
    fallback = _handler_index('on_unknown_text')

    assert _handler_index('on_start') < fallback
    assert _handler_index('on_radius_text') < fallback
    assert _handler_index('on_coords_text') < fallback


def test_geo_location_registered_before_fallback() -> None:
    assert _handler_index('on_geo_location') < _handler_index('on_unknown_text')
