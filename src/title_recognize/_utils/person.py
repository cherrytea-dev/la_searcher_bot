import re
from datetime import datetime
from enum import Enum
from re import Match
from typing import Dict, List, Optional, Tuple

from dateutil import relativedelta

from .title_commons import Block, PersonGroup, age_wording, check_word_by_natasha


def is_child(age_max: int | None) -> bool:
    return age_max is None or age_max < 18


def is_child_2(age: int) -> bool:
    return age is not None and age < 18


def recognize_one_person_group(person: Block) -> PersonGroup:
    """Recognize the Displayed Name (Pseudonym) for a SINGLE person/group as well as age"""

    return PersonRecognizer(person).recognize()


class PersonRecognizer:
    def __init__(self, person: Block):
        self.person = person

    @property
    def name_string(self) -> str:
        return self.person.init

    def recognize(self) -> PersonGroup:
        handlers = [
            self._handle_case_0,
            self._handle_case_1,
            self._handle_case_2,
            self._handle_case_3,
            self._handle_case_4,
        ]
        for handler in handlers:
            person_reco = handler()
            if person_reco:
                return person_reco
        return self._handle_case_5()

    def _handle_case_0(self) -> PersonGroup | None:
        # CASE 0. When the whole person is defined as "+N" only (NB – we already cut "+" before)
        case_0 = re.search(
            r'^\W{0,2}\d(?=(\W{0,2}(человека|женщины|мужчины|девочки|мальчика|бабушки|дедушки))?' r'\W{0,4}$)',
            self.name_string,
        )
        if not case_0:
            return None

        num_of_per = int(case_0.group())
        if num_of_per == 1:
            display_name = 'Человек'
        elif num_of_per in {2, 3, 4}:
            display_name = f'{num_of_per} человека'
        else:
            display_name = f'{num_of_per} человек'

        return PersonGroup(num_of_per=num_of_per, name=display_name, display_name=display_name)

    def _handle_case_1(self) -> PersonGroup | None:
        # CASE 1. When there is only one person like "age" (e.g. "Пропал 10 лет")
        case = re.search(r'^1?\d?\d\W{0,3}(лет|года?)\W{0,2}$', self.name_string)
        if not case:
            return None

        match = re.search(r'\d{1,3}', self.name_string)
        if not match:
            return None

        age = int(match.group())
        name = 'Ребёнок' if is_child_2(age) else 'Человек'

        return PersonGroup(
            name=name,
            num_of_per=1,
            age=age,
            display_name=f'{name}{age_wording(age)}',
        )

    def _handle_case_2(self) -> PersonGroup | None:
        # CASE 2. When the whole person is defined as "+N age, age" only
        case_2_match = re.search(
            r'(?i)^\W{0,2}(\d(?!\d)|двое|трое)'
            r'(?=(\W{0,2}(человека|женщины?|мужчины?|девочки|мальчика|бабушки|дедушки))?)',
            self.name_string,
        )
        if not case_2_match:
            return None

        case_2 = case_2_match.group()
        if len(case_2) == 1:
            num_of_per = int(case_2)
        elif case_2[-4:] == 'двое':
            num_of_per = 2
        elif case_2[-4:] == 'трое':
            num_of_per = 3
        else:
            num_of_per = -1

        match = re.search(case_2, self.name_string)
        if not match:
            return None

        string_with_ages = self.name_string[match.span()[1] :]
        age_matches = re.findall(r'1?\d?\d(?=\W)', string_with_ages)
        ages_list = [int(x) for x in age_matches]
        age_min, age_max = None, None
        name = ''
        if ages_list:
            ages_list.sort()
            age_min = int(ages_list[0])
            age_max = int(ages_list[-1])

        if num_of_per == 1:
            name = 'Ребёнок' if ages_list and is_child(age_max) else 'Человек'
        elif num_of_per in {2, 3, 4}:
            wording = 'ребёнка' if ages_list and is_child(age_max) else 'человека'
            name = f'{num_of_per} {wording}'
        else:
            wording = 'детей' if ages_list and is_child(age_max) else 'человек'
            name = f'{num_of_per} {wording}'

        display_name = name
        if age_min and age_max:
            if age_min != age_max:
                display_name = f'{name} ' f'{age_min}–{age_max}' f' {age_wording(age_max)}'
            else:
                display_name = f'{name} ' f'{age_max}' f' {age_wording(age_max)}'

        return PersonGroup(
            num_of_per=num_of_per,
            display_name=display_name,
            name=name,
            age_min=age_min,
            age_max=age_max,
        )

    def _handle_case_3(self) -> PersonGroup | None:
        # CASE 3. When the "person" is defined as plural form  and ages like "people age, age"
        case_3_match = re.search(
            r'(?i)(?<!\d)(подростки|дети|люди|мужчины?|женщины?|мальчики|девочки|бабушки|дедушки)' r'\W{0,4}(?=\d)',
            self.name_string,
        )
        if not case_3_match:
            return None

        case_3 = case_3_match.group()

        match = re.search(case_3, self.name_string)
        if not match:
            return None

        string_with_ages = self.name_string[match.span()[1] :]
        ages_list = re.findall(r'1?\d?\d(?=\W)', string_with_ages)
        age_min, age_max = None, None
        if ages_list:
            # TODO fix and merge with similar code
            ages_list.sort()
            age_min = int(ages_list[0])
            age_max = int(ages_list[-1])

        name = 'Дети' if is_child(age_max) else 'Взрослые'

        display_name = name

        if age_min and age_max:
            if age_min != age_max:
                display_name = f'{name} ' f'{age_min}–{age_max}' f' {age_wording(age_max)}'
            else:
                display_name = f'{name} ' f'{age_max}' f' {age_wording(age_max)}'

        return PersonGroup(
            num_of_per=-1,
            age_min=age_min,
            age_max=age_max,
            name=name,
            display_name=display_name,
        )

    def _handle_case_4(self) -> PersonGroup | None:
        # CASE 4. When the whole person is defined as "role" only
        if not re.search(
            r'(?i)^(женщина|мужчина|декушка|человек|дочь|сын|жена|муж|отец|мать|папа|мама|'
            r'бабушка|дедушка)(?=\W{0,4}$)',
            self.name_string,
        ):
            return None

        match = re.search(r'(?i)^\w*(?=\W{0,4}$)', self.name_string)
        if not match:
            return None

        return PersonGroup(
            name=match.group(),
            display_name='Человек',
            num_of_per=1,
        )

    def _handle_case_5(self) -> PersonGroup:
        # CASE 5. All the other more usual cases
        name_string = self.person.init
        num_of_per, match = self._define_number_of_persons(name_string)
        age_string_start = match.span()[1] if match else 0
        age = AgeRecognizer(name_string, age_string_start).define_age_of_person()
        if age is not None:
            num_of_per = 1

        person_reco = PersonGroup(
            name=self._define_name(match, age or None),
            num_of_per=num_of_per,
            age=age or None,
            age_wording=self._define_age_wording(age),
        )

        self._define_display_name(person_reco)
        self._define_number_of_persons_by_natasha(person_reco, name_string)
        return person_reco

    def _define_number_of_persons(self, name_string: str) -> Tuple[int, Match | None]:
        """Define and return the number of persons out of string input"""

        name_string_end = -1

        # language=regexp
        pattern = r'\d{1,4}\W{0,3}(лет|л\.|года?|мес|г)?'
        block_0 = re.search(pattern, name_string)
        if block_0:
            name_string_end = block_0.span()[0]

        if name_string_end == 0:
            return 1, None

        # language=regexp
        patterns = [
            r'(?i)^\W{0,3}(\d|дв(а|о?е)|тр(ое|и)|чет(веро|ыре))(\W{1,2}'
            r'(человека?|женщин[аы]|мужчин[аы]?|реб[её]нок))?(?!\d)(?!\w)',  # case "2 человека"
            r'(?i)(^|(?<=\W))[\w-]{1,100}(?=\W)',  # regular case
        ]

        block = None
        for pattern in patterns:
            block = re.search(pattern, name_string)
            if not block:
                continue
            # language=regexp
            patterns_2 = [
                (
                    r'(?i)(?<!\w)(человек|женщина|мужчина|реб[её]нок|девочка|мальчик|девушка|'
                    r'мама|папа|сын|дочь|дедушка|бабушка)(?!\w)',
                    1,
                ),
                (r'(?i)(?<!\w)дв(а|о?е)(?!\w)', 2),
                (r'(?i)(?<!\w)(трое|три)(?!\w)', 3),
                (r'(?i)(?<!\w)чет(веро|ыре)(?!\w)', 4),
            ]
            for pattern_2, person_count in patterns_2:
                exact_num_of_individuals_in_group = re.search(pattern_2, name_string)
                if exact_num_of_individuals_in_group:
                    return person_count, block

        return -1, block  # -1 for unrecognized

    def _define_age_wording(self, age: int | None) -> str:
        if not age:
            return ''

        return f' {str(age)} {age_wording(age)}'

    def _define_name(self, match: Match | None, age: int | None) -> str:
        if match:
            return match.group()
        if age is not None and is_child_2(age):
            return 'Ребёнок'
        return 'Человек'

    def _define_display_name(self, person_reco: PersonGroup) -> None:
        """Define and record the name / pseudonym that will be displayed to users"""

        # DISPLAY NAME (PSEUDONYM) IDENTIFICATION

        display_name = f'{person_reco.name}{person_reco.age_wording}'
        person_reco.display_name = display_name.capitalize()

        # case of two-word last names like Tom-Scott. in this case capitalize killed capital S, and we restore it
        dashes_in_names = re.search(r'\w-\w', person_reco.display_name)
        if dashes_in_names:
            letter_to_up = dashes_in_names.span()[0] + 2
            d = person_reco.display_name
            person_reco.display_name = f'{d[:letter_to_up]}{d[letter_to_up].capitalize()}{d[letter_to_up + 1:]}'

    def _define_number_of_persons_by_natasha(self, person_reco: PersonGroup, name_string: str) -> None:
        """Check if name_string is a name and set num_of_per to 1 if yes"""

        # last chance to define number of persons in group - with help of Natasha
        if person_reco.num_of_per != -1:
            return
        patterns = [r'^\D*\w(?=\W{1,3}\d)', r'^\D*\w(?=\W{1,3}$)']

        for pattern in patterns:
            block_2 = re.search(pattern, name_string)

            if block_2:
                name_string_is_a_name = check_word_by_natasha(block_2.group(), 'per')
                if name_string_is_a_name:
                    person_reco.num_of_per = 1
                    break


