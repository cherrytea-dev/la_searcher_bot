from datetime import date

from telegram import CallbackQuery, Chat, InlineKeyboardButton, InlineKeyboardMarkup, Message, User


def get_user() -> User:
    return User(id=1, first_name='test', is_bot=False)


def get_chat() -> Chat:
    return Chat(id=1, type='private')


def get_reply_markup() -> InlineKeyboardMarkup:
    inline_keyboard = [
        [
            InlineKeyboardButton(text='foo', callback_data="{'hash': 123}"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def get_user_message() -> Message:
    return Message(
        message_id=1,
        date=date.today(),
        chat=get_chat(),
        from_user=get_user(),
        text='foo',
        reply_markup=get_reply_markup(),
    )


def get_callback_query() -> CallbackQuery:
    return CallbackQuery(
        id=1,
        from_user=get_user(),
        message=get_user_message(),
        chat_instance='chat_id',
        data='data',
    )
