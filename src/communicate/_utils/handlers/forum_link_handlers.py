from ..buttons import (
    ItsMe,
    MainMenu,
    MainSettingsMenu,
    b_back_to_start,
)
from ..common import (
    UserInputState,
    create_one_column_reply_markup,
)
from ..decorators import tg_handle
from ..handler_context import TGHandlerContext


@tg_handle(text=ItsMe.b_yes_its_me)
def handle_linking_to_forum_its_me(ctx: TGHandlerContext) -> None:
    """Write "verified" for user"""

    ctx.db.write_user_forum_attributes_db(ctx.user_id)

    bot_message = (
        'Отлично, мы записали: теперь бот будет понимать, кто вы на форуме.\nЭто поможет '
        'вам более оперативно получать сообщения о поисках, по которым вы оставляли '
        'комментарии на форуме.'
    )
    keyboard = [MainMenu.b_settings, b_back_to_start]
    ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard))


@tg_handle(text=ItsMe.b_no_its_not_me)
def handle_linking_to_forum_not_me(ctx: TGHandlerContext) -> None:
    """suggest user to correct nicname"""
    bot_message = (
        'Пожалуйста, тщательно проверьте написание вашего ника на форуме '
        '(кириллица/латиница, без пробела в конце) и введите его заново'
    )
    keyboard = [MainSettingsMenu.b_set_forum_nick, b_back_to_start]
    ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard))
    ctx.set_state(UserInputState.input_of_forum_username)


@tg_handle(text=MainSettingsMenu.b_set_forum_nick)
def handle_linking_to_forum_show_menu(ctx: TGHandlerContext) -> None:
    """manage all interactions regarding connection of telegram and forum user accounts"""

    # TODO: if user_is linked to forum so
    saved_forum_user = ctx.db.get_user_forum_attributes_db(ctx.user_id)

    if not saved_forum_user:
        bot_message = (
            'Бот сможет быть еще полезнее, эффективнее и быстрее, если указать ваш аккаунт на форуме '
            'lizaalert.org\n\n'
            'Для этого просто введите ответным сообщением своё имя пользователя (логин).\n\n'
            'Если возникнут ошибки при распознавании – просто скопируйте имя с форума и '
            'отправьте боту ответным сообщением.'
        )
        keyboard = [b_back_to_start]
        reply_markup = create_one_column_reply_markup(keyboard)
        ctx.reply(text=bot_message, reply_markup=reply_markup)
        ctx.set_state(UserInputState.input_of_forum_username)
    else:
        saved_forum_username, saved_forum_user_id = list(saved_forum_user)

        bot_message = (
            f'Ваш телеграм уже привязан к аккаунту '
            f'<a href="https://lizaalert.org/forum/memberlist.php?mode=viewprofile&u='
            f'{saved_forum_user_id}">{saved_forum_username}</a> '
            f'на форуме ЛизаАлерт. Больше никаких действий касательно аккаунта на форуме не требуется:)'
        )
        keyboard = [MainMenu.b_settings, b_back_to_start]
        ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard))
