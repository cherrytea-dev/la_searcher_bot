from enum import Enum

from telegram import KeyboardButton, ReplyKeyboardMarkup

fed_okr_dict = {
    'Дальневосточный ФО',
    'Приволжский ФО',
    'Северо-Кавказский ФО',
    'Северо-Западный ФО',
    'Сибирский ФО',
    'Уральский ФО',
    'Центральный ФО',
    'Южный ФО',
}
# upload the new regional setting
folder_dict = {
    'Москва и МО: Активные Поиски': [276],
    'Москва и МО: Инфо Поддержка': [41],
    'Белгородская обл.': [236],
    'Брянская обл.': [138],
    'Владимирская обл.': [123, 233],
    'Воронежская обл.': [271, 315],
    'Ивановская обл.': [132, 193],
    'Калужская обл.': [185],
    'Костромская обл.': [151],
    'Курская обл.': [186],
    'Липецкая обл.': [272],
    'Орловская обл.': [222, 324],
    'Рязанская обл.': [155],
    'Смоленская обл.': [122],
    'Тамбовская обл.': [273],
    'Тверская обл.': [126],
    'Тульская обл.': [125],
    'Ярославская обл.': [264],
    'Прочие поиски по ЦФО': [179],
    'Адыгея': [299],
    'Астраханская обл.': [336],
    'Волгоградская обл.': [131],
    'Краснодарский край': [162],
    'Крым': [293],
    'Ростовская обл.': [157],
    'Прочие поиски по ЮФО': [180],
    'Архангельская обл.': [330],
    'Вологодская обл.': [370, 369, 368, 367],
    'Карелия': [403, 404],
    'Коми': [378, 377, 376],
    'Ленинградская обл.': [120, 300],
    'Мурманская обл.': [214, 371, 372, 373],
    'Псковская обл.': [210, 383, 382],
    'Прочие поиски по СЗФО': [181],
    'Амурская обл.': [390],
    'Бурятия': [274],
    'Приморский край': [298],
    'Хабаровский край': [154],
    'Прочие поиски по ДФО': [188],
    'Алтайский край': [161],
    'Иркутская обл.': [137, 387, 386, 303],
    'Кемеровская обл.': [202, 308],
    'Красноярский край': [269, 318],
    'Новосибирская обл.': [177, 310],
    'Омская обл.': [153, 314],
    'Томская обл.': [215, 401],
    'Хакасия': [402],
    'Прочие поиски по СФО': [182],
    'Свердловская обл.': [213],
    'Курганская обл.': [391, 392],
    'Тюменская обл.': [339],
    'Ханты-Мансийский АО': [338],
    'Челябинская обл.': [280],
    'Ямало-Ненецкий АО': [204],
    'Прочие поиски по УФО': [187],
    'Башкортостан': [191, 235],
    'Кировская обл.': [211, 275],
    'Марий Эл': [295, 297],
    'Мордовия': [294],
    'Нижегородская обл.': [121, 289],
    'Оренбургская обл.': [337],
    'Пензенская обл.': [170, 322],
    'Пермский край': [143, 325],
    'Самарская обл.': [333, 334, 305],
    'Саратовская обл.': [212],
    'Татарстан': [163, 231],
    'Удмуртия': [237, 239],
    'Ульяновская обл.': [290, 320],
    'Чувашия': [265, 327],
    'Прочие поиски по ПФО': [183],
    'Дагестан': [292],
    'Ставропольский край': [173],
    'Чечня': [291],
    'Кабардино-Балкария': [301],
    'Ингушетия': [422],
    'Северная Осетия': [423],
    'Прочие поиски по СКФО': [184],
    'Прочие поиски по РФ': [116],
}


class ExtendedEnum(Enum):
    @classmethod
    def list(cls):
        return list(map(lambda c: c.value, cls))


# Buttons & Keyboards
# Start & Main menu
c_start = '/start'


