import json

import pytest

pytest.importorskip('maxapi')

from max_bot._utils.keyboards import MaxKeyboardButtons, MaxKeyboardPresets


def test_main_menu_has_notification_delivery_actions():
    keyboard = MaxKeyboardPresets.main_menu()
    buttons = [row[0] for row in keyboard.payload.buttons]
    payload_by_text = {button.text: json.loads(button.payload) for button in buttons}

    assert payload_by_text[MaxKeyboardButtons.BTN_DISABLE_NOTIFICATIONS] == {'cmd': 'disable_notifications'}


def test_main_menu_for_unsubscribed_user_has_enable_action():
    keyboard = MaxKeyboardPresets.main_menu(notifications_disabled=True)
    buttons = [row[0] for row in keyboard.payload.buttons]
    payload_by_text = {button.text: json.loads(button.payload) for button in buttons}

    assert payload_by_text[MaxKeyboardButtons.BTN_ENABLE_NOTIFICATIONS] == {'cmd': 'enable_notifications'}
    assert MaxKeyboardButtons.BTN_DISABLE_NOTIFICATIONS not in payload_by_text
