import re
from datetime import datetime
from re import Match
from typing import Tuple

from dateutil import relativedelta

from .title_commons import Block, PersonGroup, age_wording, check_word_by_natasha


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
        person_reco = PersonGroup()
        # CASE 0. When the whole person is defined as "+N" only (NB – we already cut "+" before)
        case_0 = re.search(
            r'^\W{0,2}\d(?=(\W{0,2}(человека|женщины|мужчины|девочки|мальчика|бабушки|дедушки))?' r'\W{0,4}$)',
            self.name_string,
        )
        if case_0:
            person_reco.num_of_per = int(case_0.group())
            if person_reco.num_of_per == 1:
                person_reco.display_name = 'Человек'
            elif person_reco.num_of_per in {2, 3, 4}:
                person_reco.display_name = f'{person_reco.num_of_per} человека'
            else:
                person_reco.display_name = f'{person_reco.num_of_per} человек'
            person_reco.name = person_reco.display_name

            return person_reco

    def _handle_case_1(self) -> PersonGroup | None:
        person_reco = PersonGroup()

        # CASE 1. When there is only one person like "age" (e.g. "Пропал 10 лет")
        case = re.search(r'^1?\d?\d\W{0,3}(лет|года?)\W{0,2}$', self.name_string)
        if case:
            age = int(re.search(r'\d{1,3}', self.name_string).group())
            person_reco.num_of_per = 1
            person_reco.age = age
            if person_reco.is_child_2():
                person_reco.name = 'Ребёнок'
            else:
                person_reco.name = 'Человек'
            person_reco.display_name = f'{person_reco.name}{age_wording(person_reco.age)}'

            return person_reco

    def _handle_case_2(self) -> PersonGroup | None:
        person_reco = PersonGroup()
        # CASE 2. When the whole person is defined as "+N age, age" only
        case_2 = re.search(
            r'(?i)^\W{0,2}(\d(?!\d)|двое|трое)'
            r'(?=(\W{0,2}(человека|женщины?|мужчины?|девочки|мальчика|бабушки|дедушки))?)',
            self.name_string,
        )
        if not case_2:
            return None

        case_2 = case_2.group()
        if len(case_2) == 1:
            person_reco.num_of_per = int(case_2)
        elif case_2[-4:] == 'двое':
            person_reco.num_of_per = 2
        elif case_2[-4:] == 'трое':
            person_reco.num_of_per = 3

        string_with_ages = self.name_string[re.search(case_2, self.name_string).span()[1] :]
        ages_list = re.findall(r'1?\d?\d(?=\W)', string_with_ages)
        ages_list = [int(x) for x in ages_list]
        if ages_list:
            ages_list.sort()
            person_reco.age_min = int(ages_list[0])
            person_reco.age_max = int(ages_list[-1])

        if person_reco.num_of_per == 1:
            if ages_list and person_reco.is_child():
                person_reco.display_name = 'Ребёнок'
            else:
                person_reco.display_name = 'Человек'
        elif person_reco.num_of_per in {2, 3, 4}:
            if ages_list and person_reco.is_child():
                person_reco.display_name = f'{person_reco.num_of_per} ребёнка'
            else:
                person_reco.display_name = f'{person_reco.num_of_per} человека'
        else:
            if ages_list and person_reco.is_child():
                person_reco.display_name = f'{person_reco.num_of_per} детей'
            else:
                person_reco.display_name = f'{person_reco.num_of_per} человек'

        person_reco.name = person_reco.display_name

        if person_reco.age_min and person_reco.age_max:
            if person_reco.age_min != person_reco.age_max:
                person_reco.display_name = (
                    f'{person_reco.display_name} '
                    f'{person_reco.age_min}–{person_reco.age_max}'
                    f' {age_wording(person_reco.age_max)}'
                )
            else:
                person_reco.display_name = (
                    f'{person_reco.display_name} ' f'{person_reco.age_max}' f' {age_wording(person_reco.age_max)}'
                )

        return person_reco

    def _handle_case_3(self) -> PersonGroup | None:
        person_reco = PersonGroup()
        # CASE 3. When the "person" is defined as plural form  and ages like "people age, age"
        case_3 = re.search(
            r'(?i)(?<!\d)(подростки|дети|люди|мужчины?|женщины?|мальчики|девочки|бабушки|дедушки)' r'\W{0,4}(?=\d)',
            self.name_string,
        )
        if not case_3:
            return None

        case_3 = case_3.group()

        person_reco.num_of_per = -1

        string_with_ages = self.name_string[re.search(case_3, self.name_string).span()[1] :]
        ages_list = re.findall(r'1?\d?\d(?=\W)', string_with_ages)
        if ages_list:
            # TODO fix and merge with similar code
            ages_list.sort()
            person_reco.age_min = int(ages_list[0])
            person_reco.age_max = int(ages_list[-1])

        if person_reco.is_child():
            person_reco.display_name = 'Дети'
        else:
            person_reco.display_name = 'Взрослые'

        person_reco.name = person_reco.display_name

        if person_reco.age_min and person_reco.age_max:
            if person_reco.age_min != person_reco.age_max:
                person_reco.display_name = (
                    f'{person_reco.display_name} '
                    f'{person_reco.age_min}–{person_reco.age_max}'
                    f' {age_wording(person_reco.age_max)}'
                )
            else:
                person_reco.display_name = (
                    f'{person_reco.display_name} ' f'{person_reco.age_max}' f' {age_wording(person_reco.age_max)}'
                )
        return person_reco

    def _handle_case_4(self) -> PersonGroup | None:
        person_reco = PersonGroup()
        # CASE 4. When the whole person is defined as "role" only
        if re.search(
            r'(?i)^(женщина|мужчина|декушка|человек|дочь|сын|жена|муж|отец|мать|папа|мама|'
            r'бабушка|дедушка)(?=\W{0,4}$)',
            self.name_string,
        ):
            person_reco.num_of_per = 1
            person_reco.name = re.search(r'(?i)^\w*(?=\W{0,4}$)', self.name_string).group()
            person_reco.display_name = 'Человек'

            return person_reco

    def _handle_case_5(self) -> PersonGroup:
        # CASE 5. All the other more usual cases
        name_string = self.person.init
        person_reco = PersonGroup()
        person_reco.num_of_per, match = self._define_number_of_persons(name_string)
        self._define_age_of_person(match, name_string, person_reco)
        self._define_age_wording(person_reco)
        self._define_name(match, person_reco)
        self._define_display_name(match, person_reco)
        self._define_number_of_persons_by_natasha(person_reco, name_string)
        return person_reco

    def _define_number_of_persons(self, name_string: str) -> Tuple[int, Match]:
        """Define and return the number of persons out of string input"""

        name_string_end = 'None'
        number_of_persons = None
        block = None

        # language=regexp
        pattern = r'\d{1,4}\W{0,3}(лет|л\.|года?|мес|г)?'
        block_0 = re.search(pattern, name_string)
        if block_0:
            name_string_end = block_0.span()[0]

        if name_string_end != 'None' and int(name_string_end) == 0:
            number_of_persons = 1

        else:
            # language=regexp
            patterns = [
                r'(?i)^\W{0,3}(\d|дв(а|о?е)|тр(ое|и)|чет(веро|ыре))(\W{1,2}'
                r'(человека?|женщин[аы]|мужчин[аы]?|реб[её]нок))?(?!\d)(?!\w)',  # case "2 человека"
                r'(?i)(^|(?<=\W))[\w-]{1,100}(?=\W)',  # regular case
            ]

            for pattern in patterns:
                block = re.search(pattern, name_string)
                if not block:
                    continue
                # language=regexp
                patterns_2 = [
                    [
                        r'(?i)(?<!\w)(человек|женщина|мужчина|реб[её]нок|девочка|мальчик|девушка|'
                        r'мама|папа|сын|дочь|дедушка|бабушка)(?!\w)',
                        1,
                    ],
                    [r'(?i)(?<!\w)дв(а|о?е)(?!\w)', 2],
                    [r'(?i)(?<!\w)(трое|три)(?!\w)', 3],
                    [r'(?i)(?<!\w)чет(веро|ыре)(?!\w)', 4],
                ]
                for pattern_2 in patterns_2:
                    exact_num_of_individuals_in_group = re.search(pattern_2[0], name_string)
                    if exact_num_of_individuals_in_group:
                        number_of_persons = pattern_2[1]
                        break

                break

        if not number_of_persons:
            number_of_persons = -1  # -1 for unrecognized

        return number_of_persons, block

    def _define_age_of_person(self, match: Match, name_string: str, person_reco: PersonGroup) -> None:
        """Define and return the age (given or estimation based on birth year) for a person"""

        age = None
        year = None
        months = None
        date = None
        date_full = None
        date_short = None
        number = None

        age_string_start = match.span()[1] if match else 0

        # language=regexp
        patterns = [
            [r'\d{2}.\d{2}\.\d{4}', 'date_full'],
            [r'\d{2}.\d{2}\.\d{2}(?!\d)', 'date_short'],
            [r'(?<!\d)\d{1,2}(?=\W{0,2}мес(\W|яц))', 'age_months'],
            [r'(?<!\d)1?\d{1,2}(?!(\W{0,2}мес|\W{0,3}\d))', 'age'],
            [r'(?<!\d)\d{4}', 'year'],
            [r'(?<!\d)\d{1,2}(?!\d)', 'number'],
        ]

        for pattern in patterns:
            block_2 = re.search(pattern[0], name_string[age_string_start:])
            if block_2:
                person_reco.num_of_per = 1
                pattern_type = pattern[1]
                found_value = block_2.group()

                if pattern_type == 'age_months':
                    months = found_value
                if pattern_type == 'date_full':
                    date_full = found_value
                elif pattern_type == 'date_short':
                    date_short = found_value
                elif pattern_type == 'age':
                    age = found_value
                elif pattern_type == 'year':
                    year = found_value
                elif pattern_type == 'number':
                    number = found_value

        if date_full:
            date = datetime.strptime(date_full, '%d.%m.%Y')
        elif date_short:
            date = datetime.strptime(date_short, '%d.%m.%y')

        if not age and date:
            age = relativedelta.relativedelta(datetime.now(), date).years

        elif not age and year:
            year_today = datetime.today().year
            age_from_year = year_today - int(year)
            # if there's an indication of the age without explicit "years", but just a number, e.g. 57
            if number and abs(int(number) - age_from_year) in {0, 1}:
                age = number
            else:
                age = age_from_year

        elif months and not age and not year:
            age = round(int(months) / 12)

        if age:
            person_reco.age = int(age)

    def _define_age_wording(self, person_reco: PersonGroup) -> None:
        if person_reco.age:
            person_reco.age_wording = f'{str(person_reco.age)} {age_wording(person_reco.age)}'

        if person_reco.age_wording:
            person_reco.age_wording = f' {person_reco.age_wording}'
        else:
            person_reco.age_wording = ''

    def _define_name(self, match: Match, person_reco: PersonGroup) -> None:
        if match:
            person_reco.name = match.group()
        else:
            if person_reco.is_child_2():
                person_reco.name = 'Ребёнок'
            else:
                person_reco.name = 'Человек'

    def _define_display_name(self, match: Match, person_reco: PersonGroup) -> None:
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