class Commands(str, ExtendedEnum):
    c_view_act_searches = '/view_act_searches'
    c_view_latest_searches = '/view_latest_searches'
    c_settings = '/settings'
    c_other = '/other'
    c_map = '/map'


class RoleChoice(str, ExtendedEnum):
    b_role_iam_la = 'я состою в ЛизаАлерт'
    b_role_want_to_be_la = 'я хочу помогать ЛизаАлерт'
    b_role_looking_for_person = 'я ищу человека'
    b_role_other = 'у меня другая задача'
    b_role_secret = 'не хочу говорить'


b_orders_done = 'да, заявки поданы'
b_orders_tbd = 'нет, но я хочу продолжить'

# TODO - WIP: FORUM
b_forum_check_nickname = 'указать свой nickname с форума'  # noqa
b_forum_dont_have = 'у меня нет аккаунта на форуме ЛА'  # noqa
b_forum_dont_want = 'пропустить / не хочу говорить'  # noqa
# TODO ^^^


class UrgencySettings(str, ExtendedEnum):
    b_pref_urgency_highest = 'самым первым (<2 минуты)'
    b_pref_urgency_high = 'пораньше (<5 минут)'
    b_pref_urgency_medium = 'могу ждать (<10 минут)'
    b_pref_urgency_low = 'не сильно важно (>10 минут)'


b_yes_its_me = 'да, это я'
b_no_its_not_me = 'нет, это не я'

b_view_act_searches = 'посмотреть актуальные поиски'
b_settings = 'настроить бот'
b_other = 'другие возможности'
b_map = '🔥Карта Поисков 🔥'
keyboard_main = [[b_map], [b_view_act_searches], [b_settings], [b_other]]
reply_markup_main = ReplyKeyboardMarkup(keyboard_main, resize_keyboard=True)


class MainSettingsMenu(str, ExtendedEnum):
    # Settings menu
    b_set_pref_notif_type = 'настроить виды уведомлений'
    b_set_pref_coords = 'настроить "домашние координаты"'
    b_set_pref_radius = 'настроить максимальный радиус'
    b_set_pref_age = 'настроить возрастные группы БВП'
    b_set_pref_urgency = 'настроить скорость уведомлений'  # <-- TODO: likely to be removed as redundant
    b_set_pref_role = 'настроить вашу роль'  # <-- TODO # noqa
    b_set_forum_nick = 'связать аккаунты бота и форума'
    b_change_forum_nick = 'изменить аккаунт форума'  # noqa
    b_set_topic_type = 'настроить вид поисков'


b_back_to_start = 'в начало'


class NotificationSettingsMenu(str, ExtendedEnum):
    # Settings - notifications
    b_act_all = 'включить: все уведомления'
    b_act_new_search = 'включить: о новых поисках'
    b_act_stat_change = 'включить: об изменениях статусов'
    b_act_all_comments = 'включить: о всех новых комментариях'
    b_act_inforg_com = 'включить: о комментариях Инфорга'
    b_act_field_trips_new = 'включить: о новых выездах'
    b_act_field_trips_change = 'включить: об изменениях в выездах'
    b_act_coords_change = 'включить: о смене места штаба'
    b_act_first_post_change = 'включить: об изменениях в первом посте'
    b_act_all_in_followed_search = 'включить: в отслеживаемых поисках - все уведомления'
    b_deact_all = 'настроить более гибко'
    b_deact_new_search = 'отключить: о новых поисках'
    b_deact_stat_change = 'отключить: об изменениях статусов'
    b_deact_all_comments = 'отключить: о всех новых комментариях'
    b_deact_inforg_com = 'отключить: о комментариях Инфорга'
    b_deact_field_trips_new = 'отключить: о новых выездах'
    b_deact_field_trips_change = 'отключить: об изменениях в выездах'
    b_deact_coords_change = 'отключить: о смене места штаба'
    b_deact_first_post_change = 'отключить: об изменениях в первом посте'
    b_deact_all_in_followed_search = 'отключить: в отслеживаемых поисках - все уведомления'


