"""Data models for send_notifications."""

import datetime
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, TypeAdapter, field_validator


@dataclass
class TimeAnalytics:
    script_start_time: datetime.datetime = field(default_factory=datetime.datetime.now)
    notif_times: list[float] = field(default_factory=list)
    delays: list[float] = field(default_factory=list)
    parsed_times: list[float] = field(default_factory=list)


# ── MessageParams Pydantic models ──────────────────────────────────


class TextMessageParams(BaseModel):
    """Parameters for text messages."""

    parse_mode: str
    disable_web_page_preview: bool
    reply_markup: dict[str, Any] | None = None

    @field_validator('disable_web_page_preview', mode='before')
    @classmethod
    def _coerce_disable_web_page_preview(cls, v: object) -> bool:
        """Handle legacy string 'True'/'False' values from DB."""
        if isinstance(v, str):
            return v == 'True'
        return bool(v)


class CoordsMessageParams(BaseModel):
    """Parameters for coordinate messages."""

    latitude: float
    longitude: float

    @field_validator('latitude', 'longitude', mode='before')
    @classmethod
    def _coerce_float(cls, v: str | float | int) -> float:
        """Coerce string values from DB to float."""
        return float(v)


# TypeAdapter for parsing raw dicts (from DB) into the right MessageParams variant.
# Uses Pydantic smart union matching: tries each model and picks the first that validates.
_message_params_adapter: TypeAdapter[TextMessageParams | CoordsMessageParams] = TypeAdapter(
    TextMessageParams | CoordsMessageParams
)


def parse_message_params(data: dict[str, Any]) -> TextMessageParams | CoordsMessageParams:
    """Parse a raw dict into TextMessageParams or CoordsMessageParams.

    Uses Pydantic smart union — tries each model, picks the first that validates.
    """
    return _message_params_adapter.validate_python(data)
