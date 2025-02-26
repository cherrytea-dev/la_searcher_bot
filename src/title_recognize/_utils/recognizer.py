import logging
import re
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .person import recognize_one_person_group
from .title_commons import (
    Block,
    BlockType,
    PersonGroup,
    TitleRecognition,
    TopicType,
    age_wording,
)
from .tokenizer import Tokenizer


class Person(BaseModel):
    name: str = Field(description='One-word description')
    age: Optional[int] = Field(None, ge=0, le=199, description='Age in years')
    age_min: Optional[int] = Field(None, ge=0, le=199, description='Minimum age in years')
    age_max: Optional[int] = Field(None, ge=0, le=199, description='Maximum age in years')
    display_name: str = Field(description='Display name + age')
    number_of_persons: int = Field(..., ge=-1, le=9, description='Number of persons in this group, -1 or 1-9')


class Persons(BaseModel):
    total_persons: Union[int, str] = Field(..., description="Total number of persons: 1-9, 'group', or 'undefined'")
    age_min: Optional[int] = Field(None, ge=0, le=199, description='Minimum age across all persons')
    age_max: Optional[int] = Field(None, ge=0, le=199, description='Maximum age across all persons')
    total_name: str = Field(description='Name of the first person')
    total_display_name: str = Field(description='Display name + age (age range)')
    person: List[Person] = Field(default_factory=list)


class Location(BaseModel):
    address: str


class RecognitionResult(BaseModel):
    topic_type: TopicType
    avia: Optional[bool] = Field(None, description='Only for search')
    status: Optional[str] = Field(None, description='Only for search / search reverse')
    persons: Optional[Persons] = Field(None, description='Only for search')
    locations: Optional[List[Location]] = Field(None, description='Only for search')