# Settings - coordinates
b_coords_auto_def = KeyboardButton(text='автоматически определить "домашние координаты"', request_location=True)
b_coords_man_def = 'ввести "домашние координаты" вручную'
b_coords_check = 'посмотреть сохраненные "домашние координаты"'
b_coords_del = 'удалить "домашние координаты"'

# Dialogue if Region – is Moscow
b_reg_moscow = 'да, Москва – мой регион'
b_reg_not_moscow = 'нет, я из другого региона'

# Settings - Federal Districts
b_fed_dist_dal_vos = 'Дальневосточный ФО'
b_fed_dist_privolz = 'Приволжский ФО'
b_fed_dist_sev_kaz = 'Северо-Кавказский ФО'
b_fed_dist_sev_zap = 'Северо-Западный ФО'
b_fed_dist_sibiria = 'Сибирский ФО'
b_fed_dist_uralsky = 'Уральский ФО'
b_fed_dist_central = 'Центральный ФО'
b_fed_dist_yuzhniy = 'Южный ФО'
b_fed_dist_other_r = 'Прочие поиски по РФ'
b_fed_dist_pick_other = 'выбрать другой Федеральный Округ'
keyboard_fed_dist_set = [
    [b_fed_dist_dal_vos],
    [b_fed_dist_privolz],
    [b_fed_dist_sev_kaz],
    [b_fed_dist_sev_zap],
    [b_fed_dist_sibiria],
    [b_fed_dist_uralsky],
    [b_fed_dist_central],
    [b_fed_dist_yuzhniy],
    [b_fed_dist_other_r],
    [b_back_to_start],
]

# Settings - Dalnevostochniy Fed Dist - Regions
b_reg_buryatiya = 'Бурятия'
b_reg_prim_kray = 'Приморский край'
b_reg_habarovsk = 'Хабаровский край'
b_reg_amur = 'Амурская обл.'
b_reg_dal_vost_other = 'Прочие поиски по ДФО'
keyboard_dal_vost_reg_choice = [
    [b_reg_buryatiya],
    [b_reg_prim_kray],
    [b_reg_habarovsk],
    [b_reg_amur],
    [b_reg_dal_vost_other],
    [b_fed_dist_pick_other],
    [b_back_to_start],
]

# Settings - Privolzhskiy Fed Dist - Regions
b_reg_bashkorkostan = 'Башкортостан'
b_reg_kirov = 'Кировская обл.'
b_reg_mariy_el = 'Марий Эл'
b_reg_mordovia = 'Мордовия'
b_reg_nizhniy = 'Нижегородская обл.'
b_reg_orenburg = 'Оренбургская обл.'
b_reg_penza = 'Пензенская обл.'
b_reg_perm = 'Пермский край'
b_reg_samara = 'Самарская обл.'
b_reg_saratov = 'Саратовская обл.'
b_reg_tatarstan = 'Татарстан'
b_reg_udmurtiya = 'Удмуртия'
b_reg_ulyanovsk = 'Ульяновская обл.'
b_reg_chuvashiya = 'Чувашия'
b_reg_privolz_other = 'Прочие поиски по ПФО'
keyboard_privolz_reg_choice = [
    [b_reg_bashkorkostan],
    [b_reg_kirov],
    [b_reg_mariy_el],
    [b_reg_mordovia],
    [b_reg_nizhniy],
    [b_reg_orenburg],
    [b_reg_penza],
    [b_reg_perm],
    [b_reg_samara],
    [b_reg_saratov],
    [b_reg_tatarstan],
    [b_reg_udmurtiya],
    [b_reg_ulyanovsk],
    [b_reg_chuvashiya],
    [b_reg_privolz_other],
    [b_fed_dist_pick_other],
    [b_back_to_start],
]

