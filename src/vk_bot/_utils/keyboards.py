import json

from _dependencies.common.geo import compact_region_name

from .common import ButtonColor

# VK API limits
_MAX_BUTTON_LABEL_LENGTH = 40
_MAX_KEYBOARD_ROWS = 10
_MAX_INLINE_ROWS = 6
# Inline keyboard: max 10 buttons total, grouped into max 6 rows, max 5 buttons per row.
_MAX_INLINE_BUTTONS = 10



class VKKeyboardButtons:
    """Mixin providing button label constants.

    These constants are the single source of truth for all button labels.
    Handler modules reference them (e.g., ``VKKeyboardButtons.BTN_SETTINGS_REGION``)
    instead of duplicating raw strings, ensuring keyboard and handler
    always stay in sync.
    """

    # Navigation
    BTN_BACK_TO_START: str = 'в начало'
    BTN_MORE_SEARCHES: str = 'еще поиски'
    BTN_FINISH: str = 'Завершить'
    BTN_BACK: str = '← назад'
    BTN_NEXT: str = 'ещё →'

    # Main menu
    BTN_SETTINGS_BOT: str = 'настроить бот'

    # Settings menu
    BTN_DISABLE_NOTIFICATIONS: str = 'полностью отключить уведомления'
    BTN_ENABLE_NOTIFICATIONS: str = 'включить уведомления'
    BTN_SETTINGS_REGION: str = 'настроить регион поисков'
    BTN_SETTINGS_COORDS: str = 'настроить "домашние координаты"'
    BTN_SETTINGS_RADIUS: str = 'настроить максимальный радиус'

    # Coordinates sub-menu
    BTN_COORDS_ENTER: str = 'ввести "домашние координаты" вручную'
    BTN_COORDS_VIEW: str = 'посмотреть сохраненные координаты'
    BTN_COORDS_DELETE: str = 'удалить "домашние координаты"'

    # Distance / radius settings
    BTN_RADIUS_ENABLE: str = 'включить ограничение по расстоянию'
    BTN_RADIUS_DISABLE: str = 'отключить ограничение по расстоянию'
    BTN_RADIUS_CHANGE: str = 'изменить ограничение по расстоянию'
    BTN_RADIUS_EDIT: str = 'изменить радиус'

    # Notification toggles
    BTN_NOTIF_ALL_ON: str = 'включить: все уведомления'
    BTN_NOTIF_NEW_ON: str = 'включить: о новых поисках'
    BTN_NOTIF_STATUS_ON: str = 'включить: об измен. статусов'
    BTN_NOTIF_COMMENTS_ON: str = 'включить: о всех новых комментариях'
    BTN_NOTIF_INFORG_ON: str = 'включить: о комм. Инфорга'
    BTN_NOTIF_FIRST_POST_ON: str = 'включить: об измен. в первом посте'
    BTN_NOTIF_FOLLOWED_ALL_ON: str = 'включить: в отслеж. поисках - все'
    BTN_NOTIF_ALL_OFF: str = 'отключить: все уведомления'
    BTN_NOTIF_NEW_OFF: str = 'отключить: о новых поисках'
    BTN_NOTIF_STATUS_OFF: str = 'отключить: об измен. статусов'
    BTN_NOTIF_COMMENTS_OFF: str = 'отключить: о всех новых комментариях'
    BTN_NOTIF_INFORG_OFF: str = 'отключить: о комм. инфорга'
    BTN_NOTIF_FIRST_POST_OFF: str = 'отключить: об измен. в первом посте'
    BTN_NOTIF_FOLLOWED_ALL_OFF: str = 'отключить: в отслеж. поисках - все'
    BTN_NOTIF_FLEXIBLE: str = 'настроить более гибко'

    # Other menu
    BTN_OTHER_LAST_SEARCHES: str = 'посмотреть последние поиски'
    BTN_OTHER_FEEDBACK: str = 'написать разработчику бота'
    BTN_OTHER_NEWBIE_INFO: str = 'ознакомиться с информацией для новичка'
    BTN_OTHER_PHOTOS: str = 'посмотреть красивые фото с поисков'

    # Search view menu
    BTN_SEARCH_ACTIVE: str = 'активные поиски'
    BTN_SEARCH_LAST_20: str = 'последние 20 поисков'
    BTN_SEARCH_FOLLOW_MGMT: str = 'отслеживание поисков'

    # Search follow menu
    BTN_FOLLOW_ENABLE: str = 'включить режим отслеживания'
    BTN_FOLLOW_DISABLE: str = 'выключить режим отслеживания'
    BTN_FOLLOW_SHOW: str = 'показать отслеживаемые поиски'
    BTN_FOLLOW_MANAGE: str = 'управление отслеживанием'

    # Region actions
    BTN_REGION_SUBSCRIBE: str = 'подписаться на регион'
    BTN_REGION_UNSUBSCRIBE: str = 'отписаться от региона'
    BTN_REGION_CHOOSE_OTHER: str = 'выбрать другой регион'

    # Age settings
    BTN_AGE_CHILDREN: str = 'дети (0-10 лет)'
    BTN_AGE_TEENS: str = 'подростки (11-17 лет)'
    BTN_AGE_ADULTS: str = 'взрослые (18-50 лет)'
    BTN_AGE_ELDERLY: str = 'пожилые (51+ лет)'

    # Topic type settings
    BTN_TYPE_SEARCH: str = 'поисковые работы'
    BTN_TYPE_INFO: str = 'информационный поиск'

    # Onboarding
    BTN_ONBOARD_YES: str = 'да, это я'
    BTN_ONBOARD_NO: str = 'нет, это не я'
    BTN_ONBOARD_MOSCOW_YES: str = 'да, Москва – мой регион'
    BTN_ONBOARD_MOSCOW_NO: str = 'нет, я из другого региона'
    BTN_ONBOARD_HELP_YES: str = 'да, помогите мне настроить бот'
    BTN_ONBOARD_HELP_NO: str = 'нет, помощь не требуется'
    BTN_ONBOARD_ROLE_LIZA_MEMBER: str = 'я состою в ЛизаАлерт'
    BTN_ONBOARD_ROLE_LIZA_HELPER: str = 'я хочу помогать ЛизаАлерт'
    BTN_ONBOARD_ROLE_SEEKER: str = 'я ищу человека'
    BTN_ONBOARD_ROLE_OTHER_TASK: str = 'у меня другая задача'
    BTN_ONBOARD_ROLE_DONT_SAY: str = 'не хочу говорить'

    # Confirm / delete
    BTN_CONFIRM_DELETE: str = 'да, удалить'
    BTN_CONFIRM_KEEP: str = 'нет, оставить'

    # Forum / VK linking
    BTN_FORUM_ENTER_NICK: str = 'ввести ник с форума'
    BTN_VK_LINK: str = 'связать аккаунты'

    # Orders (relative role)
    BTN_ORDERED: str = 'уже заказал(а)'
    BTN_ORDER_LATER: str = 'закажу позже'

    # Federal districts
    BTN_DISTRICT_CFO: str = 'Центральный ФО'
    BTN_DISTRICT_SZFO: str = 'Северо-Западный ФО'
    BTN_DISTRICT_YUFO: str = 'Южный ФО'
    BTN_DISTRICT_SKFO: str = 'Северо-Кавказский ФО'
    BTN_DISTRICT_PFO: str = 'Приволжский ФО'
    BTN_DISTRICT_UFO: str = 'Уральский ФО'
    BTN_DISTRICT_SFO: str = 'Сибирский ФО'
    BTN_DISTRICT_DFO: str = 'Дальневосточный ФО'
    BTN_DISTRICT_OTHER: str = 'Прочие поиски по РФ'


