"""Pydantic models for message_params shared across cloud functions."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, field_validator


class MessageParams(BaseModel):
    """Unified model for text and coordinate message parameters.

    Discriminated by ``kind``:
    - ``"text"`` — use ``parse_mode``, ``disable_web_page_preview``, optional ``reply_markup``
    - ``"coords"`` — use ``latitude``, ``longitude``
    """

    kind: Literal['text', 'coords']

    # ── text fields ──────────────────────────────────────────────────
    parse_mode: str | None = None
    disable_web_page_preview: bool | None = None
    reply_markup: dict[str, Any] | None = None

    # ── coords fields ────────────────────────────────────────────────
    latitude: float | None = None
    longitude: float | None = None

    @field_validator('disable_web_page_preview', mode='before')
    @classmethod
    def _coerce_disable_web_page_preview(cls, v: object) -> bool | None:
        """Handle legacy string 'True'/'False' values from DB."""
        if v is None:
            return None
        if isinstance(v, str):
            return v == 'True'
        return bool(v)

    @field_validator('latitude', 'longitude', mode='before')
    @classmethod
    def _coerce_float(cls, v: str | float | int | None) -> float | None:
        """Coerce string values from DB to float."""
        if v is None:
            return None
        return float(v)

    @classmethod
    def new_text(
        cls,
        parse_mode: str,
        disable_web_page_preview: bool,
        reply_markup: dict[str, Any] | None = None,
    ) -> MessageParams:
        """Create a text message params instance."""
        return cls(
            kind='text',
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview,
            reply_markup=reply_markup,
        )

    @classmethod
    def new_coords(cls, latitude: float, longitude: float) -> MessageParams:
        """Create a coords message params instance."""
        return cls(kind='coords', latitude=latitude, longitude=longitude)
