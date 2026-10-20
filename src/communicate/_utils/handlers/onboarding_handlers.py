from _dependencies.bot.users_management import save_onboarding_step

from ..buttons import (
    HelpNeeded,
    IsMoscow,
    OrdersState,
    RoleChoice,
    b_back_to_start,
    c_start,
    reply_markup_main,
)
from ..common import (
    create_one_column_reply_markup,
)
from ..decorators import tg_handle
from ..handler_context import TGHandlerContext


@tg_handle(text=b_back_to_start)
def handle_back_to_main_menu(ctx: TGHandlerContext) -> None:
    ctx.reply(text='возвращаемся в главное меню', reply_markup=reply_markup_main)


@tg_handle(text=c_start)
def handle_command_start(ctx: TGHandlerContext) -> None:
    if not ctx.extra_params.user_is_new:
        bot_message = 'Привет! Бот управляется кнопками, которые заменяют обычную клавиатуру.'
        ctx.reply(text=bot_message, reply_markup=reply_markup_main)
        return

    # FIXME – 02.12.2023 – hiding menu button for the newcomers
    #  (in the future it should be done in manage_user script)
    ctx.tg_api.set_my_commands(ctx.user_id, [], 'if user_is_new')
    # FIXME ^^^

    bot_message = (
        'Привет! Это Бот Поисковика ЛизаАлерт. Он помогает Поисковикам '
        'оперативно получать информацию о новых поисках или об изменениях '
        'в текущих поисках.'
        '\n\nБот управляется кнопками, которые заменяют обычную клавиатуру. '
        'Если кнопки не отображаются, справа от поля ввода сообщения '
        'есть специальный значок, чтобы отобразить кнопки управления ботом.'
        '\n\nДавайте настроим бот индивидуально под вас. Пожалуйста, '
        'укажите вашу роль сейчас?'
    )
    reply_markup = create_one_column_reply_markup(RoleChoice.list())
    ctx.reply(text=bot_message, reply_markup=reply_markup)


@tg_handle(text=HelpNeeded.list())
def handle_help_needed(ctx: TGHandlerContext) -> None:
    if ctx.update_params.got_message == HelpNeeded.b_help_no:
        bot_message = (
            'Спасибо, понятно. Мы записали. Тогда бот более не будет вас беспокоить, '
            'пока вы сами не напишите в бот.\n\n'
            'На прощание, бот хотел бы посоветовать следующие вещи, делающие мир лучше:\n\n'
            '1. Посмотреть <a href="https://t.me/+6LYNNEy8BeI1NGUy">позитивные фото '
            'с поисков ЛизаАлерт</a>.\n\n'
            '2. <a href="https://lizaalert.org/otryadnye-nuzhdy/">Помочь '
            'отряду ЛизаАлерт, пожертвовав оборудование для поисков людей</a>.\n\n'
            '3. Помочь создателям данного бота, присоединившись к группе разработчиков'
            'или оплатив облачную инфраструктуру для бесперебойной работы бота. Для этого'
            '<a href="https://t.me/MikeMikeT">просто напишите разработчику бота</a>.\n\n'
            'Бот еще раз хотел подчеркнуть, что как только вы напишите что-то в бот – он'
            'сразу же "забудет", что вы ранее просили вас не беспокоить:)\n\n'
            'Обнимаем:)'
        )
        keyboard = [b_back_to_start]
        ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard))
        return

    if ctx.update_params.got_message == HelpNeeded.b_help_yes:
        bot_message = (
            'Супер! Тогда давайте посмотрим, что у вас не настроено.\n\n'
            'У вас не настроен Регион поисков – без него Бот не может определить, '
            'какие поиски вас интересуют. Вы можете настроить регион двумя способами:\n'
            '1. Либо автоматически на основании ваших координат – нужно будет отправить '
            'вашу геолокацию (работает только с мобильных устройств),\n'
            '2. Либо выбрав регион вручную: для этого нужно сначала выбрать ФО = '
            'Федеральный Округ, где находится ваш регион, а потом кликнуть на сам регион. '
            '\n\n'
        )
        ctx.reply(text=bot_message, reply_markup=reply_markup_main)
        return

    ctx.reply(text='', reply_markup=reply_markup_main)


