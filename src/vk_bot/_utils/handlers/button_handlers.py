"""Main button/command handlers for the VK bot.

Each handler matches by vk_message.text content and handles a specific
button click or command. Returns VKHandlerResult if it handles the message,
or None to pass to the next handler in the chain.
"""

import logging
import time

from _dependencies.services.message_formatter import (
    community_intro,
    first_search_intro,
    forum_already_linked,
    forum_link_intro,
    onboarding_completed_message,
    other_menu_intro,
    role_other_ask_region,
    role_relative_instructions,
    role_volunteer_instructions,
    vk_already_linked,
    vk_link_instructions,
    vk_link_intro,
    welcome_back_user,
    welcome_new_user,
)
from _dependencies.services.state_machine import DialogState

from ..common import VKHandlerResult, VKMessage
from ..database import db
from ..keyboards import VKKeyboard

logger = logging.getLogger(__name__)


# ── Onboarding ─────────────────────────────────────────────────────


def handle_command_start(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle /start command — show welcome message and main menu."""
    if vk_message.text.strip() != '/start':
        return None

    is_new = db().settings.check_if_new_user(user_id)
    text = welcome_new_user() if is_new else welcome_back_user()
    return VKHandlerResult(
        text=text,
        keyboard=VKKeyboard.main_menu(),
        new_state=DialogState.not_defined,
    )


def handle_role_choice(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle role selection during onboarding.

    Matches button text from VKKeyboard.role_choice().
    """
    text = vk_message.text.strip().lower()

    role_map = {
        'я состою в лизаалерт': 'member',
        'я хочу помогать лизаалерт': 'volunteer',
        'я ищу человека': 'relative',
        'у меня другая задача': 'other',
        'не хочу говорить': 'other',
    }

    if text not in role_map:
        return None

    role_code = role_map[text]
    db().settings.save_user_role(user_id, role_code)
    db().settings.save_onboarding_step(user_id, 'role_set')

    instructions_map = {
        'member': role_volunteer_instructions(),
        'volunteer': role_volunteer_instructions(),
        'other': role_other_ask_region(),
    }
    instructions = instructions_map.get(role_code)

    if role_code == 'relative':
        return VKHandlerResult(
            text=role_relative_instructions(),
            keyboard=VKKeyboard.orders_done(),
        )

    if role_code == 'member':
        # Complete onboarding — region can be set in admin panel
        db().settings.save_onboarding_step(user_id, 'finished')
        return VKHandlerResult(
            text=onboarding_completed_message(),
            keyboard=VKKeyboard.main_menu(),
        )

    # volunteer or other → complete onboarding
    db().settings.save_onboarding_step(user_id, 'finished')
    return VKHandlerResult(
        text=onboarding_completed_message(),
        keyboard=VKKeyboard.main_menu(),
    )


def handle_orders_state(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle orders done/TBD for relative role."""
    text = vk_message.text.strip().lower()
    if text not in ('уже заказал(а)', 'закажу позже'):
        return None

    db().settings.save_onboarding_step(user_id, 'finished')
    return VKHandlerResult(
        text=onboarding_completed_message(),
        keyboard=VKKeyboard.main_menu(),
    )


# ── Main Menu ──────────────────────────────────────────────────────


def handle_main_menu(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle main menu navigation buttons."""
    text = vk_message.text.strip().lower()

    if text == 'другие возможности':
        return VKHandlerResult(
            text=other_menu_intro(),
            keyboard=VKKeyboard.other_menu(),
        )

    return None


def handle_back_to_start(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle 'в начало' button — return to main menu."""
    if vk_message.text.strip().lower() != 'в начало':
        return None

    return VKHandlerResult(
        text=welcome_back_user(),
        keyboard=VKKeyboard.main_menu(),
        new_state=DialogState.not_defined,
    )


# ── Settings (account linking only) ────────────────────────────────


def handle_forum_linking(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle forum linking — set state to input forum username."""
    text = vk_message.text.strip().lower()
    if text != 'ввести ник с форума':
        return None

    return VKHandlerResult(
        text='Введите ваш логин (ник) на форуме lizaalert.org:',
        keyboard=VKKeyboard.back_to_start(),
        new_state=DialogState.input_of_forum_username,
    )


def handle_vk_linking(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle VK linking button."""
    text = vk_message.text.strip().lower()
    if text != 'связать аккаунты':
        return None

    vk_id = db().settings.get_user_vk_id(user_id)
    if vk_id:
        return VKHandlerResult(
            text=vk_already_linked(),
            keyboard=VKKeyboard.settings_menu(),
        )

    invite_text = f'la_link_{user_id}_{int(time.time())}'
    return VKHandlerResult(
        text=vk_link_instructions(invite_text),
        keyboard=VKKeyboard.settings_menu(),
    )


def handle_settings_menu(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle settings menu button clicks (account linking only).

    Other settings (notifications, coordinates, radius, regions, etc.)
    are now managed via the web admin panel.
    """
    text = vk_message.text.strip().lower()

    if text == 'связать аккаунты бота и форума':
        forum_data = db().settings.get_forum_attributes(user_id)
        if forum_data:
            forum_username, forum_user_id = forum_data
            return VKHandlerResult(
                text=forum_already_linked(forum_username, int(forum_user_id)),
                keyboard=VKKeyboard.settings_menu(),
            )
        return VKHandlerResult(
            text=forum_link_intro(),
            keyboard=VKKeyboard.forum_linking(),
        )

    if text == 'связать аккаунты бота и vkontakte':
        vk_id = db().settings.get_user_vk_id(user_id)
        if vk_id:
            return VKHandlerResult(
                text=vk_already_linked(),
                keyboard=VKKeyboard.settings_menu(),
            )
        return VKHandlerResult(
            text=vk_link_intro(),
            keyboard=VKKeyboard.vk_linking(),
        )

    return None


# ── Other Menu ─────────────────────────────────────────────────────


def handle_other_menu(vk_message: VKMessage, state: DialogState | None, user_id: int) -> VKHandlerResult | None:
    """Handle other options menu buttons."""
    text = vk_message.text.strip().lower()

    if text == 'посмотреть последние поиски':
        # Delegate to the latest searches handler in view_searches_handlers
        # by returning None to let it pass through the handler chain
        return None

    if text == 'написать разработчику бота':
        return VKHandlerResult(
            text=community_intro(),
            keyboard=VKKeyboard.other_menu(),
        )

    if text == 'ознакомиться с информацией для новичка':
        return VKHandlerResult(
            text=first_search_intro(),
            keyboard=VKKeyboard.other_menu(),
        )

    return None
