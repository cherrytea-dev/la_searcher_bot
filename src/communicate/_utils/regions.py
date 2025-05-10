from functools import cache
from itertools import chain

from pydantic import BaseModel, ConfigDict, Field
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .buttons import b_back_to_start, b_fed_dist_other_r, b_fed_dist_pick_other
from .common import ACTION_KEY, KEYBOARD_NAME_KEY


class FederalDistrict(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    provinces: tuple[tuple[str, tuple[int, ...]], ...]

    def get_buttons(self) -> list[list[str]]:
        buttons = [[x[0]] for x in self.provinces]
        buttons.append([b_fed_dist_pick_other])
        buttons.append([b_back_to_start])

        return buttons


class InlineButtonCallbackData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    keyboard_name: str | None = Field(default=None, alias=KEYBOARD_NAME_KEY)
    action: str | int | None = Field(default=None, alias=ACTION_KEY)

    def as_str(self) -> str:
        return str(self.model_dump(by_alias=True))
        # return self.model_dump_json(ensure_ascii=False, by_alias=True)


GEO_KEYBOARD_NAME = 'reg'


class Geography(BaseModel):
    model_config = ConfigDict(frozen=True)

    fed_okrugs: tuple[FederalDistrict, ...]

    def starting_buttons(self) -> list[str]:
        return [
            ['Регионы А-Б', 'Регионы В-И'],
            ['Регионы Й-К', 'Регионы Л-О'],
            ['Регионы П-П', 'Регионы Р-Т'],
            ['Регионы У-Я'],
        ]

    def starting_buttons_flat(self) -> list[str]:
        return list(chain(*self.starting_buttons()))

    def filter_regions(self, start: str) -> list[str]:
        start_and_finish = start.replace('Регионы ', '')
        _start = start_and_finish[0]
        _finish = start_and_finish[2]

        filtered = [x for x in self.all_region_names() if _start <= x[0] <= _finish]
        return sorted(filtered)

    @cache
    def full_regions_list(self) -> list[list[str]]:
        regions = [x.get_buttons()[:-2] for x in self.fed_okrugs]
        res = list(chain(*regions))
        res.append([b_fed_dist_other_r])
        return res

    @cache
    def keyboard_federal_districts(self) -> list[list[str]]:
        res = [[x.name] for x in self.fed_okrugs]
        res.append([b_fed_dist_other_r])
        res.append([b_back_to_start])
        return res

    @cache
    def folder_dict(self) -> dict[str, tuple[int, ...]]:
        all_tuples = [x.provinces for x in self.fed_okrugs]
        all_tuples_joined = tuple(chain(*all_tuples))
        folders = {province: folders for province, folders in all_tuples_joined}
        folders['Прочие поиски по РФ'] = (116,)
        return folders

    @cache
    def reversed_folder_dict(self) -> dict[int, str]:
        """to get region name by any containing folder id"""
        return {value[0]: key for (key, value) in self.folder_dict().items()}

    @cache
    def federal_district_names(self) -> list[str]:
        return [x.name for x in self.fed_okrugs]

    @cache
    def all_region_names(self) -> list[str]:
        names = [word[0] for word in self.full_regions_list()]
        names.sort()
        return names

    @cache
    def region_to_district_maping(self) -> dict[str, str]:
        region_to_district_maping: dict[str, str] = {}
        for fed_dist in self.fed_okrugs:
            for region in fed_dist.provinces:
                region_to_district_maping[region[0]] = fed_dist.name
        return region_to_district_maping

    def get_keyboard_by_region(self, region_name: str) -> list[list[str]]:
        region_to_district_maping = self.region_to_district_maping()
        try:
            fed_dist_name = region_to_district_maping[region_name]
            return self.get_keyboard_by_fed_district(fed_dist_name)
        except KeyError:
            # 116 - "Прочие поиски по РФ"
            return self.keyboard_federal_districts()

    def get_keyboard_by_fed_district(self, fed_district_name: str) -> list[list[str]]:
        federal_district_keyboards = {x.name: x.get_buttons() for x in self.fed_okrugs}
        return federal_district_keyboards[fed_district_name]

    def get_inline_keyboard_first_letters(self) -> InlineKeyboardMarkup:
        buttons = self._get_first_letter_buttons()
        return InlineKeyboardMarkup(arrange_buttons_to_rows(buttons, 5))

    def _get_first_letter_buttons(self) -> list[InlineKeyboardButton]:
        first_letters: set[str] = set()
        for x in self.all_region_names():
            first_letters.add(x[0])
        sorted_list = sorted(first_letters)

        buttons = []
        for current_letter in sorted_list:
            callback_data = InlineButtonCallbackData(keyboard_name=GEO_KEYBOARD_NAME, action=current_letter)
            buttons.append(InlineKeyboardButton(text=current_letter, callback_data=callback_data.as_str()))
        return buttons

    def get_inline_keyboard_by_first_letter(self, letter: str) -> InlineKeyboardMarkup:
        letters_buttons = self._get_first_letter_buttons()
        region_buttons = self._get_regions_by_first_letter(letter)

        return InlineKeyboardMarkup(
            arrange_buttons_to_rows(letters_buttons, 5)
            + [[InlineKeyboardButton(text='---------', callback_data='foo')]]
            + arrange_buttons_to_rows(region_buttons, 2),
        )

    def _get_regions_by_first_letter(self, letter: str) -> list[InlineKeyboardButton]:
        filtered_regions = [x for x in self.all_region_names() if x.startswith(letter)]

        buttons = []
        for region_name in filtered_regions:
            callback_data = InlineButtonCallbackData(
                keyboard_name=GEO_KEYBOARD_NAME,
                action=self.all_region_names().index(region_name),
            )
            buttons.append(InlineKeyboardButton(text=region_name, callback_data=callback_data.as_str()))
        return buttons


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


geography = Geography(fed_okrugs=all_fed_okr)


# next just to see distribution by alphabet
_all_regs = [
    'Адыгея',
    'Алтайский край',
    'Амурская обл.',
    'Архангельская обл.',
    'Астраханская обл.',
    ###
    'Башкортостан',
    'Белгородская обл.',
    'Брянская обл.',
    'Бурятия',
    ###
    'Владимирская обл.',
    'Волгоградская обл.',
    'Вологодская обл.',
    'Воронежская обл.',
    ###
    'Дагестан',
    ###
    'Ивановская обл.',
    'Ингушетия',
    'Иркутская обл.',
    ###
    'Кабардино-Балкария',
    'Калужская обл.',
    'Карелия',
    'Кемеровская обл.',
    'Кировская обл.',
    'Коми',
    'Костромская обл.',
    'Краснодарский край',
    'Красноярский край',
    'Крым',
    'Курганская обл.',
    'Курская обл.',
    ###
    'Ленинградская обл.',
    'Липецкая обл.',
    ###
    'Марий Эл',
    'Мордовия',
    'Москва и МО: Активные Поиски',
    'Москва и МО: Инфо Поддержка',
    'Мурманская обл.',
    ###
    'Нижегородская обл.',
    'Новосибирская обл.',
    ###
    'Омская обл.',
    'Оренбургская обл.',
    'Орловская обл.',
    ###
    'Пензенская обл.',
    'Пермский край',
    'Приморский край',
    'Прочие поиски по ДФО',
    'Прочие поиски по ПФО',
    'Прочие поиски по РФ',
    'Прочие поиски по СЗФО',
    'Прочие поиски по СКФО',
    'Прочие поиски по СФО',
    'Прочие поиски по УФО',
    'Прочие поиски по ЦФО',
    'Прочие поиски по ЮФО',
    'Псковская обл.',
    ###
    'Ростовская обл.',
    'Рязанская обл.',
    ###
    'Самарская обл.',
    'Саратовская обл.',
    'Свердловская обл.',
    'Северная Осетия',
    'Смоленская обл.',
    'Ставропольский край',
    ###
    'Тамбовская обл.',
    'Татарстан',
    'Тверская обл.',
    'Томская обл.',
    'Тульская обл.',
    'Тюменская обл.',
    ###
    'Удмуртия',
    'Ульяновская обл.',
    ###
    'Хабаровский край',
    'Хакасия',
    'Ханты-Мансийский АО',
    ###
    'Челябинская обл.',
    'Чечня',
    'Чувашия',
    ###
    'Ямало-Ненецкий АО',
    'Ярославская обл.',
]


def arrange_buttons_to_rows(buttons: list[str], columns_count: int) -> list[list[str]]:
    # if len(buttons) % columns_count != 0:
    #     raise ValueError(
    #         f'buttons length {len(buttons)} must be divisible by columns_count {columns_count}'
    #     )
    return [buttons[start_index : start_index + columns_count] for start_index in range(0, len(buttons), columns_count)]