class DatePart(str, Enum):
    age = 'age'
    year = 'year'
    months = 'months'
    date_full = 'date_full'
    date_short = 'date_short'
    number = 'number'


class AgeRecognizer:
    def __init__(self, name_string: str, age_string_start: int) -> None:
        self.name_string = name_string
        self.age_string_start = age_string_start

    def define_age_of_person(self) -> int | None:
        """Define and return the age (given or estimation based on birth year) for a person"""
        extracted_data = self._extract_age_related_data()
        return self._get_age_from_extracted_data(extracted_data)

    def _extract_age_related_data(self) -> dict[DatePart, str | None]:
        patterns = self._get_age_patterns()

        extracted_data: dict[DatePart, str | None]

        extracted_data = {x: None for x in DatePart}

        for pattern, pattern_type in patterns:
            block_2 = re.search(pattern, self.name_string[self.age_string_start :])
            if block_2:
                found_value = block_2.group()
                extracted_data[pattern_type] = found_value

        return extracted_data

    def _get_age_patterns(self) -> list[tuple[str, DatePart]]:
        return [
            (r'\d{2}.\d{2}\.\d{4}', DatePart.date_full),
            (r'\d{2}.\d{2}\.\d{2}(?!\d)', DatePart.date_short),
            (r'(?<!\d)\d{1,2}(?=\W{0,2}мес(\W|яц))', DatePart.months),
            (r'(?<!\d)1?\d{1,2}(?!(\W{0,2}мес|\W{0,3}\d))', DatePart.age),
            (r'(?<!\d)\d{4}', DatePart.year),
            (r'(?<!\d)\d{1,2}(?!\d)', DatePart.number),
        ]

    def _get_age_from_extracted_data(self, data: dict[DatePart, str | None]) -> int | None:
        date = self._parse_date(data[DatePart.date_full], data[DatePart.date_short])
        age = self._calculate_age(
            date,
            data[DatePart.age],
            data[DatePart.year],
            data[DatePart.months],
            data[DatePart.number],
        )

        return age

    def _parse_date(self, date_full: str | None, date_short: str | None) -> datetime | None:
        if date_full:
            return datetime.strptime(date_full, '%d.%m.%Y')
        elif date_short:
            return datetime.strptime(date_short, '%d.%m.%y')
        return None

    def _calculate_age(
        self,
        date: datetime | None,
        age: str | None,
        year: str | None,
        months: str | None,
        number: str | None,
    ) -> int | None:
        if age:
            return int(age)

        if date:
            return relativedelta.relativedelta(datetime.now(), date).years

        if year:
            year_today = datetime.today().year
            age_from_year = year_today - int(year)
            if number and abs(int(number) - age_from_year) in {0, 1}:
                return int(number)
            return age_from_year

        if months:
            return round(int(months) / 12)

        return None
