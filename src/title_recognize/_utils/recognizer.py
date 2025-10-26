import logging
import re
from typing import Any, Dict, Optional, Union

from pydantic import ConfigDict, ValidationError

from _dependencies.recognition_schema import Location, Person, PersonsSummary, RecognitionResult, RecognitionTopicType

from .pattern_collections import BlockTypePatternCollection, get_mistype_patterns
from .person import recognize_one_person_group
from .title_commons import (
    Block,
    BlockType,
    PersonGroup,
    PersonGroupSummary,
    TitleRecognition,
    age_wording,
)
from .tokenizer import Tokenizer


class TitleRecognizer:
    def __init__(self, recognition: TitleRecognition) -> None:
        self.recognition = recognition

    def _calculate_activity(self) -> str | None:
        for block in self.recognition.blocks:
            if block.activity and not self.recognition.act:
                return block.activity

        for block in self.recognition.blocks:
            if block.type == BlockType.ACT:
                return block.reco

        return None

    def _get_first_group_with_name(self) -> PersonGroup | None:
        for group in self.recognition.person_groups:
            return group
        return None

    def _define_person_block_display_name_and_age_range(self) -> None:
        """Define the Displayed Name (Pseudonym) and Age Range for the whole Persons Block"""

        persons_recognized = any(block.is_person() for block in self.recognition.blocks)
        if not persons_recognized:
            return

        # level of PERSON BLOCKS (likely to be only one for each title)
        # for block in person_blocks:
        age_list = self._get_ages_list()
        group_with_name = self.recognition.person_groups[0]
        final_num_of_pers = self._define_final_number_of_persons()

        person_group = PersonGroupSummary(
            name=group_with_name.name,
            block_num=final_num_of_pers,
            age=self._get_final_age(age_list),
            age_wording=self._get_final_age_wording(age_list),
        )

        # go to the level of PERSON GROUPS (subgroup in person block)
        final_pseudonym = self._define_final_pseudonym(final_num_of_pers, person_group, group_with_name)
        person_group.display_name = final_pseudonym.capitalize()

        self.recognition.person_groups_summary = person_group

    def _define_final_pseudonym(
        self,
        final_num_of_pers: int,
        person_group: PersonGroupSummary,
        group_with_name: PersonGroup | None,
    ) -> str:
        final_pseudonym = ''
        if group_with_name:
            # STEP 2. Define the pseudonym for the person / group
            if group_with_name.num_of_per > 1:
                final_pseudonym = group_with_name.display_name
            else:
                final_pseudonym = group_with_name.name

        persons_groups = self.recognition.person_groups
        num_of_per_groups = len(persons_groups)

        final_age_words = f' {person_group.age_wording}' if person_group.age_wording else ''
        if final_pseudonym and final_num_of_pers == 1:
            return f'{final_pseudonym}{final_age_words}'

        if final_pseudonym and final_num_of_pers > 1:
            if final_pseudonym in {'дети', 'люди', 'подростки'}:
                return f'{final_pseudonym}{final_age_words}'

            if num_of_per_groups == 1:
                if not person_group.age:  # added due to 5052
                    return person_group.name
                return final_pseudonym

            first_group_num_of_pers = persons_groups[0].num_of_per if persons_groups else 0
            return f'{final_pseudonym} + {final_num_of_pers - first_group_num_of_pers} ' f'чел.{final_age_words}'

        if final_pseudonym and num_of_per_groups == 1 and final_num_of_pers == -1:
            return f'{final_pseudonym}{final_age_words}'

        return f'{final_pseudonym} и Ко.{final_age_words}'

    def _define_final_number_of_persons(self) -> int:
        numbers_of_persons_in_blocks = [group.num_of_per for group in self.recognition.person_groups]
        if any([not isinstance(x, int) or x <= 0 for x in numbers_of_persons_in_blocks]):
            # if persons count in any of blocks is unrecognized, set overall count of persons to -1
            return -1
        return sum([x for x in numbers_of_persons_in_blocks if isinstance(x, int)])

    def _get_final_age_wording(self, age_list: list[int]) -> str | None:
        if not age_list:
            return None

        if min(age_list) != max(age_list):
            return f'{min(age_list)}–{max(age_list)} {age_wording(max(age_list))}'

        return f'{max(age_list)} {age_wording(max(age_list))}'

    def _get_final_age(self, age_list: list[int]) -> int | list[int]:
        if age_list and len(age_list) > 1:
            return age_list
        elif age_list and len(age_list) == 1:
            return age_list[0]
        else:
            return []

    def _get_ages_list(self) -> list[int]:
        age_list = []
        for person_group in self.recognition.person_groups:
            if person_group.age or person_group.age == 0:
                age_list.append(person_group.age)
            if person_group.age_min:
                age_list.append(person_group.age_min)
            if person_group.age_max:
                age_list.append(person_group.age_max)
        age_list = list(set(age_list))
        age_list.sort()
        return age_list

    def _prettify_loc_group_address(self) -> None:
        """Prettify (delete unneeded symbols) every location address"""

        unneed_symbols_pattern = r'[,!?\s\-–—]{1,5}$'
        for block in self.recognition.groups:
            if block.is_location():
                block.reco = re.sub(unneed_symbols_pattern, '', block.init)

    def _define_general_status(self) -> str | None:
        """In rare cases searches have 2 statuses: or by mistake or due to differences between lost persons' statues"""

        statuses_list = [
            (j, block.reco) for j, block in enumerate(self.recognition.groups) if block.type == BlockType.ST
        ]

        # if status is the only one (which is true in 99% of cases)
        if len(statuses_list) == 1:
            return statuses_list[0][1]

        # if there are more than 1 status. have never seen 3, so stopping on 2
        elif len(statuses_list) > 1:
            # if statuses goes one-just-after-another --> it means a mistake. Likely 1st status is correct
            if statuses_list[1][0] - statuses_list[0][0] == 1:
                return statuses_list[0][1]

            # if there's another block between status blocks – which is not mistake, but just a rare case
            else:
                if statuses_list[0][1] == statuses_list[1][1]:
                    return statuses_list[0][1]
                else:
                    return f'{statuses_list[0][1]} и {statuses_list[1][1]}'
        return None

    def _calculate_total_num_of_persons(self) -> str | int | None:
        """Define the Total number of persons to search"""

        if self.recognition.act != 'search':
            return None

        per_blocks_says = self._per_blocks_says()

        status_says_only_one_person = self._status_says_only_one_person()

        # total_num_of_persons can be: [1-9] / 'group' / 'unidentified'
        if per_blocks_says == 'unidentified':
            if status_says_only_one_person == True:  # noqa – intentively to highlight that it is not False / None
                return 1
            elif status_says_only_one_person == False:  # noqa – to aviod case of 'None'
                return 'group'
            else:
                return 'unidentified'
        else:
            return per_blocks_says

    def _per_blocks_says(self) -> str | int:
        persons_count_list = [
            block.num_of_per for block in self.recognition.person_groups if block.num_of_per is not None
        ]

        # per_blocks_says can be: [1-9] / 'group' / 'unidentified'
        if not persons_count_list:
            return 'unidentified'
        else:
            if min(persons_count_list) == -1 and len(persons_count_list) > 1:
                return 'group'
            elif min(persons_count_list) == -1 and len(persons_count_list) == 1:
                return 'unidentified'
            else:  # that means = min(pers_list) > -1:
                return sum(persons_count_list)

    def _status_says_only_one_person(self) -> bool | None:
        patterns: list[tuple[str, bool]] = [
            (r'(?i)пропала?(?!и)', True),
            (r'(?i)пропали', False),
            (r'(?i)ппохищена?(?!ы)', True),  # seems like mistype
            (r'(?i)похищена?(?!ы)', True),
            (r'(?i)похищены', False),
            (r'(?i)найдена?(?!ы)', True),
            (r'(?i)найдены', False),
            (r'(?i)жива?(?!ы)', True),
            (r'(?i)живы', False),
            (r'(?i)погиб(ла)?(?!ли)', True),
            (r'(?i)погибли', False),
        ]

        for block in self.recognition.blocks:
            if block.type != BlockType.ST:
                continue
            for pattern, is_one_person in patterns:
                match = re.search(pattern, block.init)
                if match:
                    # as per statistics of 27k cases these was no single case when
                    # there were two contradictory statuses
                    return is_one_person
        return None

    def generate_final_reco_dict(self) -> RecognitionResult:
        """Generate the final outcome dictionary for recognized title"""

        recognition = self.recognition

        result = RecognitionResult(
            avia=True if recognition.is_avia else None,
            status=recognition.st,
            topic_type=RecognitionTopicType(self._get_final_topic_type()),
            persons=self._get_result_persons_summary(),
            locations=self._get_final_locations() or None,
        )

        # placeholders if no persons
        if (
            result.topic_type in {RecognitionTopicType.search, RecognitionTopicType.search_training}
            and not result.persons
        ):
            persons_summary_placeholder = PersonsSummary(
                total_persons=-1,
                total_name='Неизвестный',
                total_display_name='Неизвестный',
            )
            result.persons = persons_summary_placeholder

        if result.persons and result.persons.total_persons == -1 and recognition.per_num == 1:
            result.persons.total_persons = 1

        return result

    def _get_final_topic_type(self) -> str:
        if self.recognition.is_training:
            return RecognitionTopicType.search_training

        for block in self.recognition.groups[::-1]:
            if block.type == 'ACT':
                return block.reco or ''

        if self.recognition.act:
            return self.recognition.act

        return RecognitionTopicType.unrecognized

    def _patch_recognition_act_and_st(self) -> None:
        """maybe it can be moved somewhere else"""
        recognition = self.recognition
        recognition.st = self._define_general_status()
        if recognition.st:
            return

        persons_identified = bool(recognition.person_groups_summary)

        if not recognition.act and persons_identified:
            recognition.act = 'search'
            recognition.st = 'Ищем'
            # FIXME - 07.11.2023 – for status_only debug
            logging.info(f'2 RECO ST: {recognition.st}')
            # FIXME ^^^

        if recognition.is_training:
            # default status for "search training"
            recognition.st = 'Ищем'

    def _get_final_locations(self) -> list[Location]:
        return [Location(address=block.reco) for block in self.recognition.groups if block.is_location() and block.reco]

    def _get_result_persons_summary(self) -> PersonsSummary | None:
        persons: list[Person] = []
        for person_group in self.recognition.person_groups:  # from GROUPS!
            person_model = Person(
                name=person_group.name,
                age=person_group.age or None,
                age_min=person_group.age_min or None,
                age_max=person_group.age_max or None,
                display_name=person_group.display_name,
                number_of_persons=person_group.num_of_per,
            )
            persons.append(person_model)

        if not persons:
            return None

        if not self.recognition.person_groups_summary:
            return None

        person_group_summary = self.recognition.person_groups_summary  # from BLOCKS!
        summary = PersonsSummary(
            total_persons=person_group_summary.block_num,
            total_name=person_group_summary.name,
            total_display_name=person_group_summary.display_name or '',
            person=persons,
        )

        if isinstance(person_group_summary.age, list) and len(person_group_summary.age) > 0:
            summary.age_min = person_group_summary.age[0]
            summary.age_max = person_group_summary.age[-1]
        elif isinstance(person_group_summary.age, int):
            summary.age_min = person_group_summary.age
            summary.age_max = person_group_summary.age

        return summary

    def _define_person_display_name_and_age(self) -> None:
        """Recognize the Displayed Name (Pseudonym) for ALL person/groups as well as ages"""
        person_groups = [block for block in self.recognition.groups if block.is_person()]
        for person_block in person_groups:
            self.recognition.person_groups.append(recognize_one_person_group(person_block))