class TitleRecognizer:
    def __init__(self, recognition: TitleRecognition) -> None:
        self.recognition = recognition

    def _calculate_activity(self) -> None:
        for block in self.recognition.blocks:
            if block.activity and not self.recognition.act:
                self.recognition.act = block.activity
                break

        for block in self.recognition.blocks:
            # TODO very similar with upper code block
            # maybe can be removed, tests are green
            if block.type == BlockType.ACT:
                self.recognition.act = block.reco
            # MEMO: recognition.st is done on the later stages of title recognition

    def _define_person_block_display_name_and_age_range(self) -> None:
        """Define the Displayed Name (Pseudonym) and Age Range for the whole Persons Block"""

        persons_blocks = [x for x in self.recognition.blocks if x.is_person()]
        persons_groups = [x for x in self.recognition.groups if x.is_person()]

        # level of PERSON BLOCKS (likely to be only one for each title)

        for block in persons_blocks:
            block.reco = PersonGroup()
            final_num_of_pers = 0
            num_of_groups_in_block = 0
            final_pseudonym = ''
            first_group_num_of_pers = None

            # go to the level of PERSON GROUPS (subgroup in person block)
            for group in persons_groups:
                num_of_groups_in_block += 1

                # STEP 1. Define the number of persons for search
                num_of_persons = group.reco.num_of_per
                if not first_group_num_of_pers:
                    first_group_num_of_pers = num_of_persons

                if isinstance(num_of_persons, int) and num_of_persons > 0 and final_num_of_pers != -1:
                    # -1 stands for unrecognized number of people
                    final_num_of_pers += num_of_persons
                else:
                    final_num_of_pers = -1  # -1 stands for unrecognized number of people

                # STEP 2. Define the pseudonym for the person / group
                if group.reco.name:
                    if not final_pseudonym:
                        if num_of_persons > 1:
                            final_pseudonym = group.reco.display_name
                        else:
                            final_pseudonym = group.reco.name
                        block.reco.name = group.reco.name

            self._process_age(persons_groups, block)

            if block.reco.age_wording:
                final_age_words = f' {block.reco.age_wording}'
            else:
                final_age_words = ''

            num_of_per_blocks = len(persons_blocks)
            num_of_per_groups = len(persons_groups)
            if final_pseudonym and final_num_of_pers == 1:
                final_pseudonym = f'{final_pseudonym}{final_age_words}'
            elif final_pseudonym and final_num_of_pers > 1:
                if final_pseudonym in {'дети', 'люди', 'подростки'}:
                    final_pseudonym = f'{final_pseudonym}{final_age_words}'
                elif num_of_per_blocks == 1 and num_of_per_groups == 1:
                    if not block.reco.age:  # added due to 5052
                        final_pseudonym = block.reco.name
                else:
                    final_pseudonym = (
                        f'{final_pseudonym} + {final_num_of_pers - first_group_num_of_pers} ' f'чел.{final_age_words}'
                    )
            elif final_pseudonym and num_of_groups_in_block == 1 and final_num_of_pers == -1:
                final_pseudonym = f'{final_pseudonym}{final_age_words}'
            else:
                final_pseudonym = f'{final_pseudonym} и Ко.{final_age_words}'

            block.reco.display_name = final_pseudonym.capitalize()
            block.reco.block_num = final_num_of_pers

    def _process_age(self, persons_groups: list[Block], block: Block) -> None:
        age_list = []
        for group in persons_groups:
            if group.reco.age or group.reco.age == 0:
                age_list.append(group.reco.age)
            if group.reco.age_min:
                age_list.append(group.reco.age_min)
            if group.reco.age_max:
                age_list.append(group.reco.age_max)

        if age_list and len(age_list) > 1:
            age_list.sort()
            final_age = age_list
            if min(age_list) != max(age_list):
                final_age_wording = f'{min(age_list)}–{max(age_list)} {age_wording(max(age_list))}'
            else:
                final_age_wording = f'{max(age_list)} {age_wording(max(age_list))}'

        elif age_list and len(age_list) == 1:
            final_age = age_list[0]
            final_age_wording = f'{age_list[0]} {age_wording(age_list[0])}'
        else:
            final_age = []
            final_age_wording = None

        block.reco.age = final_age
        block.reco.age_wording = final_age_wording

    def _prettify_loc_group_address(self) -> None:
        """Prettify (delete unneeded symbols) every location address"""

        unneed_symbols_pattern = r'[,!?\s\-–—]{1,5}$'
        for block in self.recognition.groups:
            if block.is_location():
                block.reco = re.sub(unneed_symbols_pattern, '', block.init)

    def _define_loc_block_summary(self) -> None:
        """For Debug and not for real prod use. Define the cumulative location string based on addresses"""

        # level of PERSON BLOCKS (should be only one for each title)
        for block in self.recognition.blocks:
            if not block.is_location():
                return
            block.reco = ''

            # go to the level of LOCATION GROUPS (subgroup in locations block)
            for individual_block in self.recognition.groups:
                if individual_block.is_location():
                    block.reco += f', {individual_block.reco}'

            if block.reco:
                block.reco = block.reco[2:]

    def _define_general_status(self) -> str:
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
        persons_count_list = [block.reco.num_of_per for block in self.recognition.groups if block.is_person()]

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
        patterns = [
            [r'(?i)пропала?(?!и)', True],
            [r'(?i)пропали', False],
            [r'(?i)ппохищена?(?!ы)', True],  # seems like mistype
            [r'(?i)похищена?(?!ы)', True],
            [r'(?i)похищены', False],
            [r'(?i)найдена?(?!ы)', True],
            [r'(?i)найдены', False],
            [r'(?i)жива?(?!ы)', True],
            [r'(?i)живы', False],
            [r'(?i)погиб(ла)?(?!ли)', True],
            [r'(?i)погибли', False],
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
        final_dict = {}

        """
        SCHEMA:
        {topic_type = search / search reverse / search patrol / search training / event / info,
        [optional, only for search] avia = True / False,
        [optional, only for search / search reverse] status,
        [optional, only for search] persons =
            {
            total_persons = [1-9] / group / undefined
            age_min = [0-199]
            age_max = [0-199]
            total_name = name of the first person
            total_display_name = display name + age (age range)
            person =
                [
                [optional] person =
                    {
                    name = one-word description,
                    [optional] age = [0-199] in years,
                    [optional] age_min = [0-199] in years,
                    [optional] age_max = [0-199] in years,
                    display_name = display name + age,
                    number_of_persons = -1 or [1-9] (only in this group of persons)
                    }
                ]
            }
        [optional, only for search] locations =
            [
                {
                address = string
                }
            ]
        }
        """

        result = RecognitionResult.model_construct()
        persons_identified = any(True for block in recognition.blocks if block.type == 'PER')

        if not recognition.act and not recognition.st and persons_identified:
            recognition.act = 'search'
            recognition.st = 'Ищем'
            # FIXME - 07.11.2023 – for status_only debug
            logging.info(f'2 RECO ST: {recognition.st}')
            # FIXME ^^^

        if recognition.act and not recognition.st and recognition.tr:
            recognition.st = 'Ищем'

        if recognition.act:
            result.topic_type = recognition.act

        if recognition.avia:
            final_dict['avia'] = True

        if recognition.st:
            final_dict['status'] = recognition.st

        persons = []
        locations = []
        for block in recognition.groups:
            if block.type == 'ACT':
                result.topic_type = block.reco

            elif block.is_person():
                individual_dict = {}
                if block.reco.name:
                    individual_dict['name'] = block.reco.name
                if block.reco.age:
                    individual_dict['age'] = block.reco.age
                if block.reco.age_min:
                    individual_dict['age_min'] = block.reco.age_min
                if block.reco.age_max:
                    individual_dict['age_max'] = block.reco.age_max
                if block.reco.display_name:
                    individual_dict['display_name'] = block.reco.display_name
                if block.reco.num_of_per:
                    individual_dict['number_of_persons'] = block.reco.num_of_per
                if individual_dict:
                    persons.append(individual_dict)

            elif block.is_location():
                individual_dict = {}
                if block.reco:
                    individual_dict['address'] = block.reco
                if individual_dict:
                    locations.append(individual_dict)

        if recognition.tr:
            result.topic_type = 'search training'

        self._fill_result_persons(final_dict, persons)

        if locations:
            final_dict['locations'] = locations

        # placeholders if no persons
        if result.topic_type in {'search', 'search training'} and 'persons' not in final_dict.keys():
            per_dict = {'total_persons': -1, 'total_name': 'Неизвестный', 'total_display_name': 'Неизвестный'}
            final_dict['persons'] = per_dict

        if (
            'persons' in final_dict.keys()
            and 'total_persons' in final_dict['persons'].keys()
            and final_dict['persons']['total_persons'] == -1
            and recognition.per_num == 1
        ):
            final_dict['persons']['total_persons'] = 1

        final_dict['topic_type'] = result.topic_type
        result = RecognitionResult.model_validate(final_dict)
        # result.model_validate(**result)
        return result

    def _fill_result_persons(self, final_dict: dict, persons: list[dict]) -> None:
        if not persons:
            return
        summary = {}
        for block in self.recognition.blocks:
            if block.type and block.type == 'PER':
                summary['total_persons'] = block.reco.block_num
                summary['total_name'] = block.reco.name
                summary['total_display_name'] = block.reco.display_name
                if isinstance(block.reco.age, list) and len(block.reco.age) > 0:
                    summary['age_min'] = block.reco.age[0]
                    summary['age_max'] = block.reco.age[-1]
                elif isinstance(block.reco.age, list):
                    summary['age_min'] = None
                    summary['age_max'] = None
                else:
                    summary['age_min'] = block.reco.age
                    summary['age_max'] = block.reco.age
                break

        summary['person'] = persons
        final_dict['persons'] = summary

    def _define_person_display_name_and_age(self) -> None:
        """Recognize the Displayed Name (Pseudonym) for ALL person/groups as well as ages"""
        for person_block in self.recognition.groups:
            if person_block.is_person():
                person_block.reco = recognize_one_person_group(person_block)


def recognize_title(line: str, reco_type: str) -> Union[Dict, None]:
    """Recognize LA Thread Subject (Title) and return a dict of recognized parameters"""

    recognition = Tokenizer.get_recognition_from_str(line)

    recognizer = TitleRecognizer(recognition=recognition)
    recognizer._calculate_activity()  # TODO ??
    recognizer._define_person_display_name_and_age()
    recognizer._define_person_block_display_name_and_age_range()
    recognizer.recognition.st = recognizer._define_general_status()

    if reco_type != 'status_only':
        recognizer._prettify_loc_group_address()
        recognizer._define_loc_block_summary()
        recognizer.recognition.per_num = recognizer._calculate_total_num_of_persons()

    final_recognition = recognizer.generate_final_reco_dict()

    return final_recognition.model_dump(exclude_none=True)