@tg_handle(text=[*RoleChoice.list(), OrdersState.b_orders_done, OrdersState.b_orders_tbd])
def handle_user_role(ctx: TGHandlerContext) -> None:
    got_message = ctx.update_params.got_message
    user_id = ctx.user_id

    if got_message in RoleChoice.list():
        ctx.db.save_user_pref_role(user_id, got_message)
        save_onboarding_step(user_id, 'role_set')

    if got_message == RoleChoice.b_role_looking_for_person:
        # get user role = relatives looking for a person
        bot_message = (
            'Тогда вам следует:\n\n'
            '1. Подайте заявку на поиск в ЛизаАлерт ОДНИМ ИЗ ДВУХ способов:\n'
            '  1.1. САМОЕ БЫСТРОЕ – звоните на 88007005452 (бесплатная горячая '
            'линия ЛизаАлерт). Вам зададут ряд вопросов, который максимально '
            'ускорит поиск, и посоветуют дальнейшие действия. \n'
            '  1.2. Заполните форму поиска https://lizaalert.org/zayavka-na-poisk/ \n'
            'После заполнения формы на сайте нужно ожидать звонка от ЛизаАлерт. На '
            'обработку может потребоваться более часа. Если нет возможности ждать, '
            'после заполнения заявки следует позвонить на горячую линию отряда '
            '88007005452, сообщив, что вы уже оформили заявку на сайте.\n\n'
            '2. Подать заявление в Полицию. Если иное не посоветовали на горячей линии,'
            'заявка в Полицию – поможет ускорить и упростить поиск. Самый быстрый '
            'способ – позвонить на 102.\n\n'
            '3. Отслеживайте ход поиска.\n'
            'Когда заявки в ЛизаАлерт и Полицию сделаны, отряд начнет первые '
            'мероприятия для поиска человека: уточнение деталей, прозвоны '
            'в госучреждения, формирование плана и команды поиска и т.п. Весь этот'
            'процесс вам не будет виден, но часто люди находятся именно на этой стадии'
            'поиска. Если первые меры не помогут и отряд примет решение проводить'
            'выезд "на место поиска" – тогда вы сможете отслеживать ход поиска '
            'через данный Бот, для этого продолжите настройку бота: вам нужно будет'
            'указать ваш регион и выбрать, какие уведомления от бота вы будете '
            'получать. '
            'Как альтернатива, вы можете зайти на форум https://lizaalert.org/forum/, '
            'и отслеживать статус поиска там.\n'
            'Отряд сделает всё возможное, чтобы найти вашего близкого как можно '
            'скорее.\n\n'
            'Сообщите, подали ли вы заявки в ЛизаАлерт и Полицию?'
        )

        keyboard_orders = [OrdersState.b_orders_done, OrdersState.b_orders_tbd]
        ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard_orders))
        return

    if got_message == RoleChoice.b_role_want_to_be_la:
        # get user role = potential LA volunteer
        bot_message = (
            'Супер! \n'
            'Знаете ли вы, как можно помогать ЛизаАлерт? Определились ли вы, как '
            'вы готовы помочь? Если еще нет – не беда – рекомендуем '
            'ознакомиться со статьёй: '
            'https://takiedela.ru/news/2019/05/25/instrukciya-liza-alert/\n\n'
            'Задачи, которые можно выполнять даже без специальной подготовки, '
            'выполняют Поисковики "на месте поиска". Этот Бот как раз старается '
            'помогать именно Поисковикам. '
            'Есть хороший сайт, рассказывающий, как начать участвовать в поиске: '
            'https://lizaalert.org/dvizhenie/novichkam/\n\n'
            'В случае любых вопросов – не стесняйтесь, обращайтесь на общий телефон, '
            '8 800 700-54-52, где вам помогут с любыми вопросами при вступлении в отряд.\n\n'
            'А если вы "из мира IT" и готовы помогать развитию этого Бота,'
            'пишите нам в специальный чат https://t.me/+2J-kV0GaCgwxY2Ni\n\n'
            'Надеемся, эта информацию оказалась полезной. '
            'Если вы готовы продолжить настройку Бота, уточните, пожалуйста: '
            'ваш основной регион – это Москва и Московская Область?'
        )
        keyboard_coordinates_admin = [IsMoscow.b_reg_moscow, IsMoscow.b_reg_not_moscow]
        ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard_coordinates_admin))
        return

    # all other cases
    bot_message = 'Спасибо. Теперь уточните, пожалуйста, ваш основной регион – это Москва и Московская Область?'
    keyboard_coordinates_admin = [IsMoscow.b_reg_moscow, IsMoscow.b_reg_not_moscow]
    ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard_coordinates_admin))