def recognize_title(line: str, reco_type: str | None) -> Union[Dict, None]:
    """Recognize LA Thread Subject (Title) and return a dict of recognized parameters"""

    prettified_line = clean_and_prettify_initial_text(line)

    if is_spam_message(prettified_line.lower()):
        final_recognition = RecognitionResult(
            topic_type=RecognitionTopicType.unrecognized,
        )
        return final_recognition.model_dump(exclude_none=True)

    recognition = TitleRecognition(_initial_text=line, _pretty=prettified_line)
    recognition.blocks = Tokenizer(pretty_text=prettified_line).split_text_to_blocks()
    recognition.groups = split_blocks_to_groups(recognition.blocks)

    recognizer = TitleRecognizer(recognition=recognition)
    recognition.act = recognizer._calculate_activity()  # TODO ??
    recognizer._define_person_display_name_and_age()
    recognizer._define_person_block_display_name_and_age_range()
    recognizer._patch_recognition_act_and_st()

    if reco_type != 'status_only':
        # TODO we can always return full data. Methods below are cheap.
        recognizer._prettify_loc_group_address()
        recognizer.recognition.per_num = recognizer._calculate_total_num_of_persons()

    final_recognition = recognizer.generate_final_reco_dict()

    final_dict = final_recognition.model_dump(exclude_none=True)
    _temp_patch_result(final_recognition, final_dict)

    return final_dict