class VKKeyboardBase:
    """Low-level keyboard building blocks: validation and primitive button builders.

    VK keyboard format::

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

    VK API limits (validated at construction time):

    - Button labels: max 40 characters
    - Non-inline keyboards: max 40 buttons, max 10 rows, max 5 buttons per row
    - Inline keyboards: max 10 buttons, max 6 rows, max 5 buttons per row
    """

    @staticmethod
    def validate_label(label: str, max_len: int = _MAX_BUTTON_LABEL_LENGTH) -> str:
        """Validate a button label does not exceed VK API limits."""
        if len(label) > max_len:
            raise ValueError(f'VK button label exceeds {max_len} character limit ' f'({len(label)} chars): "{label}"')
        return label

    @staticmethod
    def validate_rows(buttons: list, inline: bool = False) -> None:
        """Validate keyboard dimensions do not exceed VK API limits.

        For inline keyboards, validates both row count (max 6) and
        total button count (max 10).

        Args:
            buttons: The list of button rows (each row is a list of button dicts).
            inline: Whether this is an inline keyboard (max 6 rows, 10 buttons
                    vs 10 rows for non-inline).

        Raises:
            ValueError: If the number of rows or total buttons exceeds VK API limits.
        """
        max_rows = _MAX_INLINE_ROWS if inline else _MAX_KEYBOARD_ROWS
        row_count = len(buttons)
        if row_count > max_rows:
            raise ValueError(
                f'VK keyboard exceeds {max_rows} row limit '
                f'({row_count} rows). '
                f'Use two_columns or paginate the content.'
            )
        if inline:
            total_buttons = sum(len(row) for row in buttons)
            if total_buttons > _MAX_INLINE_BUTTONS:
                raise ValueError(
                    f'VK inline keyboard exceeds {_MAX_INLINE_BUTTONS} button limit '
                    f'({total_buttons} buttons). '
                    f'Reduce page_size or use fewer rows.'
                )

    @staticmethod
    def text_button(label: str, color: ButtonColor = 'secondary', payload: str = '') -> dict:
        """Build a text action button dict."""
        VKKeyboardBase.validate_label(label)
        return {
            'action': {
                'type': 'text',
                'label': label,
                'payload': payload or json.dumps({'button': label}, ensure_ascii=False),
            },
            'color': color,
        }

    @staticmethod
    def url_button(label: str, url: str) -> dict:
        """Build an open-link action button dict."""
        VKKeyboardBase.validate_label(label)
        return {
            'action': {
                'type': 'open_link',
                'label': label,
                'link': url,
            },
        }

    @staticmethod
    def location_button() -> dict:
        """Build a location request button dict (VK API, but not supported in all clients)."""
        return {
            'action': {
                'type': 'location',
            },
        }

    @staticmethod
    def inline_callback_button(label: str, payload: dict, color: ButtonColor = 'secondary') -> dict:
        """Build an inline callback button with JSON payload.

        When clicked, VK sends a ``message_event`` with the payload data.
        The payload dict must be JSON-serializable and under 255 bytes.

        Args:
            label: Button label (validated against 40-char limit).
            payload: Dict to be JSON-encoded as the callback payload.
            color: Button color ('primary' for green/highlighted, 'secondary' for white/default).

        Returns:
            A button dict suitable for inline keyboards.
        """
        VKKeyboardBase.validate_label(label)
        return {
            'action': {
                'type': 'callback',
                'label': label,
                'payload': json.dumps(payload, ensure_ascii=False),
            },
            'color': color,
        }


