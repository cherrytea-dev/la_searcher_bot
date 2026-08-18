"""Button label constants shared by the VK and MAX bot keyboards.

Centralises the settings-menu button labels that are identical across
:mod:`src.vk_bot` and :mod:`src.max_bot` keyboards so the two bots stay
in sync. Messenger-specific labels remain in each bot's own
``MaxKeyboardButtons`` / ``VKKeyboardButtons`` class.
"""


class ButtonTexts:
    """Button label constants shared by the VK and MAX bots."""

    # Main menu
    BTN_DISABLE_NOTIFICATIONS: str = 'полностью отключить уведомления'
    BTN_ENABLE_NOTIFICATIONS: str = 'включить уведомления'
    BTN_SETTINGS_REGION: str = 'настроить регион поисков'
    BTN_SETTINGS_COORDS: str = 'настроить "домашние координаты"'
    BTN_SETTINGS_RADIUS: str = 'настроить максимальный радиус'

    # Coordinates sub-menu
    BTN_COORDS_ENTER: str = 'ввести "домашние координаты" вручную'
    BTN_COORDS_VIEW: str = 'посмотреть сохраненные координаты'
    BTN_COORDS_DELETE: str = 'удалить "домашние координаты"'

    # Reset settings
    BTN_RESET_SETTINGS: str = 'снести все настройки на дефолт'
    BTN_RESET_CONFIRM: str = 'да, снести настройки'
    BTN_RESET_KEEP: str = 'нет, оставить как есть'