# Settings - Severo-Kavkazskiy Fed Dist - Regions
b_reg_dagestan = 'Дагестан'
b_reg_stavropol = 'Ставропольский край'
b_reg_chechnya = 'Чечня'
b_reg_kabarda = 'Кабардино-Балкария'
b_reg_ingushetia = 'Ингушетия'
b_reg_sev_osetia = 'Северная Осетия'
b_reg_sev_kav_other = 'Прочие поиски по СКФО'
keyboard_sev_kav_reg_choice = [
    [b_reg_dagestan],
    [b_reg_stavropol],
    [b_reg_chechnya],
    [b_reg_kabarda],
    [b_reg_ingushetia],
    [b_reg_sev_osetia],
    [b_reg_sev_kav_other],
    [b_fed_dist_pick_other],
    [b_back_to_start],
]

# Settings - Severo-Zapadniy Fed Dist - Regions
b_reg_vologda = 'Вологодская обл.'
b_reg_karelia = 'Карелия'
b_reg_komi = 'Коми'
b_reg_piter = 'Ленинградская обл.'
b_reg_murmansk = 'Мурманская обл.'
b_reg_pskov = 'Псковская обл.'
b_reg_archangelsk = 'Архангельская обл.'
b_reg_sev_zap_other = 'Прочие поиски по СЗФО'
keyboard_sev_zap_reg_choice = [
    [b_reg_vologda],
    [b_reg_komi],
    [b_reg_karelia],
    [b_reg_piter],
    [b_reg_murmansk],
    [b_reg_pskov],
    [b_reg_archangelsk],
    [b_reg_sev_zap_other],
    [b_fed_dist_pick_other],
    [b_back_to_start],
]

# Settings - Sibirskiy Fed Dist - Regions
b_reg_altay = 'Алтайский край'
b_reg_irkutsk = 'Иркутская обл.'
b_reg_kemerovo = 'Кемеровская обл.'
b_reg_krasnoyarsk = 'Красноярский край'
b_reg_novosib = 'Новосибирская обл.'
b_reg_omsk = 'Омская обл.'
b_reg_tomsk = 'Томская обл.'
b_reg_hakasiya = 'Хакасия'
b_reg_sibiria_reg_other = 'Прочие поиски по СФО'
keyboard_sibiria_reg_choice = [
    [b_reg_altay],
    [b_reg_irkutsk],
    [b_reg_kemerovo],
    [b_reg_krasnoyarsk],
    [b_reg_novosib],
    [b_reg_omsk],
    [b_reg_tomsk],
    [b_reg_hakasiya],
    [b_reg_sibiria_reg_other],
    [b_fed_dist_pick_other],
    [b_back_to_start],
]

# Settings - Uralskiy Fed Dist - Regions
b_reg_ekat = 'Свердловская обл.'
b_reg_kurgan = 'Курганская обл.'
b_reg_tyumen = 'Тюменская обл.'
b_reg_hanty_mansi = 'Ханты-Мансийский АО'
b_reg_chelyabinks = 'Челябинская обл.'
b_reg_yamal = 'Ямало-Ненецкий АО'
b_reg_urals_reg_other = 'Прочие поиски по УФО'
keyboard_urals_reg_choice = [
    [b_reg_ekat],
    [b_reg_kurgan],
    [b_reg_tyumen],
    [b_reg_hanty_mansi],
    [b_reg_chelyabinks],
    [b_reg_yamal],
    [b_reg_urals_reg_other],
    [b_fed_dist_pick_other],
    [b_back_to_start],
]