class VKKeyboardLayouts(VKKeyboardBase):
    """Keyboard layout composition methods.

    Builds complete keyboard dicts from lists of button labels using
    various layout strategies (one column, two columns, one row, etc.).
    """

    @classmethod
    def one_column(cls, buttons: list[str], color: ButtonColor = 'secondary') -> dict:
        """Each button in its own row (vertical list)."""
        rows = [[cls.text_button(btn, color)] for btn in buttons]
        cls.validate_rows(rows, inline=False)
        return {
            'one_time': False,
            'inline': False,
            'buttons': rows,
        }

    @classmethod
    def two_columns(
        cls, buttons: list[str], color: ButtonColor = 'secondary', selected_regions: set[str] | None = None
    ) -> dict:
        """Buttons in pairs per row. If odd count, last one is alone.

        Args:
            buttons: List of button labels.
            color: Default button color.
            selected_regions: Set of region names to highlight with 'primary' color.

        Returns:
            A VK keyboard dict.
        """
        rows: list[list[dict]] = []
        if selected_regions is None:
            selected_regions = set()
        for i in range(0, len(buttons), 2):
            btn1_name = compact_region_name(buttons[i])
            btn1_color = 'primary' if buttons[i] in selected_regions else color
            row = [cls.text_button(btn1_name, btn1_color)]
            if i + 1 < len(buttons):
                btn2_name = compact_region_name(buttons[i + 1])
                btn2_color = 'primary' if buttons[i + 1] in selected_regions else color
                row.append(cls.text_button(btn2_name, btn2_color))
            rows.append(row)
        cls.validate_rows(rows, inline=False)
        return {'one_time': False, 'inline': False, 'buttons': rows}

    @classmethod
    def one_row(cls, buttons: list[str], color: ButtonColor = 'secondary') -> dict:
        """All buttons in a single row (max 4-5 buttons)."""
        rows = [[cls.text_button(btn, color) for btn in buttons]]
        cls.validate_rows(rows, inline=False)
        return {
            'one_time': False,
            'inline': False,
            'buttons': rows,
        }

    @classmethod
    def inline_url(cls, buttons: list[tuple[str, str]]) -> dict:
        """Inline keyboard with URL buttons. *buttons* = [(label, url), ...]"""
        rows = [[cls.url_button(label, url)] for label, url in buttons]
        cls.validate_rows(rows, inline=True)
        return {
            'inline': True,
            'buttons': rows,
        }

    @classmethod
    def empty(cls) -> dict:
        """Empty keyboard (removes current keyboard)."""
        return {'one_time': False, 'inline': False, 'buttons': []}


