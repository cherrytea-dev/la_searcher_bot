"""Onboarding and navigation handlers for the VK bot.

Contains the `router` list with handlers for:
- /start command
- Role selection during onboarding
- Moscow region confirmation
- Help needed question
- Main menu navigation
- Back to start button

Each handler matches by vk_message.text content and handles a specific
button click or command. Returns VKHandlerResult if it handles the message,
or None to pass to the next handler in the chain.
"""

from _dependencies.models import DialogState

from ..common import VKHandlerResult, VKMessage
from ..database import db
from ..keyboards import VKKeyboardButtons, VKKeyboardPresets
from ..services.message_formatter import (
    onboarding_completed_message,
    region_selection_intro,
    role_other_ask_region,
    role_relative_instructions,
    role_volunteer_instructions,
    settings_menu_intro,
    welcome_back_user,
    welcome_new_user,
)


def handle_command_start(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle /start command — show welcome message and main menu."""
    if vk_message.text.strip() != '/start':
        return None

    is_new = db().check_if_new_user(user_id)
    text = welcome_new_user() if is_new else welcome_back_user()
    return VKHandlerResult(
        text=text,
        keyboard=VKKeyboardPresets.main_menu(),
        new_state=DialogState.not_defined,
    )


def handle_role_choice(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle role selection during onboarding.

    Matches button text from VKKeyboardPresets.role_choice().
    """
    text = vk_message.text.strip().lower()

    role_map = {
        VKKeyboardButtons.BTN_ONBOARD_LIZA_MEMBER.lower(): 'member',
        VKKeyboardButtons.BTN_ONBOARD_LIZA_HELPER.lower(): 'volunteer',
        VKKeyboardButtons.BTN_ONBOARD_SEEKER.lower(): 'relative',
        VKKeyboardButtons.BTN_ONBOARD_OTHER_TASK.lower(): 'other',
        VKKeyboardButtons.BTN_ONBOARD_DONT_SAY.lower(): 'other',
    }

    if text not in role_map:
        return None

    role_code = role_map[text]
    db().save_user_role(user_id, role_code)
    db().save_onboarding_step(user_id, 'role_set')

    instructions_map = {
        'member': role_volunteer_instructions(),
        'volunteer': role_volunteer_instructions(),
        'other': role_other_ask_region(),
    }
    instructions = instructions_map.get(role_code)

    if role_code == 'relative':
        return VKHandlerResult(
            text=role_relative_instructions(),
            keyboard=VKKeyboardPresets.orders_done(),
        )

    if role_code == 'member':
        return VKHandlerResult(
            text=instructions or 'Нужна ли вам помощь?',
            keyboard=VKKeyboardPresets.help_needed(),
        )

    # volunteer or other → ask Moscow
    return VKHandlerResult(
        text=instructions or region_selection_intro(),
        keyboard=VKKeyboardPresets.is_moscow(),
    )


def handle_orders_state(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle orders done/TBD for relative role."""
    text = vk_message.text.strip().lower()
    if text not in (VKKeyboardButtons.BTN_ORDERED.lower(), VKKeyboardButtons.BTN_ORDER_LATER.lower()):
        return None

    db().save_onboarding_step(user_id, 'region_set')
    return VKHandlerResult(
        text='Спасибо! Давайте настроим регион для поисков.',
        keyboard=VKKeyboardPresets.is_moscow(),
    )


def _subscribe_moscow_regions(user_id: int) -> None:
    """Subscribe user to Moscow and Moscow Oblast regions."""
    folders = db().get_geo_folders()
    for fid, name in folders:
        if 'москв' in name.lower() or 'мо:' in name.lower():
            db().add_region(user_id, fid)


def handle_is_moscow(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle Moscow region confirmation during onboarding."""
    text = vk_message.text.strip().lower()

    if text == VKKeyboardButtons.BTN_ONBOARD_MOSCOW_YES.lower():
        _subscribe_moscow_regions(user_id)
        db().save_onboarding_step(user_id, 'finished')
        return VKHandlerResult(
            text=onboarding_completed_message(),
            keyboard=VKKeyboardPresets.main_menu(),
        )

    if text == VKKeyboardButtons.BTN_ONBOARD_MOSCOW_NO.lower():
        return VKHandlerResult(
            text=region_selection_intro(),
            keyboard=VKKeyboardPresets.fed_districts(),
        )

    return None


def handle_help_needed(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle help needed question for member role."""
    text = vk_message.text.strip().lower()
    if text not in (VKKeyboardButtons.BTN_ONBOARD_HELP_YES.lower(), VKKeyboardButtons.BTN_ONBOARD_HELP_NO.lower()):
        return None

    db().save_onboarding_step(user_id, 'region_set')
    return VKHandlerResult(
        text=region_selection_intro(),
        keyboard=VKKeyboardPresets.fed_districts(),
    )


def handle_main_menu(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle main menu navigation buttons."""
    text = vk_message.text.strip().lower()

    if text == VKKeyboardButtons.BTN_SETTINGS_BOT.lower():
        settings_text = settings_menu_intro()

        return VKHandlerResult(
            text=settings_text,
            keyboard=VKKeyboardPresets.settings_menu(),
        )

    # 'посмотреть актуальные поиски' and 'другие возможности' are hidden from
    # the main menu keyboard — handled by view_searches_handlers.py if needed
    return None


def handle_back_to_start(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle 'в начало' button — return to main menu."""
    if vk_message.text.strip().lower() != VKKeyboardButtons.BTN_BACK_TO_START.lower():
        return None

    return VKHandlerResult(
        text=welcome_back_user(),
        keyboard=VKKeyboardPresets.main_menu(),
        new_state=DialogState.not_defined,
    )


router: list = [
    handle_command_start,
    handle_role_choice,
    handle_orders_state,
    handle_is_moscow,
    handle_help_needed,
    handle_back_to_start,
    handle_main_menu,
]