def is_spam_message(prettified_line: str) -> bool:
    cases = (
        '[kkК][rрpР][аaА][kkК][еeЕ][nhнН]'.lower(),
        r'https:\/\/.+\.top',
        r'https:\/\/.+\.shop',
        r'https:\/\/.+\.biz',
        r'https:\/\/krak.+\.',
        r'CASINÒ'.lower(),
        r'CASINÓ'.lower(),
    )
    re_patterns = [re.compile(x) for x in cases]

    prettified_line = prettified_line.lower()
    replaces = '*@-_'
    for replace in replaces:
        prettified_line = prettified_line.replace(replace, '')

    if any(pattern.search(prettified_line) for pattern in re_patterns):
        return True

    keywords_combinations = [
        ['браузер', 'tor', 'vpn'],
        ['онлайн', 'top', 'сайт'],
    ]
    for combination in keywords_combinations:
        if all((x in prettified_line) for x in combination):
            return True

    return False


def _temp_patch_result(final_recognition: RecognitionResult, final_dict: dict) -> None:
    # temporary patch for equality with result of old algorithm
    if (
        final_recognition.topic_type not in (RecognitionTopicType.unrecognized, RecognitionTopicType.search_training)
        and final_recognition.persons
    ):
        if not final_recognition.persons.age_min:
            final_dict['persons']['age_min'] = None
        if not final_recognition.persons.age_max:
            final_dict['persons']['age_max'] = None
    if final_recognition.topic_type == RecognitionTopicType.search_training and final_recognition.persons:
        # another patch
        if not final_recognition.persons.person:
            del final_dict['persons']['person']
        else:
            if not final_recognition.persons.age_min:
                final_dict['persons']['age_min'] = None
            if not final_recognition.persons.age_max:
                final_dict['persons']['age_max'] = None


