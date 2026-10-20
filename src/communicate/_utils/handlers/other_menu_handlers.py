from uuid import uuid4

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)

from _dependencies.common.commons import get_app_config

from ..buttons import (
    Commands,
    MainMenu,
    OtherOptionsMenu,
    b_back_to_start,
)
from ..common import (
    LA_BOT_CHAT_URL,
    create_one_column_reply_markup,
)
from ..decorators import tg_handle
from ..handler_context import TGHandlerContext


@tg_handle(text=[MainMenu.b_other, Commands.c_other])
def handle_command_other(ctx: TGHandlerContext) -> None:
    bot_message = (
        'Здесь можно посмотреть статистику по 20 последним поискам, перейти в '
        'канал Коммъюнити или Прочитать важную информацию для Новичка и посмотреть '
        'душевные фото с поисков'
    )
    keyboard_other = [
        OtherOptionsMenu.b_view_latest_searches,
        OtherOptionsMenu.b_goto_first_search,
        OtherOptionsMenu.b_goto_community,
        OtherOptionsMenu.b_goto_photos,
        b_back_to_start,
    ]
    ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard_other))


@tg_handle(text=[MainMenu.b_map, Commands.c_map])
def handle_show_map(ctx: TGHandlerContext) -> None:
    bot_message = (
        'В Боте Поисковика теперь можно посмотреть 🗺️Карту Поисков📍.\n\n'
        'На карте вы сможете увидеть все активные поиски, '
        'построить к каждому из них маршрут с учетом пробок, '
        'а также открыть этот маршрут в сервисах Яндекс.\n\n'
        'Карта работает в тестовом режиме.\n'
        'Если карта будет работать некорректно, или вы видите, как ее необходимо '
        'доработать – напишите в '
        f'<a href="{LA_BOT_CHAT_URL}">чат разработчиков</a>.'
        ''
    )

    map_button = InlineKeyboardButton(
        text='Открыть карту поисков',
        web_app=WebAppInfo(
            url=f'{get_app_config().web_app_url}?nocache={uuid4()}',
        ),
    )

    keyboard = [[map_button]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    ctx.reply(text=bot_message, reply_markup=reply_markup)


@tg_handle(text=OtherOptionsMenu.b_goto_photos)
def handle_goto_photos(ctx: TGHandlerContext) -> None:
    bot_message = (
        'Если вам хочется окунуться в атмосферу ПСР, приглашаем в замечательный '
        '<a href="https://t.me/+6LYNNEy8BeI1NGUy">телеграм-канал с красивыми фото с '
        'поисков</a>. Все фото – сделаны поисковиками во время настоящих ПСР.'
    )
    keyboard = [
        OtherOptionsMenu.b_view_latest_searches,
        OtherOptionsMenu.b_goto_community,
        OtherOptionsMenu.b_goto_first_search,
        b_back_to_start,
    ]
    ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard))


@tg_handle(text=OtherOptionsMenu.b_goto_first_search)
def handle_goto_first_search(ctx: TGHandlerContext) -> None:
    bot_message = (
        'Если вы хотите стать добровольцем ДПСО «ЛизаАлерт», пожалуйста, '
        '<a href="https://lizaalert.org/forum/viewtopic.php?t=56934">'
        'посетите страницу форума</a>, там можно ознакомиться с базовой информацией '
        'для новичков и задать свои вопросы.'
        'Если вы готовитесь к своему первому поиску – приглашаем '
        '<a href="https://lizaalert.org/dvizhenie/novichkam/">ознакомиться с основами '
        'работы ЛА</a>. Всю теорию работы ЛА необходимо получать от специально '
        'обученных волонтеров ЛА. Но если у вас еще не было возможности пройти '
        'официальное обучение, а вы уже готовы выехать на поиск – этот ресурс '
        'для вас.'
    )
    keyboard = [
        OtherOptionsMenu.b_view_latest_searches,
        OtherOptionsMenu.b_goto_community,
        OtherOptionsMenu.b_goto_photos,
        b_back_to_start,
    ]
    ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard))


@tg_handle(text=OtherOptionsMenu.b_goto_community)
def handle_goto_community(ctx: TGHandlerContext) -> None:
    bot_message = (
        'Бот можно обсудить с соотрядниками в '
        f'<a href="{LA_BOT_CHAT_URL}">Специальном Чате '
        'в телеграм</a>. Там можно предложить свои идеи, указать на проблемы '
        'и получить быструю обратную связь от разработчика.'
    )
    keyboard = [
        OtherOptionsMenu.b_view_latest_searches,
        OtherOptionsMenu.b_goto_first_search,
        OtherOptionsMenu.b_goto_photos,
        b_back_to_start,
    ]
    ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard))
