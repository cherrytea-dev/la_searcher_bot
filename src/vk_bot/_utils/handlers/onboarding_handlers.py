"""Onboarding and navigation handlers for the VK bot.

Each handler is registered via @vk_handle decorator with conditions
matching button text or command patterns.
"""

from _dependencies.common.geo import NavButton

from ..common import VKHandlerContext
from ..decorators import vk_handle
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


@vk_handle(text='/start')
def handle_command_start(ctx: VKHandlerContext) -> None:
    """Handle /start command — show welcome message and main menu.

    Uses ``ctx.is_new_user`` (set by ``handle_new_message`` when the user
    was just registered) instead of ``ctx.db.check_if_new_user()`` because
    the user is already registered by the time the handler chain runs.
    """
    text = welcome_new_user() if ctx.is_new_user else welcome_back_user()
    ctx.reply(text=text, keyboard=VKKeyboardPresets.main_menu())


@vk_handle(
    text=[
        VKKeyboardButtons.BTN_ONBOARD_ROLE_LIZA_MEMBER,
        VKKeyboardButtons.BTN_ONBOARD_ROLE_LIZA_HELPER,
        VKKeyboardButtons.BTN_ONBOARD_ROLE_SEEKER,
        VKKeyboardButtons.BTN_ONBOARD_ROLE_OTHER_TASK,
        VKKeyboardButtons.BTN_ONBOARD_ROLE_DONT_SAY,
    ]
)
def handle_role_choice(ctx: VKHandlerContext) -> None:
    """Handle role selection during onboarding.

    Matches button text from VKKeyboardPresets.role_choice().
    """
    text = ctx.message.text.strip().lower()

    role_map = {
        VKKeyboardButtons.BTN_ONBOARD_ROLE_LIZA_MEMBER.lower(): 'member',
        VKKeyboardButtons.BTN_ONBOARD_ROLE_LIZA_HELPER.lower(): 'volunteer',
        VKKeyboardButtons.BTN_ONBOARD_ROLE_SEEKER.lower(): 'relative',
        VKKeyboardButtons.BTN_ONBOARD_ROLE_OTHER_TASK.lower(): 'other',
        VKKeyboardButtons.BTN_ONBOARD_ROLE_DONT_SAY.lower(): 'other',
    }

    role_code = role_map[text]
    ctx.db.save_user_role(ctx.user_id, role_code)
    ctx.db.save_onboarding_step(ctx.user_id, 'role_set')

    instructions_map = {
        'member': role_volunteer_instructions(),
        'volunteer': role_volunteer_instructions(),
        'other': role_other_ask_region(),
    }
    instructions = instructions_map.get(role_code)

    if role_code == 'relative':
        ctx.reply(
            text=role_relative_instructions(),
            keyboard=VKKeyboardPresets.orders_done(),
        )
        return

    if role_code == 'member':
        ctx.reply(
            text=instructions or 'Нужна ли вам помощь?',
            keyboard=VKKeyboardPresets.help_needed(),
        )
        return

    # volunteer or other → ask Moscow
    ctx.reply(
        text=instructions or region_selection_intro(),
        keyboard=VKKeyboardPresets.is_moscow(),
    )


@vk_handle(text=[VKKeyboardButtons.BTN_ORDERED, VKKeyboardButtons.BTN_ORDER_LATER])
def handle_orders_state(ctx: VKHandlerContext) -> None:
    """Handle orders done/TBD for relative role."""
    ctx.db.save_onboarding_step(ctx.user_id, 'region_set')
    ctx.reply(
        text='Спасибо! Давайте настроим регион для поисков.',
        keyboard=VKKeyboardPresets.is_moscow(),
    )


def _subscribe_moscow_regions(user_id: int, ctx: VKHandlerContext) -> None:
    """Subscribe user to Moscow and Moscow Oblast regions."""
    folders = ctx.db.get_geo_folders()
    for fid, name in folders:
        if 'москв' in name.lower() or 'мо:' in name.lower():
            ctx.db.add_region(user_id, fid)


@vk_handle(text=[VKKeyboardButtons.BTN_ONBOARD_MOSCOW_YES, VKKeyboardButtons.BTN_ONBOARD_MOSCOW_NO])
def handle_is_moscow(ctx: VKHandlerContext) -> None:
    """Handle Moscow region confirmation during onboarding."""
    text = ctx.message.text.strip().lower()

    if text == VKKeyboardButtons.BTN_ONBOARD_MOSCOW_YES.lower():
        _subscribe_moscow_regions(ctx.user_id, ctx)
        ctx.db.save_onboarding_step(ctx.user_id, 'finished')
        ctx.reply(
            text=onboarding_completed_message(),
            keyboard=VKKeyboardPresets.main_menu(),
        )
        return

    if text == VKKeyboardButtons.BTN_ONBOARD_MOSCOW_NO.lower():
        ctx.reply(
            text=region_selection_intro(),
            keyboard=VKKeyboardPresets.fed_districts(),
        )


@vk_handle(text=[VKKeyboardButtons.BTN_ONBOARD_HELP_YES, VKKeyboardButtons.BTN_ONBOARD_HELP_NO])
def handle_help_needed(ctx: VKHandlerContext) -> None:
    """Handle help needed question for member role."""
    ctx.db.save_onboarding_step(ctx.user_id, 'region_set')
    ctx.reply(
        text=region_selection_intro(),
        keyboard=VKKeyboardPresets.fed_districts(),
    )


@vk_handle(text=VKKeyboardButtons.BTN_SETTINGS_BOT)
def handle_main_menu(ctx: VKHandlerContext) -> None:
    """Handle main menu navigation buttons."""
    settings_text = settings_menu_intro()
    notifications_disabled = ctx.db.get_user_status(ctx.user_id) == 'unsubscribed'
    ctx.reply(
        text=settings_text,
        keyboard=VKKeyboardPresets.settings_menu(notifications_disabled=notifications_disabled),
    )


@vk_handle(text=NavButton.BACK_TO_START)
def handle_back_to_start(ctx: VKHandlerContext) -> None:
    """Handle 'в начало' button — return to main menu."""
    ctx.reply(
        text=welcome_back_user(),
        keyboard=VKKeyboardPresets.main_menu(),
    )