class VKKeyboardPresets(VKKeyboardLayouts, VKKeyboardButtons):
    """Preset keyboard menus for the VK bot.

    Combines button label constants, primitive builders, layout methods,
    and ready-to-use preset menus. This is the main class used by handlers.

    Usage::

        from .keyboards import VKKeyboardPresets

        keyboard = VKKeyboardPresets.main_menu()
        keyboard = VKKeyboardPresets.one_column([...])
    """

    @classmethod
    def main_menu(cls) -> dict:
        """Main menu — only settings button visible."""
        return cls.one_column(
            [
                cls.BTN_SETTINGS_BOT,
            ],
            color='primary',
        )

    @classmethod
    def settings_menu(cls, notifications_disabled: bool = False) -> dict:
        """Settings menu — simplified."""
        delivery_status_button = (
            cls.BTN_ENABLE_NOTIFICATIONS if notifications_disabled else cls.BTN_DISABLE_NOTIFICATIONS
        )
        return cls.one_column(
            [
                cls.BTN_SETTINGS_REGION,
                cls.BTN_SETTINGS_COORDS,
                cls.BTN_SETTINGS_RADIUS,
                delivery_status_button,
                cls.BTN_BACK_TO_START,
            ]
        )

    @classmethod
    def coords_menu(cls) -> dict:
        """Coordinate settings menu."""
        return cls.one_column(
            [
                cls.BTN_COORDS_ENTER,
                cls.BTN_COORDS_VIEW,
                cls.BTN_COORDS_DELETE,
                cls.BTN_BACK_TO_START,
            ]
        )

    @classmethod
    def role_choice(cls) -> dict:
        """Role selection during onboarding."""
        return cls.one_column(
            [
                cls.BTN_ONBOARD_ROLE_LIZA_MEMBER,
                cls.BTN_ONBOARD_ROLE_LIZA_HELPER,
                cls.BTN_ONBOARD_ROLE_SEEKER,
                cls.BTN_ONBOARD_ROLE_OTHER_TASK,
                cls.BTN_ONBOARD_ROLE_DONT_SAY,
            ],
            color='primary',
        )

    @classmethod
    def yes_no(cls) -> dict:
        """Yes / No two-column layout."""
        return cls.two_columns([cls.BTN_ONBOARD_YES, cls.BTN_ONBOARD_NO], color='primary')

    @classmethod
    def back_to_start(cls) -> dict:
        """Single 'back to start' button."""
        return cls.one_column([cls.BTN_BACK_TO_START])

    @classmethod
    def other_menu(cls) -> dict:
        """Other options menu."""
        return cls.one_column(
            [
                cls.BTN_OTHER_LAST_SEARCHES,
                cls.BTN_OTHER_FEEDBACK,
                cls.BTN_OTHER_NEWBIE_INFO,
                cls.BTN_OTHER_PHOTOS,
                cls.BTN_BACK_TO_START,
            ]
        )

    @classmethod
    def distance_settings(cls) -> dict:
        """Radius/distance settings menu."""
        return cls.one_column(
            [
                cls.BTN_RADIUS_ENABLE,
                cls.BTN_RADIUS_DISABLE,
                cls.BTN_RADIUS_CHANGE,
                cls.BTN_BACK_TO_START,
            ]
        )

    @classmethod
    def notification_settings(cls) -> dict:
        """Notification settings — enable/disable toggles.

        VK API limits:
        - Non-inline keyboards: 10 rows max
        - Button labels: 40 characters max
        """
        return {
            'one_time': False,
            'inline': False,
            'buttons': [
                [cls.text_button(cls.BTN_NOTIF_ALL_ON, 'positive')],
                [
                    cls.text_button(cls.BTN_NOTIF_NEW_ON),
                    cls.text_button(cls.BTN_NOTIF_STATUS_ON),
                ],
                [
                    cls.text_button(cls.BTN_NOTIF_COMMENTS_ON),
                    cls.text_button(cls.BTN_NOTIF_INFORG_ON),
                ],
                [
                    cls.text_button(cls.BTN_NOTIF_FIRST_POST_ON),
                    cls.text_button(cls.BTN_NOTIF_FOLLOWED_ALL_ON),
                ],
                [
                    cls.text_button(cls.BTN_NOTIF_FLEXIBLE),
                    cls.text_button(cls.BTN_NOTIF_ALL_OFF, 'negative'),
                ],
                [cls.text_button(cls.BTN_BACK_TO_START)],
            ],
        }

    @classmethod
    def fed_districts(cls) -> dict:
        """Federal districts selection (regular text buttons)."""
        return cls.one_column(
            [
                cls.BTN_DISTRICT_CFO,
                cls.BTN_DISTRICT_SZFO,
                cls.BTN_DISTRICT_YUFO,
                cls.BTN_DISTRICT_SKFO,
                cls.BTN_DISTRICT_PFO,
                cls.BTN_DISTRICT_UFO,
                cls.BTN_DISTRICT_SFO,
                cls.BTN_DISTRICT_DFO,
                cls.BTN_DISTRICT_OTHER,
                cls.BTN_BACK_TO_START,
            ]
        )

    @classmethod
    def fed_districts_inline(cls) -> dict:
        """Federal districts selection as inline callback buttons.

        Each button has a callback payload with ``cmd='district_select'`` and
        the normalized district name (e.g., 'Центральный'). When clicked,
        VK sends a ``message_event`` which is handled by ``handle_callback_event``
        in :mod:`dispatcher` — the message is edited in-place to show regions.

        Uses two_columns layout to fit 9 districts + 1 "Завершить" button
        within VK's 6-row inline keyboard limit (5 rows of 2 + 1 row for
        "Завершить" = 6 rows total).

        Returns:
            An inline VK keyboard dict with district callback buttons.
        """
        districts = [
            (cls.BTN_DISTRICT_CFO, 'Центральный'),
            (cls.BTN_DISTRICT_SZFO, 'Северо-Западный'),
            (cls.BTN_DISTRICT_YUFO, 'Южный'),
            (cls.BTN_DISTRICT_SKFO, 'Северо-Кавказский'),
            (cls.BTN_DISTRICT_PFO, 'Приволжский'),
            (cls.BTN_DISTRICT_UFO, 'Уральский'),
            (cls.BTN_DISTRICT_SFO, 'Сибирский'),
            (cls.BTN_DISTRICT_DFO, 'Дальневосточный'),
            (cls.BTN_DISTRICT_OTHER, 'Прочие поиски по РФ'),
        ]
        rows: list[list[dict]] = []
        for i in range(0, len(districts), 2):
            label_a, district_a = districts[i]
            row = [
                cls.inline_callback_button(
                    label_a,
                    {'cmd': 'district_select', 'district': district_a},
                )
            ]
            if i + 1 < len(districts):
                label_b, district_b = districts[i + 1]
                row.append(
                    cls.inline_callback_button(
                        label_b,
                        {'cmd': 'district_select', 'district': district_b},
                    )
                )
            rows.append(row)
        rows.append([cls.inline_callback_button(cls.BTN_FINISH, {'cmd': 'paginate_finish'})])
        cls.validate_rows(rows, inline=True)
        return {'inline': True, 'buttons': rows}

    @classmethod
    def is_moscow(cls) -> dict:
        """Moscow region confirmation."""
        return cls.two_columns(
            [cls.BTN_ONBOARD_MOSCOW_YES, cls.BTN_ONBOARD_MOSCOW_NO],
            color='primary',
        )

    @classmethod
    def help_needed(cls) -> dict:
        """Help needed confirmation."""
        return cls.two_columns(
            [cls.BTN_ONBOARD_HELP_YES, cls.BTN_ONBOARD_HELP_NO],
            color='primary',
        )

    @classmethod
    def age_settings(cls) -> dict:
        """Age group preferences."""
        return cls.one_column(
            [
                cls.BTN_AGE_CHILDREN,
                cls.BTN_AGE_TEENS,
                cls.BTN_AGE_ADULTS,
                cls.BTN_AGE_ELDERLY,
                cls.BTN_BACK_TO_START,
            ]
        )

    @classmethod
    def topic_type_settings(cls) -> dict:
        """Search type preferences (VK version - simplified, no inline toggles)."""
        return cls.one_column(
            [
                cls.BTN_TYPE_SEARCH,
                cls.BTN_TYPE_INFO,
                cls.BTN_BACK_TO_START,
            ]
        )

    @classmethod
    def region_actions(cls, region_name: str, is_subscribed: bool) -> dict:
        """Region actions: subscribe/unsubscribe and done."""
        action_btn = cls.BTN_REGION_UNSUBSCRIBE if is_subscribed else cls.BTN_REGION_SUBSCRIBE
        return cls.one_column(
            [
                action_btn,
                cls.BTN_REGION_CHOOSE_OTHER,
                cls.BTN_BACK_TO_START,
            ]
        )

    @classmethod
    def radius_settings(cls, has_radius: bool = False) -> dict:
        """Radius settings menu."""
        if has_radius:
            return cls.one_column(
                [
                    cls.BTN_RADIUS_EDIT,
                    cls.BTN_RADIUS_DISABLE,
                    cls.BTN_BACK_TO_START,
                ]
            )
        return cls.one_column(
            [
                cls.BTN_RADIUS_ENABLE,
                cls.BTN_BACK_TO_START,
            ]
        )

    @classmethod
    def confirm_delete(cls) -> dict:
        """Confirmation keyboard for destructive actions."""
        return cls.two_columns([cls.BTN_CONFIRM_DELETE, cls.BTN_CONFIRM_KEEP], color='positive')

    @classmethod
    def forum_linking(cls) -> dict:
        """Forum linking menu."""
        return cls.one_column(
            [
                cls.BTN_FORUM_ENTER_NICK,
                cls.BTN_BACK_TO_START,
            ]
        )

    @classmethod
    def vk_linking(cls) -> dict:
        """VK linking menu (for Telegram users linking VK)."""
        return cls.one_column(
            [
                cls.BTN_VK_LINK,
                cls.BTN_BACK_TO_START,
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
                cls.BTN_ORDERED,
                cls.BTN_ORDER_LATER,
            ],
            color='primary',
        )

    @classmethod
    def search_view_menu(cls) -> dict:
        """Search view options menu."""
        return cls.one_column(
            [
                cls.BTN_SEARCH_ACTIVE,
                cls.BTN_SEARCH_LAST_20,
                cls.BTN_SEARCH_FOLLOW_MGMT,
                cls.BTN_BACK_TO_START,
            ]
        )

    @classmethod
    def search_follow_menu(cls) -> dict:
        """Search follow management menu."""
        return cls.one_column(
            [
                cls.BTN_FOLLOW_ENABLE,
                cls.BTN_FOLLOW_DISABLE,
                cls.BTN_FOLLOW_SHOW,
                cls.BTN_BACK_TO_START,
            ]
        )

    @classmethod
    def search_actions(cls, topic_id: int) -> dict:
        """Actions for a specific search."""
        return cls.one_column(
            [
                f'+{topic_id} — следить',
                f'-{topic_id} — игнорировать',
                cls.BTN_MORE_SEARCHES,
                cls.BTN_BACK_TO_START,
            ]
        )

    @classmethod
    def search_navigation(cls) -> dict:
        """Navigation after viewing searches."""
        return cls.one_column(
            [
                cls.BTN_MORE_SEARCHES,
                cls.BTN_FOLLOW_MANAGE,
                cls.BTN_BACK_TO_START,
            ]
        )

    @classmethod
    def paginated_regions_inline(
        cls,
        region_buttons: list[str],
        page: int,
        district: str,
        page_size: int = 6,
        selected_regions: set[str] | None = None,
    ) -> dict:
        """Inline keyboard with paginated region selection callback buttons.

        Each region button has a callback payload with ``cmd='paginate_toggle'``.
        Navigation buttons have ``cmd='paginate_nav'`` with district and page.
        'Завершить' button has ``cmd='paginate_finish'``.

        Already-selected regions are highlighted with 'primary' (green) color.

        Region names are compacted via ``compact_region_name()`` — verbose
        subtype suffixes (e.g., " – Активные поиски") are replaced with short
        emoji markers (e.g., "🔍") to fit within VK's 40-character button limit.

        Uses two-column layout with *page_size*=6 (3 rows of 2 + 1 nav row = max 9 buttons),
        fitting within VK's inline keyboard limits: max 10 buttons, max 6 rows.

        Args:
            region_buttons: Full list of region button labels.
            page: Zero-based page index.
            district: Normalized district name (e.g., 'Центральный').
            page_size: Number of items per page (default: 6 = 3 rows of 2 + 1 nav row).
            selected_regions: Set of region names that are already subscribed (highlighted green).

        Returns:
            An inline VK keyboard dict with region + navigation buttons.
        """
        total_pages = (len(region_buttons) + page_size - 1) // page_size
        start = page * page_size
        end = start + page_size
        page_items = region_buttons[start:end]

        if selected_regions is None:
            selected_regions = set()

        compacted = [(compact_region_name(name), name) for name in page_items]

        rows: list[list[dict]] = []
        for i in range(0, len(compacted), 2):
            row: list[dict] = []
            for compact_name, original_name in compacted[i : i + 2]:
                btn_color: ButtonColor = 'primary' if original_name in selected_regions else 'secondary'
                row.append(
                    cls.inline_callback_button(
                        compact_name,
                        {
                            'cmd': 'paginate_toggle',
                            'region': original_name,
                            'district': district,
                            'page': page,
                        },
                        color=btn_color,
                    )
                )
            rows.append(row)

        bottom_row: list[dict] = []
        if page > 0:
            bottom_row.append(
                cls.inline_callback_button(
                    cls.BTN_BACK,
                    {
                        'cmd': 'paginate_nav',
                        'district': district,
                        'page': page - 1,
                    },
                )
            )
        if page < total_pages - 1:
            bottom_row.append(
                cls.inline_callback_button(
                    cls.BTN_NEXT,
                    {
                        'cmd': 'paginate_nav',
                        'district': district,
                        'page': page + 1,
                    },
                )
            )
        bottom_row.append(cls.inline_callback_button(cls.BTN_FINISH, {'cmd': 'paginate_finish'}))
        rows.append(bottom_row)

        cls.validate_rows(rows, inline=True)
        return {'inline': True, 'buttons': rows}
