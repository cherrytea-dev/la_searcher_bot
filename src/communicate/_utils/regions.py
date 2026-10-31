from functools import cache
from itertools import chain

from pydantic import BaseModel, ConfigDict
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .buttons import b_back_to_start, b_fed_dist_other_r, b_fed_dist_pick_other
from .common import InlineButtonCallbackData


class FederalDistrict(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    provinces: tuple[tuple[str, tuple[int, ...]], ...]

    def get_buttons(self) -> list[list[str]]:
        buttons = [[x[0]] for x in self.provinces]
        buttons.append([b_fed_dist_pick_other])
        buttons.append([b_back_to_start])

        return buttons


GEO_KEYBOARD_NAME = 'reg'


class Geography(BaseModel):
    model_config = ConfigDict(frozen=True)

    fed_okrugs: tuple[FederalDistrict, ...]

    def filter_regions(self, start: str) -> list[str]:
        start_and_finish = start.replace('Регионы ', '')
        _start = start_and_finish[0]
        _finish = start_and_finish[2]

        filtered = [x for x in self.all_region_names() if _start <= x[0] <= _finish]
        return sorted(filtered)

    @cache  # noqa: B019 — `geography` is a module-level singleton
    def full_regions_list(self) -> list[list[str]]:
        regions = [x.get_buttons()[:-2] for x in self.fed_okrugs]
        res = list(chain(*regions))
        res.append([b_fed_dist_other_r])
        return res

    @cache  # noqa: B019 — `geography` is a module-level singleton
    def folder_dict(self) -> dict[str, tuple[int, ...]]:
        all_tuples = [x.provinces for x in self.fed_okrugs]
        all_tuples_joined = tuple(chain(*all_tuples))
        folders = {province: folders for province, folders in all_tuples_joined}
        folders['Прочие поиски по РФ'] = (116,)
        return folders

    def forum_folders_to_regions_list(self, user_curr_regs_list: list[int]) -> list[str]:
        """to get region name by any containing folder id"""
        rev_reg_dict = {value[0]: key for (key, value) in self.folder_dict().items()}
        regions: list[str] = []

        for user_region in user_curr_regs_list:
            if user_region in rev_reg_dict:
                regions.append(rev_reg_dict[user_region])
        return regions

    @cache  # noqa: B019 — `geography` is a module-level singleton
    def all_region_names(self) -> list[str]:
        names = [word[0] for word in self.full_regions_list()]
        names.sort()
        return names

    def _get_first_letter_buttons(self, selected_regions: list[str]) -> list[InlineKeyboardButton]:
        selected_regions_first_letters = set([x[0] for x in selected_regions])
        first_letters = set([x[0] for x in self.all_region_names()])

        buttons = []
        for current_letter in sorted(first_letters):
            callback_data = InlineButtonCallbackData(keyboard_name=GEO_KEYBOARD_NAME, action=current_letter)
            button_text = _format_text_if_selected(current_letter, selected_regions_first_letters)
            buttons.append(InlineKeyboardButton(text=button_text, callback_data=callback_data.as_str()))
        return buttons

    def get_inline_keyboard_by_first_letter(self, letter: str, selected_regions: list[str]) -> InlineKeyboardMarkup:
        letters_buttons = self._get_first_letter_buttons(selected_regions)
        region_buttons = self._get_regions_by_first_letter(letter, selected_regions)
        empty_callback_data = InlineButtonCallbackData(keyboard_name=GEO_KEYBOARD_NAME, action='close')

        placeholder = InlineKeyboardButton(
            text='-' * 22 + '      Завершить      ' + '-' * 22 + ' ' * 20,  # to take maximum screen width
            callback_data=empty_callback_data.as_str(),
        )

        return InlineKeyboardMarkup(
            [*arrange_buttons_to_rows(letters_buttons, 5), [placeholder], *arrange_buttons_to_rows(region_buttons, 2)],
        )

    def get_selected_region_name_by_order(self, index: int) -> str:
        return self.all_region_names()[index]

    def _get_regions_by_first_letter(self, letter: str, selected_regions: list[str]) -> list[InlineKeyboardButton]:
        if letter == '+':
            filtered_regions = [
                'Москва и МО: Активные Поиски',
                'Ленинградская обл.',
                'Москва и МО: Инфо Поддержка',
                'Самарская обл.',
            ]
        else:
            filtered_regions = [x for x in self.all_region_names() if x.startswith(letter)]

        buttons = []
        for region_name in filtered_regions:
            callback_data = InlineButtonCallbackData(
                keyboard_name=GEO_KEYBOARD_NAME,
                action=self.all_region_names().index(region_name),
                letter_to_show=letter,
            )
            button_text = _format_text_if_selected(region_name, selected_regions)
            buttons.append(InlineKeyboardButton(text=button_text, callback_data=callback_data.as_str()))
        return buttons


all_fed_okr = (
    FederalDistrict(
        name='Дальневосточный ФО',
        provinces=(
            ('Бурятия', (274,)),
            ('Приморский край', (298,)),
            ('Хабаровский край', (154,)),
            ('Амурская обл.', (390,)),
            ('Прочие поиски по ДФО', (188,)),
        ),
    ),
    FederalDistrict(
        name='Приволжский ФО',
        provinces=(
            ('Башкортостан', (191,)),
            ('Кировская обл.', (211,)),
            ('Марий Эл', (295,)),
            ('Мордовия', (294,)),
            ('Нижегородская обл.', (121,)),
            ('Оренбургская обл.', (337,)),
            ('Пензенская обл.', (170,)),
            ('Пермский край', (143,)),
            ('Самарская обл.', (333, 334)),
            ('Саратовская обл.', (212,)),
            ('Татарстан', (163,)),
            ('Удмуртия', (237,)),
            ('Ульяновская обл.', (290,)),
            ('Чувашия', (265,)),
            ('Прочие поиски по ПФО', (183,)),
        ),
    ),
    FederalDistrict(
        name='Северо-Кавказский ФО',
        provinces=(
            ('Дагестан', (292,)),
            ('Ставропольский край', (173,)),
            ('Чечня', (291,)),
            ('Кабардино-Балкария', (301,)),
            ('Ингушетия', (422,)),
            ('Северная Осетия', (423,)),
            ('Прочие поиски по СКФО', (184,)),
        ),
    ),
    FederalDistrict(
        name='Северо-Западный ФО',
        provinces=(
            ('Вологодская обл.', (370, 369, 367)),
            ('Карелия', (403,)),
            ('Коми', (378, 377)),
            ('Ленинградская обл.', (120,)),
            ('Мурманская обл.', (214, 371, 372)),
            ('Псковская обл.', (210, 383)),
            ('Архангельская обл.', (330,)),
            ('Прочие поиски по СЗФО', (181,)),
        ),
    ),
    FederalDistrict(
        name='Сибирский ФО',
        provinces=(
            ('Алтайский край', (161,)),
            ('Иркутская обл.', (137, 387, 386)),
            ('Кемеровская обл.', (202,)),
            ('Красноярский край', (269,)),
            ('Новосибирская обл.', (177,)),
            ('Омская обл.', (153,)),
            ('Томская обл.', (215,)),
            ('Хакасия', (402,)),
            ('Прочие поиски по СФО', (182,)),
        ),
    ),
    FederalDistrict(
        name='Уральский ФО',
        provinces=(
            ('Свердловская обл.', (213,)),
            ('Курганская обл.', (391,)),
            ('Тюменская обл.', (339,)),
            ('Ханты-Мансийский АО', (338,)),
            ('Челябинская обл.', (280,)),
            ('Ямало-Ненецкий АО', (204,)),
            ('Прочие поиски по УФО', (187,)),
        ),
    ),
    FederalDistrict(
        name='Центральный ФО',
        provinces=(
            ('Белгородская обл.', (236,)),
            ('Брянская обл.', (138,)),
            ('Владимирская обл.', (123,)),
            ('Воронежская обл.', (271,)),
            ('Ивановская обл.', (132,)),
            ('Калужская обл.', (185,)),
            ('Костромская обл.', (151,)),
            ('Курская обл.', (186,)),
            ('Липецкая обл.', (272,)),
            ('Москва и МО: Активные Поиски', (276,)),
            ('Москва и МО: Инфо Поддержка', (41,)),
            ('Орловская обл.', (222,)),
            ('Рязанская обл.', (155,)),
            ('Смоленская обл.', (122,)),
            ('Тамбовская обл.', (273,)),
            ('Тверская обл.', (126,)),
            ('Тульская обл.', (125,)),
            ('Ярославская обл.', (264,)),
            ('Прочие поиски по ЦФО', (179,)),
        ),
    ),
    FederalDistrict(
        name='Южный ФО',
        provinces=(
            ('Адыгея', (299,)),
            ('Астраханская обл.', (336,)),
            ('Волгоградская обл.', (131,)),
            ('Краснодарский край', (162,)),
            ('Крым', (293,)),
            ('Ростовская обл.', (157,)),
            ('Прочие поиски по ЮФО', (180,)),
        ),
    ),
)


geography = Geography(fed_okrugs=all_fed_okr)


def arrange_buttons_to_rows(
    buttons: list[InlineKeyboardButton], columns_count: int
) -> list[list[InlineKeyboardButton]]:
    return [buttons[start_index : start_index + columns_count] for start_index in range(0, len(buttons), columns_count)]


def _format_text_if_selected(text: str, selected: list[str] | set[str]) -> str:
    return '✅ ' + text if text in selected else text
