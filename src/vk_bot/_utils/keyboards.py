import json
from typing import Literal

from .common import ButtonColor


class VKKeyboard:
    """Builder for VK keyboard JSON.

    VK keyboard format:
    {
        "one_time": false,
        "inline": false,
        "buttons": [
            [
                {
                    "action": {"type": "text", "label": "...", "payload": "..."},
                    "color": "primary"
                }
            ]
        ]
    }
    """

    @staticmethod
    def _text_button(label: str, color: ButtonColor = 'secondary', payload: str = '') -> dict:
        return {
            'action': {
                'type': 'text',
                'label': label,
                'payload': payload or json.dumps({'button': label}, ensure_ascii=False),
            },
            'color': color,
        }

    @staticmethod
    def _url_button(label: str, url: str) -> dict:
        return {
            'action': {
                'type': 'open_link',
                'label': label,
                'link': url,
            },
        }

    @staticmethod
    def _location_button() -> dict:
        """Request location button (VK API, but not supported in all clients)."""
        return {
            'action': {
                'type': 'location',
            },
        }

    @classmethod
    def one_column(cls, buttons: list[str], color: ButtonColor = 'secondary') -> dict:
        """Each button in its own row (vertical list)."""
        return {
            'one_time': False,
            'inline': False,
            'buttons': [[cls._text_button(btn, color)] for btn in buttons],
        }

    @classmethod
    def two_columns(cls, buttons: list[str], color: ButtonColor = 'secondary') -> dict:
        """Buttons in pairs per row. If odd count, last one is alone."""
        rows: list[list[dict]] = []
        for i in range(0, len(buttons), 2):
            row = [cls._text_button(buttons[i], color)]
            if i + 1 < len(buttons):
                row.append(cls._text_button(buttons[i + 1], color))
            rows.append(row)
        return {'one_time': False, 'inline': False, 'buttons': rows}

    @classmethod
    def one_row(cls, buttons: list[str], color: ButtonColor = 'secondary') -> dict:
        """All buttons in a single row (max 4-5 buttons)."""
        return {
            'one_time': False,
            'inline': False,
            'buttons': [[cls._text_button(btn, color) for btn in buttons]],
        }

    @classmethod
    def inline_url(cls, buttons: list[tuple[str, str]]) -> dict:
        """Inline keyboard with URL buttons. buttons = [(label, url), ...]"""
        return {
            'inline': True,
            'buttons': [[cls._url_button(label, url)] for label, url in buttons],
        }

    @classmethod
    def empty(cls) -> dict:
        """Empty keyboard (removes current keyboard)."""
        return {'one_time': False, 'inline': False, 'buttons': []}

    # ─── Preset menus ────────────────────────────────────────────────

    @classmethod
    def main_menu(cls) -> dict:
        """Main menu."""
        return cls.one_column(
            [
                'посмотреть актуальные поиски',
                'панель управления',
                'другие возможности',
            ],
            color='primary',
        )

    @classmethod
    def settings_menu(cls) -> dict:
        """Settings menu — now links to the web admin panel."""
        return cls.one_column(
            [
                'связать аккаунты бота и форума',
                'связать аккаунты бота и VKontakte',
                'в начало',
            ]
        )

    @classmethod
    def role_choice(cls) -> dict:
        """Role selection during onboarding."""
        return cls.one_column(
            [
                'я состою в ЛизаАлерт',
                'я хочу помогать ЛизаАлерт',
                'я ищу человека',
                'у меня другая задача',
                'не хочу говорить',
            ],
            color='primary',
        )

    @classmethod
    def yes_no(cls) -> dict:
        """Yes / No two-column layout."""
        return cls.two_columns(['да, это я', 'нет, это не я'], color='primary')

    @classmethod
    def back_to_start(cls) -> dict:
        """Single 'back to start' button."""
        return cls.one_column(['в начало'])

    @classmethod
    def other_menu(cls) -> dict:
        """Other options menu."""
        return cls.one_column(
            [
                'посмотреть последние поиски',
                'написать разработчику бота',
                'ознакомиться с информацией для новичка',
                'в начало',
            ]
        )

    @classmethod
    def confirm_delete(cls) -> dict:
        """Confirmation keyboard for destructive actions."""
        return cls.two_columns(['да, удалить', 'нет, оставить'], color='positive')

    @classmethod
    def forum_linking(cls) -> dict:
        """Forum linking menu."""
        return cls.one_column(
            [
                'ввести ник с форума',
                'в начало',
            ]
        )

    @classmethod
    def vk_linking(cls) -> dict:
        """VK linking menu (for Telegram users linking VK)."""
        return cls.one_column(
            [
                'связать аккаунты',
                'в начало',
            ]
        )

    @classmethod
    def onboarding_region_confirm(cls, region_name: str) -> dict:
        """Confirm region during onboarding."""
        return cls.two_columns(
            [
                f'да, {region_name}',
                'нет, выбрать другой',
            ],
            color='primary',
        )

    @classmethod
    def orders_done(cls) -> dict:
        """Orders status for relative role."""
        return cls.two_columns(
            [
                'уже заказал(а)',
                'закажу позже',
            ],
            color='primary',
        )

    @classmethod
    def search_view_menu(cls) -> dict:
        """Search view options menu."""
        return cls.one_column(
            [
                'активные поиски',
                'последние 20 поисков',
                'отслеживание поисков',
                'в начало',
            ]
        )

    @classmethod
    def search_follow_menu(cls) -> dict:
        """Search follow management menu."""
        return cls.one_column(
            [
                'включить режим отслеживания',
                'выключить режим отслеживания',
                'показать отслеживаемые поиски',
                'в начало',
            ]
        )

    @classmethod
    def search_actions(cls, topic_id: int) -> dict:
        """Actions for a specific search."""
        return cls.one_column(
            [
                f'+{topic_id} — следить',
                f'-{topic_id} — игнорировать',
                'еще поиски',
                'в начало',
            ]
        )

    @classmethod
    def search_navigation(cls) -> dict:
        """Navigation after viewing searches."""
        return cls.one_column(
            [
                'еще поиски',
                'управление отслеживанием',
                'в начало',
            ]
        )
