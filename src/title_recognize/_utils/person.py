import re
from datetime import datetime
from re import Match
from typing import Tuple

from dateutil import relativedelta

from .title_commons import Block, PersonGroup, TitleRecognition, age_wording, check_word_by_natasha


def _define_number_of_persons(name_string: str) -> Tuple[int, Match]:
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


def _define_age_of_person(block: Match, name_string: str, person_reco: PersonGroup) -> PersonGroup:
    """Define and return the age (given or estimation based on birth year) for a person"""

    age = None
    year = None
    months = None
    date = None
    date_full = None
    date_short = None
    number = None

    age_string_start = block.span()[1] if block else 0

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
            if pattern[1] == 'age_months':
                months = block_2.group()
            if pattern[1] == 'date_full':
                date_full = block_2.group()
            elif pattern[1] == 'date_short':
                date_short = block_2.group()
            elif pattern[1] == 'age':
                age = block_2.group()
            elif pattern[1] == 'year':
                year = block_2.group()
            elif pattern[1] == 'number':
                number = block_2.group()

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
        person_reco.age_wording = f'{str(person_reco.age)} {age_wording(person_reco.age)}'

    if person_reco.age_wording:
        person_reco.age_wording = f' {person_reco.age_wording}'
    else:
        person_reco.age_wording = ''

    return person_reco


def _define_display_name(block: Match, person_reco: PersonGroup) -> PersonGroup:
    """Define and record the name / pseudonym that will be displayed to users"""

    # DISPLAY NAME (PSEUDONYM) IDENTIFICATION
    if block:
        person_reco.name = block.group()
    else:
        if person_reco.age and int(person_reco.age) < 18:
            person_reco.name = 'Ребёнок'
        else:
            person_reco.name = 'Человек'

    display_name = f'{person_reco.name}{person_reco.age_wording}'
    person_reco.display_name = display_name.capitalize()

    # case of two-word last names like Tom-Scott. in this case capitalize killed capital S, and we restore it
    dashes_in_names = re.search(r'\w-\w', person_reco.display_name)
    if dashes_in_names:
        letter_to_up = dashes_in_names.span()[0] + 2
        d = person_reco.display_name
        person_reco.display_name = f'{d[:letter_to_up]}{d[letter_to_up].capitalize()}{d[letter_to_up + 1:]}'

    return person_reco


def _define_age_of_person_by_natasha(person_reco: PersonGroup, name_string: str) -> PersonGroup:
    """Define and return the age for a person if the predecessor symbols are recognized as Person by Natasha"""

    # last chance to define number of persons in group - with help of Natasha
    if person_reco.num_of_per == -1:
        # language=regexp
        patterns = [r'^\D*\w(?=\W{1,3}\d)', r'^\D*\w(?=\W{1,3}$)']

        for pattern in patterns:
            block_2 = re.search(pattern, name_string)

            if block_2:
                name_string_is_a_name = check_word_by_natasha(block_2.group(), 'per')
                if name_string_is_a_name:
                    person_reco.num_of_per = 1
                    break

    return person_reco


def recognize_one_person_group(person: Block) -> PersonGroup:
    """Recognize the Displayed Name (Pseudonym) for a SINGLE person/group as well as age"""

    person_reco = PersonGroup(block_num=person.type[1])
    name_string = person.init

    # CASE 0. When the whole person is defined as "+N" only (NB – we already cut "+" before)
    case_0 = re.search(
        r'^\W{0,2}\d(?=(\W{0,2}(человека|женщины|мужчины|девочки|мальчика|бабушки|дедушки))?' r'\W{0,4}$)',
        name_string,
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

    # CASE 1. When there is only one person like "age" (e.g. "Пропал 10 лет")
    case = re.search(r'^1?\d?\d\W{0,3}(лет|года?)\W{0,2}$', name_string)
    if case:
        age = int(re.search(r'\d{1,3}', name_string).group())
        person_reco.num_of_per = 1
        person_reco.age = age
        if person_reco.age < 18:
            person_reco.name = 'Ребёнок'
        else:
            person_reco.name = 'Человек'
        person_reco.display_name = f'{person_reco.name}{age_wording(person_reco.age)}'

        return person_reco

    # CASE 2. When the whole person is defined as "+N age, age" only
    case_2 = re.search(
        r'(?i)^\W{0,2}(\d(?!\d)|двое|трое)'
        r'(?=(\W{0,2}(человека|женщины?|мужчины?|девочки|мальчика|бабушки|дедушки))?)',
        name_string,
    )
    if case_2:
        case_2 = case_2.group()
        if len(case_2) == 1:
            person_reco.num_of_per = int(case_2)
        elif case_2[-4:] == 'двое':
            person_reco.num_of_per = 2
        elif case_2[-4:] == 'трое':
            person_reco.num_of_per = 3

        string_with_ages = name_string[re.search(case_2, name_string).span()[1] :]
        ages_list = re.findall(r'1?\d?\d(?=\W)', string_with_ages)
        ages_list = [int(x) for x in ages_list]
        if ages_list:
            ages_list.sort()
            person_reco.age_min = int(ages_list[0])
            person_reco.age_max = int(ages_list[-1])

        if person_reco.num_of_per == 1:
            if ages_list and person_reco.age_max < 18:
                person_reco.display_name = 'Ребёнок'
            else:
                person_reco.display_name = 'Человек'
        elif person_reco.num_of_per in {2, 3, 4}:
            if ages_list and person_reco.age_max < 18:
                person_reco.display_name = f'{person_reco.num_of_per} ребёнка'
            else:
                person_reco.display_name = f'{person_reco.num_of_per} человека'
        else:
            if ages_list and person_reco.age_max < 18:
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

    # CASE 3. When the "person" is defined as plural form  and ages like "people age, age"
    case_3 = re.search(
        r'(?i)(?<!\d)(подростки|дети|люди|мужчины?|женщины?|мальчики|девочки|бабушки|дедушки)' r'\W{0,4}(?=\d)',
        name_string,
    )
    if case_3:
        case_3 = case_3.group()

        person_reco.num_of_per = -1

        string_with_ages = name_string[re.search(case_3, name_string).span()[1] :]
        ages_list = re.findall(r'1?\d?\d(?=\W)', string_with_ages)
        if ages_list:
            ages_list.sort()
            person_reco.age_min = int(ages_list[0])
            person_reco.age_max = int(ages_list[-1])

        if person_reco.age_max < 18:
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

    # CASE 4. When the whole person is defined as "role" only
    if re.search(
        r'(?i)^(женщина|мужчина|декушка|человек|дочь|сын|жена|муж|отец|мать|папа|мама|' r'бабушка|дедушка)(?=\W{0,4}$)',
        name_string,
    ):
        person_reco.num_of_per = 1
        person_reco.name = re.search(r'(?i)^\w*(?=\W{0,4}$)', name_string).group()
        person_reco.display_name = 'Человек'

        return person_reco

    # CASE 5. All the other more usual cases
    person_reco.num_of_per, block = _define_number_of_persons(name_string)
    person_reco = _define_age_of_person(block, name_string, person_reco)
    person_reco = _define_display_name(block, person_reco)
    person_reco = _define_age_of_person_by_natasha(person_reco, name_string)

    return person_reco


def define_person_display_name_and_age(curr_recognition: TitleRecognition) -> TitleRecognition:
    """Recognize the Displayed Name (Pseudonym) for ALL person/groups as well as ages"""
    for person_block in curr_recognition.groups:
        if person_block.is_person():
            person_block.reco = recognize_one_person_group(person_block)

    return curr_recognition


class PersonRecognizer:
    pass