def clean_and_prettify_initial_text(string: str) -> str:
    """Convert a string with known mistypes to the prettified view"""

    patterns = get_mistype_patterns()

    for pattern in patterns:
        string = re.sub(pattern[0], pattern[1], string)

    return string


def split_blocks_to_groups(blocks: list[Block]) -> list[Block]:
    """Split the recognized Block with aggregated persons/locations to separate Groups of individuals/addresses"""

    result_groups: list[Block] = []
    for block in blocks:
        if not block.is_person() and not block.is_location():
            result_groups.append(block)  # as is
            continue

        individual_stops = []

        if block.is_person():
            patterns = BlockTypePatternCollection.get_person_by_individual_patterns()
        elif block.is_location():
            patterns = BlockTypePatternCollection.get_location_by_individual_patterns()

        for pattern in patterns:
            string_to_split = block.init
            delimiters_list = re.finditer(pattern, string_to_split)

            if not delimiters_list:
                continue

            for delimiters_line in delimiters_list:
                if delimiters_line.span()[1] != len(string_to_split):
                    individual_stops.append(delimiters_line.span()[1])

        individual_stops.extend([0, len(string_to_split)])  # add begin and end anyway
        individual_stops = list(set(individual_stops))
        individual_stops.sort()

        for i in range(len(individual_stops) - 1):
            block_start, block_end = individual_stops[i], individual_stops[i + 1]
            result_groups.append(
                Block(
                    init=string_to_split[block_start:block_end],
                    type=block.type,
                )
            )
    return result_groups