# Settings - Central Fed Dist - Regions
b_reg_belogorod = 'Белгородская обл.'
b_reg_bryansk = 'Брянская обл.'
b_reg_vladimir = 'Владимирская обл.'
b_reg_voronezh = 'Воронежская обл.'
b_reg_ivanovo = 'Ивановская обл.'
b_reg_kaluga = 'Калужская обл.'
b_reg_kostroma = 'Костромская обл.'
b_reg_kursk = 'Курская обл.'
b_reg_lipetsk = 'Липецкая обл.'
b_reg_msk_act = 'Москва и МО: Активные Поиски'
b_reg_msk_inf = 'Москва и МО: Инфо Поддержка'
b_reg_orel = 'Орловская обл.'
b_reg_ryazan = 'Рязанская обл.'
b_reg_smolensk = 'Смоленская обл.'
b_reg_tambov = 'Тамбовская обл.'
b_reg_tver = 'Тверская обл.'
b_reg_tula = 'Тульская обл.'
b_reg_yaroslavl = 'Ярославская обл.'
b_reg_central_reg_other = 'Прочие поиски по ЦФО'
keyboard_central_reg_choice = [
    [b_reg_belogorod],
    [b_reg_bryansk],
    [b_reg_vladimir],
    [b_reg_voronezh],
    [b_reg_ivanovo],
    [b_reg_kaluga],
    [b_reg_kostroma],
    [b_reg_kursk],
    [b_reg_lipetsk],
    [b_reg_msk_act],
    [b_reg_msk_inf],
    [b_reg_orel],
    [b_reg_ryazan],
    [b_reg_smolensk],
    [b_reg_tambov],
    [b_reg_tver],
    [b_reg_tula],
    [b_reg_yaroslavl],
    [b_reg_central_reg_other],
    [b_fed_dist_pick_other],
    [b_back_to_start],
]

# Settings - Yuzhniy Fed Dist - Regions
b_reg_adygeya = 'Адыгея'
b_reg_astrahan = 'Астраханская обл.'
b_reg_volgograd = 'Волгоградская обл.'
b_reg_krasnodar = 'Краснодарский край'
b_reg_krym = 'Крым'
b_reg_rostov = 'Ростовская обл.'
b_reg_yuzhniy_reg_other = 'Прочие поиски по ЮФО'
keyboard_yuzhniy_reg_choice = [
    [b_reg_adygeya],
    [b_reg_astrahan],
    [b_reg_volgograd],
    [b_reg_krasnodar],
    [b_reg_krym],
    [b_reg_rostov],
    [b_reg_yuzhniy_reg_other],
    [b_fed_dist_pick_other],
    [b_back_to_start],
]

# Settings - Fed Dist - Regions
b_menu_set_region = 'настроить регион поисков'

full_list_of_regions = (
    keyboard_dal_vost_reg_choice[:-1]
    + keyboard_privolz_reg_choice[:-1]
    + keyboard_sev_kav_reg_choice[:-1]
    + keyboard_sev_zap_reg_choice[:-1]
    + keyboard_sibiria_reg_choice[:-1]
    + keyboard_urals_reg_choice[:-1]
    + keyboard_central_reg_choice[:-1]
    + keyboard_yuzhniy_reg_choice[:-1]
    + [[b_fed_dist_other_r]]
)  # noqa – for strange pycharm indent warning
full_dict_of_regions = {word[0] for word in full_list_of_regions}

dict_of_fed_dist = {
    b_fed_dist_dal_vos: keyboard_dal_vost_reg_choice,
    b_fed_dist_privolz: keyboard_privolz_reg_choice,
    b_fed_dist_sev_kaz: keyboard_sev_kav_reg_choice,
    b_fed_dist_sev_zap: keyboard_sev_zap_reg_choice,
    b_fed_dist_sibiria: keyboard_sibiria_reg_choice,
    b_fed_dist_uralsky: keyboard_urals_reg_choice,
    b_fed_dist_central: keyboard_central_reg_choice,
    b_fed_dist_yuzhniy: keyboard_yuzhniy_reg_choice,
}

# Other menu
b_view_latest_searches = 'посмотреть последние поиски'
b_goto_community = 'написать разработчику бота'
b_goto_first_search = 'ознакомиться с информацией для новичка'
b_goto_photos = 'посмотреть красивые фото с поисков'
b_act_titles = 'названия'  # these are "Title update notification" button
