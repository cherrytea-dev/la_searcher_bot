"""MAX bot handlers: aggregated registration point.

Порядок импортов — это поведение: maxapi выполняет первое подошедшее
описание, а on_unknown_text (catch-all) обязан регистрироваться последним.
"""

# ruff: noqa: I001 — import order is behavior (first matching handler wins),
# so isort must not alphabetize this registration list.

from ..common import _ensure_user_registered, router

from . import (
    onboarding_handlers,  # on_start — обязан регистрироваться до fallback
    settings_handlers,
    region_select_handlers,
    radius_settings_handlers,  # on_radius_text (DBStateFilter) — до fallback
    coords_settings_handlers,  # on_coords_text (DBStateFilter) — до fallback
    other_handlers,  # on_geo_location, on_unknown_text — строго последним
)
