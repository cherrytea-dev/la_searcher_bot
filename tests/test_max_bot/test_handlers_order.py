"""Registration-order guards for the max_bot handlers package.

maxapi executes the FIRST matching handler description and stops, so the
import order in ``handlers/__init__.py`` is behavior: the catch-all
``on_unknown_text`` must be registered after ``/start``, the DB-state text
handlers and the geo-location handler.
"""

from max_bot._utils import handlers


def _handler_index(name: str) -> int:
    for index, handler in enumerate(handlers.router.event_handlers):
        if handler.func_event.__qualname__ == name:
            return index
    raise AssertionError(f'Handler {name!r} is not registered on the shared router')


def test_fallback_is_registered_last() -> None:
    fallback = _handler_index('on_unknown_text')

    assert _handler_index('on_start') < fallback
    assert _handler_index('on_radius_text') < fallback
    assert _handler_index('on_coords_text') < fallback


def test_geo_location_registered_before_fallback() -> None:
    assert _handler_index('on_geo_location') < _handler_index('on_unknown_text')
