from telegram import (
    KeyboardButton,
    ReplyKeyboardRemove,
)

from ..buttons import (
    CoordinateSettingsMenu,
    DistanceSettings,
    MainSettingsMenu,
    b_back_to_start,
    b_coords_auto_def,
)
from ..common import (
    UserInputState,
    create_one_column_reply_markup,
    generate_yandex_maps_place_link,
)
from ..decorators import tg_handle
from ..handler_context import TGHandlerContext


@tg_handle(text=MainSettingsMenu.b_set_pref_radius)
def handle_radius_menu_show(ctx: TGHandlerContext) -> None:
    """Show menu for radius setting"""

    saved_radius = ctx.db.check_saved_radius(ctx.user_id)
    if saved_radius:
        list_of_buttons = [
            DistanceSettings.b_pref_radius_change,
            DistanceSettings.b_pref_radius_deact,
            MainSettingsMenu.b_set_pref_coords,
            b_back_to_start,
        ]
        bot_message = (
            f'Сейчас вами установлено ограничение радиуса {saved_radius} км. '
            f'Вы в любой момент можете изменить или снять это ограничение.\n\n'
            'ВАЖНО! Вы всё равно будете проинформированы по всем поискам, по которым '
            'Бот не смог распознать никакие координаты.\n\n'
            'Также, бот в первую очередь '
            'проверяет расстояние от штаба, а если он не указан, то до ближайшего '
            'населенного пункта (или топонима), указанного в теме поиска. '
            'Расстояние считается по прямой.'
        )
    else:
        list_of_buttons = [
            DistanceSettings.b_pref_radius_act,
            MainSettingsMenu.b_set_pref_coords,
            b_back_to_start,
        ]
        bot_message = (
            'Данная настройка позволяет вам ограничить уведомления от бота только теми поисками, '
            'для которых расстояние от ваших "домашних координат" до штаба/города '
            'не превышает указанного вами Радиуса.\n\n'
            'ВАЖНО! Вы всё равно будете проинформированы по всем поискам, по которым '
            'Бот не смог распознать никакие координаты.\n\n'
            'Также, Бот в первую очередь '
            'проверяет расстояние от штаба, а если он не указан, то до ближайшего '
            'населенного пункта (или топонима), указанного в теме поиска. '
            'Расстояние считается по прямой.'
        )
    ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(list_of_buttons))


@tg_handle(text=[*DistanceSettings.list()])
def handle_radius_menu(ctx: TGHandlerContext) -> None:
    """Save user Radius preference and generate the actual radius preference"""

    if ctx.update_params.got_message in {DistanceSettings.b_pref_radius_act, DistanceSettings.b_pref_radius_change}:
        saved_radius = ctx.db.check_saved_radius(ctx.user_id)
        if saved_radius:
            bot_message = (
                f'У вас установлено максимальное расстояние до поиска {saved_radius}.'
                f'\n\nВведите обновлённое расстояние в километрах по прямой в формате простого '
                f'числа (например: 150) и нажмите обычную кнопку отправки сообщения'
            )
        else:
            bot_message = (
                'Введите расстояние в километрах по прямой в формате простого числа '
                '(например: 150) и нажмите обычную кнопку отправки сообщения'
            )
        ctx.reply(text=bot_message, reply_markup=ReplyKeyboardRemove())
        ctx.set_state(UserInputState.radius_input)
    else:
        list_of_buttons = [
            DistanceSettings.b_pref_radius_act,
            MainSettingsMenu.b_set_pref_radius,
            b_back_to_start,
        ]
        ctx.db.delete_user_saved_radius(ctx.user_id)
        bot_message = 'Ограничение на расстояние по поискам снято!'
        ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(list_of_buttons))


@tg_handle(text=MainSettingsMenu.b_set_pref_coords)
def handle_coordinates_show_menu(ctx: TGHandlerContext) -> None:
    bot_message = (
        'АВТОМАТИЧЕСКОЕ ОПРЕДЕЛЕНИЕ координат работает только для носимых устройств'
        ' (для настольных компьютеров – НЕ работает: используйте, пожалуйста, '
        'кнопку ручного ввода координат). '
        'При автоматическом определении координат – нажмите на кнопку и '
        'разрешите определить вашу текущую геопозицию. '
        'Координаты, загруженные вручную или автоматически, будут считаться '
        'вашим "домом", откуда будут рассчитаны расстояние и '
        'направление до поисков.'
    )
    keyboard: list[str | KeyboardButton] = [
        b_coords_auto_def,
        CoordinateSettingsMenu.b_coords_man_def,
        CoordinateSettingsMenu.b_coords_check,
        CoordinateSettingsMenu.b_coords_del,
        b_back_to_start,
    ]
    ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard))


@tg_handle(text=CoordinateSettingsMenu.b_coords_del)
def handle_coordinates_delete(ctx: TGHandlerContext) -> None:
    ctx.db.delete_user_coordinates(ctx.user_id)
    bot_message = (
        'Ваши "домашние координаты" удалены. Теперь расстояние и направление '
        'до поисков не будет отображаться.\n'
        'Вы в любой момент можете заново ввести новые "домашние координаты". '
        'Функция Автоматического определения координат работает только для '
        'носимых устройств, для настольного компьютера – воспользуйтесь '
        'ручным вводом.'
    )
    keyboard: list[str | KeyboardButton] = [
        b_coords_auto_def,
        CoordinateSettingsMenu.b_coords_man_def,
        CoordinateSettingsMenu.b_coords_check,
        b_back_to_start,
    ]
    ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard))


@tg_handle(text=CoordinateSettingsMenu.b_coords_check)
def handle_coordinates_show_saved(ctx: TGHandlerContext) -> None:
    lat, lon = ctx.db.get_user_coordinates_or_none(ctx.user_id)

    if lat and lon:
        bot_message = f'Ваши "домашние координаты" {generate_yandex_maps_place_link(lat, lon, "coords")}'
    else:
        bot_message = 'Ваши координаты пока не сохранены. Введите их автоматически или вручную.'

    keyboard: list[str | KeyboardButton] = [
        b_coords_auto_def,
        CoordinateSettingsMenu.b_coords_man_def,
        CoordinateSettingsMenu.b_coords_check,
        CoordinateSettingsMenu.b_coords_del,
        b_back_to_start,
    ]

    ctx.reply(text=bot_message, reply_markup=create_one_column_reply_markup(keyboard))


@tg_handle(text=CoordinateSettingsMenu.b_coords_man_def)
def handle_coordinates_menu_manual_input(ctx: TGHandlerContext) -> None:
    bot_message = (
        'Введите координаты вашего дома вручную в теле сообщения и просто '
        'отправьте. Формат: XX.XXXХХ, XX.XXXХХ, где количество цифр после точки '
        'может быть различным. Широта (первое число) должна быть между 30 '
        'и 80, Долгота (второе число) – между 10 и 190.'
    )
    ctx.reply(text=bot_message, reply_markup=ReplyKeyboardRemove())
    ctx.set_state(UserInputState.input_of_coords_man)
