from dataclasses import dataclass
from itertools import chain

from communicate._utils.buttons import b_back_to_start, b_fed_dist_other_r, b_fed_dist_pick_other


@dataclass
class FederalDistrict:
    name: str
    provinces: list[tuple[str, list[int]]]

    def get_buttons(self) -> list[list[str]]:
        buttons = [[x[0]] for x in self.provinces]
        buttons.append([b_fed_dist_pick_other])
        buttons.append([b_back_to_start])

        return buttons


@dataclass
class Federal:
    fed_okrugs: list[FederalDistrict]

    def full_regions_list(self) -> list[list[str]]:
        # regions = [x.get_buttons()[:-1] for x in self.fed_okrugs]# was error?
        regions = [x.get_buttons()[:-2] for x in self.fed_okrugs]
        res = list(chain(*regions))
        res.append([b_fed_dist_other_r])
        return res

    def get_keyboard_fed_dist_set(self) -> list[list[str]]:
        res = [[x.name] for x in self.fed_okrugs]
        res.append([b_fed_dist_other_r])
        res.append([b_back_to_start])
        return res

    def get_folder_dict(self) -> dict[str, list[int]]:
        all_tuples = [x.provinces for x in self.fed_okrugs]
        all_tuples_joined = list(chain(*all_tuples))
        folders = {province: folders for province, folders in all_tuples_joined}
        folders['Прочие поиски по РФ'] = [116]
        return folders


all_fed_okr = [
    FederalDistrict(
        name='Дальневосточный ФО',
        provinces=[
            ('Бурятия', [274]),
            ('Приморский край', [298]),
            ('Хабаровский край', [154]),
            ('Амурская обл.', [390]),
            ('Прочие поиски по ДФО', [188]),
        ],
    ),
    FederalDistrict(
        name='Приволжский ФО',
        provinces=[
            ('Башкортостан', [191, 235]),
            ('Кировская обл.', [211, 275]),
            ('Марий Эл', [295, 297]),
            ('Мордовия', [294]),
            ('Нижегородская обл.', [121, 289]),
            ('Оренбургская обл.', [337]),
            ('Пензенская обл.', [170, 322]),
            ('Пермский край', [143, 325]),
            ('Самарская обл.', [333, 334, 305]),
            ('Саратовская обл.', [212]),
            ('Татарстан', [163, 231]),
            ('Удмуртия', [237, 239]),
            ('Ульяновская обл.', [290, 320]),
            ('Чувашия', [265, 327]),
            ('Прочие поиски по ПФО', [183]),
        ],
    ),
    FederalDistrict(
        name='Северо-Кавказский ФО',
        provinces=[
            ('Дагестан', [292]),
            ('Ставропольский край', [173]),
            ('Чечня', [291]),
            ('Кабардино-Балкария', [301]),
            ('Ингушетия', [422]),
            ('Северная Осетия', [423]),
            ('Прочие поиски по СКФО', [184]),
        ],
    ),
    FederalDistrict(
        name='Северо-Западный ФО',
        provinces=[
            ('Вологодская обл.', [370, 369, 368, 367]),
            ('Карелия', [403, 404]),
            ('Коми', [378, 377, 376]),
            ('Ленинградская обл.', [120, 300]),
            ('Мурманская обл.', [214, 371, 372, 373]),
            ('Псковская обл.', [210, 383, 382]),
            ('Архангельская обл.', [330]),
            ('Прочие поиски по СЗФО', [181]),
        ],
    ),
    FederalDistrict(
        name='Сибирский ФО',
        provinces=[
            ('Алтайский край', [161]),
            ('Иркутская обл.', [137, 387, 386, 303]),
            ('Кемеровская обл.', [202, 308]),
            ('Красноярский край', [269, 318]),
            ('Новосибирская обл.', [177, 310]),
            ('Омская обл.', [153, 314]),
            ('Томская обл.', [215, 401]),
            ('Хакасия', [402]),
            ('Прочие поиски по СФО', [182]),
        ],
    ),
    FederalDistrict(
        name='Уральский ФО',
        provinces=[
            ('Свердловская обл.', [213]),
            ('Курганская обл.', [391, 392]),
            ('Тюменская обл.', [339]),
            ('Ханты-Мансийский АО', [338]),
            ('Челябинская обл.', [280]),
            ('Ямало-Ненецкий АО', [204]),
            ('Прочие поиски по УФО', [187]),
        ],
    ),
    FederalDistrict(
        name='Центральный ФО',
        provinces=[
            ('Белгородская обл.', [236]),
            ('Брянская обл.', [138]),
            ('Владимирская обл.', [123, 233]),
            ('Воронежская обл.', [271, 315]),
            ('Ивановская обл.', [132, 193]),
            ('Калужская обл.', [185]),
            ('Костромская обл.', [151]),
            ('Курская обл.', [186]),
            ('Липецкая обл.', [272]),
            ('Москва и МО: Активные Поиски', [276]),
            ('Москва и МО: Инфо Поддержка', [41]),
            ('Орловская обл.', [222, 324]),
            ('Рязанская обл.', [155]),
            ('Смоленская обл.', [122]),
            ('Тамбовская обл.', [273]),
            ('Тверская обл.', [126]),
            ('Тульская обл.', [125]),
            ('Ярославская обл.', [264]),
            ('Прочие поиски по ЦФО', [179]),
        ],
    ),
    FederalDistrict(
        name='Южный ФО',
        provinces=[
            ('Адыгея', [299]),
            ('Астраханская обл.', [336]),
            ('Волгоградская обл.', [131]),
            ('Краснодарский край', [162]),
            ('Крым', [293]),
            ('Ростовская обл.', [157]),
            ('Прочие поиски по ЮФО', [180]),
        ],
    ),
]


federal = Federal(fed_okrugs=all_fed_okr)

_full_list_of_regions = federal.full_regions_list()
full_dict_of_regions = [word[0] for word in _full_list_of_regions]
dict_of_fed_dist = {x.name: x.get_buttons() for x in federal.fed_okrugs}
fed_okr_dict = set(x.name for x in federal.fed_okrugs)
keyboard_fed_dist_set = federal.get_keyboard_fed_dist_set()
folder_dict = federal.get_folder_dict()
