from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)

from _dependencies.common.commons import add_tel_link, get_app_config
from _dependencies.common.pubsub import notify_admin

from ..buttons import (
    b_admin_menu,
    b_back_to_start,
    b_test_menu,
    reply_markup_main,
)
from ..common import (
    LA_BOT_CHAT_URL,
    create_one_column_reply_markup,
)
from ..decorators import tg_handle
from ..handler_context import TGHandlerContext


@tg_handle(text='go')
def handle_test_admin_check(ctx: TGHandlerContext) -> None:
    # DEBUG: for debugging purposes only
    notify_admin('test_admin_check')
    ctx.reply(text='', reply_markup=reply_markup_main)


@tg_handle(
    text=[
        b_admin_menu,
        b_test_menu,
        'notest',
        'test msg 1',
        'test msg 2',
    ]
)
def handle_admin_experimental_settings(ctx: TGHandlerContext) -> None:
    # TODO split to separate handlers
    # FIXME - WIP
    got_message = ctx.update_params.got_message
    user_id = ctx.user_id

    # Admin mode
    if got_message.lower() == b_admin_menu:
        bot_message = 'Вы вошли в специальный тестовый админ-раздел'
        keyboard_coordinates_admin = [b_back_to_start, b_back_to_start]
        reply_markup = create_one_column_reply_markup(keyboard_coordinates_admin)
        ctx.reply(text=bot_message, reply_markup=reply_markup)
        return

    if got_message.lower() == b_test_menu:
        ctx.db.add_user_sys_role(user_id, 'tester')
        bot_message = (
            'Вы в секретном тестовом разделе, где всё может работать не так :) '
            'Если что – пишите, пожалуйста, в телеграм-чат '
            f'{LA_BOT_CHAT_URL}'
            '\n💡 А еще Вам добавлена роль tester - некоторые тестовые функции включены автоматически.'
            '\nДля отказа от роли tester нужно отправить команду notest'
        )

        map_button = InlineKeyboardButton(
            text='Открыть карту поисков', web_app=WebAppInfo(url=get_app_config().web_app_url_test)
        )

        keyboard = [[map_button]]
        ctx.reply(text=bot_message, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if got_message.lower() == 'notest':
        ctx.db.delete_user_sys_role(user_id, 'tester')
        ctx.db.delete_search_whiteness(user_id)
        ctx.db.delete_search_follow_mode(user_id)
        bot_message = 'Роль tester удалена. Приходите еще! :-) Возвращаемся в главное меню.'
        ctx.reply(text=bot_message, reply_markup=reply_markup_main)
        return

    if got_message == 'test msg 1':
        bot_message = """Ответственные:\n &#8226; Инфорг: Арина (Арина) 89001234567 \n\n"""
        bot_message = add_tel_link(bot_message)
        ctx.reply(text=bot_message, reply_markup=reply_markup_main)
        return

    if got_message == 'test msg 2':
        bot_message = """🔀Изменения в первом посте по <a href="https://lizaalert.org/forum/viewtopic.php?t=94862">Иванов 33 года</a> (Москва и МО – Активные поиски):

➖Удалено:
<s>Координатор-консультант: Маркиза
СНМ: Дуглас
Инфорг: Герда (Арина) 89001234567 Написать Герда (Арина) в Telegram
</s>
➕Добавлено:
С 7 мая 2025 года нет данных о его местонахождении.
рост 170 см,  худощавого телосложения, волосы седые, глаза карие.
Одежда: темно-синяя с лампасами на рукавах или темно-серая кофта, темно-синяя футболка, темно-синие брюки, темно-синие шлепанцы.
Внимание, выезд!
Штаб начинает работу 7 мая 2025 года в  23:00
Координаты штаба: <code>55.153047, 37.461095</code>
Адрес штаба: Московская обл, г Чехов, ул Московская, д 86
Форма одежды: город.
Маркиза
Дуглас
Герда (Арина) 89001234567 """
        bot_message = add_tel_link(bot_message)
        ctx.reply(text=bot_message, reply_markup=reply_markup_main)
        return

    ctx.reply(text='Неизвестная команда', reply_markup=reply_markup_main)
