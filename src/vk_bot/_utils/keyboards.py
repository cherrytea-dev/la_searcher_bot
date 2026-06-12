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
                '🔥Карта Поисков 🔥',
                'посмотреть актуальные поиски',
                'настроить бот',
                'другие возможности',
            ],
            color='primary',
        )

    @classmethod
    def settings_menu(cls) -> dict:
        """Settings menu."""
        return cls.one_column(
            [
                'настроить виды уведомлений',
                'настроить "домашние координаты"',
                'настроить максимальный радиус',
                'настроить возрастные группы БВП',
                'настроить вид поисков',
                'связать аккаунты бота и форума',
                'связать аккаунты бота и VKontakte',
                'в начало',
            ]
        )

    @classmethod
    def coords_menu(cls) -> dict:
        """Coordinate settings menu."""
        return cls.one_column(
            [
                'ввести "домашние координаты" вручную',
                'посмотреть сохраненные "домашние координаты"',
                'удалить "домашние координаты"',
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
                'посмотреть красивые фото с поисков',
                'в начало',
            ]
        )

    @classmethod
    def distance_settings(cls) -> dict:
        """Radius/distance settings menu."""
        return cls.one_column(
            [
                'включить ограничение по расстоянию',
                'отключить ограничение по расстоянию',
                'изменить ограничение по расстоянию',
                'в начало',
            ]
        )

    @classmethod
    def notification_settings(cls) -> dict:
        """Notification settings — enable/disable toggles."""
        return cls.one_column(
            [
                'включить: все уведомления',
                'включить: о новых поисках',
                'включить: об изменениях статусов',
                'включить: о всех новых комментариях',
                'включить: о комментариях Инфорга',
                'включить: об изменениях в первом посте',
                'включить: в отслеживаемых поисках - все уведомления',
                '---',
                'настроить более гибко',
                'отключить: о новых поисках',
                'отключить: об изменениях статусов',
                'отключить: о всех новых комментариях',
                'отключить: о комментариях Инфорга',
                'отключить: об изменениях в первом посте',
                'отключить: в отслеживаемых поисках - все уведомления',
                'в начало',
            ]
        )

    @classmethod
    def fed_districts(cls) -> dict:
        """Federal districts selection."""
        return cls.one_column(
            [
                'Центральный ФО',
                'Северо-Западный ФО',
                'Южный ФО',
                'Северо-Кавказский ФО',
                'Приволжский ФО',
                'Уральский ФО',
                'Сибирский ФО',
                'Дальневосточный ФО',
                'Прочие поиски по РФ',
                'в начало',
            ]
        )

    @classmethod
    def is_moscow(cls) -> dict:
        """Moscow region confirmation."""
        return cls.two_columns(
            ['да, Москва – мой регион', 'нет, я из другого региона'],
            color='primary',
        )

    @classmethod
    def help_needed(cls) -> dict:
        """Help needed confirmation."""
        return cls.two_columns(
            ['да, помогите мне настроить бот', 'нет, помощь не требуется'],
            color='primary',
        )

    @classmethod
    def age_settings(cls) -> dict:
        """Age group preferences."""
        return cls.one_column(
            [
                'дети (0-10 лет)',
                'подростки (11-17 лет)',
                'взрослые (18-50 лет)',
                'пожилые (51+ лет)',
                'в начало',
            ]
        )

    @classmethod
    def topic_type_settings(cls) -> dict:
        """Search type preferences (VK version - simplified, no inline toggles)."""
        return cls.one_column(
            [
                'поисковые работы',
                'информационный поиск',
                'в начало',
            ]
        )

    @classmethod
    def region_actions(cls, region_name: str, is_subscribed: bool) -> dict:
        """Region actions: subscribe/unsubscribe and done."""
        action_btn = 'отписаться от региона' if is_subscribed else 'подписаться на регион'
        return cls.one_column(
            [
                action_btn,
                'выбрать другой регион',
                'в начало',
            ]
        )

    @classmethod
    def radius_settings(cls, has_radius: bool = False) -> dict:
        """Radius settings menu."""
        if has_radius:
            return cls.one_column(
                [
                    'изменить радиус',
                    'отключить ограничение по расстоянию',
                    'в начало',
                ]
            )
        return cls.one_column(
            [
                'включить ограничение по расстоянию',
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
