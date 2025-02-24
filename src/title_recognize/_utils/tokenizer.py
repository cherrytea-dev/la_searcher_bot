import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from .pattern_collections import PatternCollection
from .title_commons import Block, BlockType, PatternType, TitleRecognition, check_word_by_natasha


def match_type_to_pattern(pattern_type: PatternType) -> List[List[str]]:
    return PatternCollection().match_type_to_pattern(pattern_type)


def recognize_a_pattern(
    pattern_type: str, input_string: str
) -> Tuple[Optional[List[Union[None, str, Block]]], Optional[str]]:
    """Recognize data in a string with help of given pattern type"""

    block = None
    status = None
    activity = None

    patterns = match_type_to_pattern(pattern_type)

    if not patterns:
        return None, None

    for pattern in patterns:
        block = re.search(pattern[0], input_string)
        if block:
            status = pattern[1]
            if pattern_type in {BlockType.ST, BlockType.TR, BlockType.ACT}:
                activity = pattern[2]
            break

    if not block:
        return None, None

    start_number = block.start()
    end_number = block.end()

    reco_part = Block(init=block.group(), reco=status, type=pattern_type, done=True)

    rest_part_before = input_string[:start_number] if start_number != 0 else None
    rest_part_after = input_string[end_number:] if end_number != len(input_string) else None

    return [rest_part_before, reco_part, rest_part_after], activity


class Tokenizer:
    """split input string to tokens"""

    def __init__(self, recognition: TitleRecognition) -> None:
        self.recognition = recognition

    @classmethod
    def get_recognition_from_str(cls, line: str) -> TitleRecognition:
        prettified_line = cls._clean_and_prettify(line)
        recognition = TitleRecognition(_initial_text=line, pretty=prettified_line)
        tokenizer = cls(recognition)
        tokenizer._split_text_to_groups()
        return tokenizer.recognition

    def _split_text_to_groups(self) -> None:
        self._split_status_training_activity()
        self._split_per_from_loc_blocks()
        self._split_per_and_loc_blocks_to_groups()

    @classmethod
    def _clean_and_prettify(cls, string: str) -> str:
        """Convert a string with known mistypes to the prettified view"""

        patterns = PatternCollection.get_mistype_patterns()

        for pattern in patterns:
            string = re.sub(pattern[0], pattern[1], string)

        return string

    def _split_status_training_activity(self) -> None:
        """Create an initial 'Recognition' object and recognize data for Status, Training, Activity, Avia"""

        recognition = self.recognition
        list_of_pattern_types = [
            BlockType.ST,
            BlockType.ST,  # duplication – is not a mistake: there are cases when two status checks are necessary
            BlockType.TR,
            BlockType.AVIA,
            BlockType.ACT,
        ]

        first_block = Block(block_num=0, init=recognition.pretty, done=False)
        recognition.blocks.append(first_block)

        # find status / training / aviation / activity – via PATTERNS
        for pattern_type in list_of_pattern_types:
            for non_reco_block in recognition.blocks:
                if non_reco_block.done:
                    continue

                text_to_recognize = non_reco_block.init
                recognized_blocks, recognized_activity = recognize_a_pattern(pattern_type, text_to_recognize)
                self._update_full_blocks_with_new(non_reco_block.block_num, recognized_blocks)

                # TODO move calculation of "act" attribute somewhere else
                if recognition.act and recognized_activity and recognition.act != recognized_activity:
                    logging.error(
                        f'RARE CASE! recognized activity does not match: ' f'{recognition.act} != {recognized_activity}'
                    )
                    pass
                if recognized_activity and not recognition.act:
                    recognition.act = recognized_activity

        return recognition

    def _update_reco_with_per_and_loc_blocks(self, string_to_split: str, block: Block, marker: int) -> None:
        """Update the Recognition object with two separated Blocks for Persons and Locations"""

        recognized_blocks = []

        if len(string_to_split[:marker]) > 0:
            name_block = Block(block_num=block.block_num, init=string_to_split[:marker], done=True, type='PER')
            recognized_blocks.append(name_block)

        if len(string_to_split[marker:]) > 0:
            location_block = Block(block_num=block.block_num + 1, init=string_to_split[marker:], done=True, type='LOC')
            recognized_blocks.append(location_block)

        self._update_full_blocks_with_new(block.block_num, recognized_blocks)

    def _update_full_blocks_with_new(
        self,
        init_num_of_the_block_to_split: int,
        recognized_blocks: Optional[List[Union[None, str, Block]]],
    ) -> None:
        """Update the 'b1 Blocks' with the new recognized information"""

        if not recognized_blocks:
            return

        curr_recognition_blocks_b1 = []
        recognition = self.recognition

        # 0. Get Blocks, which go BEFORE the recognition
        for i in range(init_num_of_the_block_to_split):
            curr_recognition_blocks_b1.append(recognition.blocks[i])

        # 1. Get Blocks, which ARE FORMED by the recognition
        j = 0
        for item in recognized_blocks:
            if item and item != 'None':
                if isinstance(item, str):
                    new_block = Block(init=item, done=False)
                else:
                    new_block = item
                new_block.block_num = init_num_of_the_block_to_split + j
                j += 1
                curr_recognition_blocks_b1.append(new_block)

        # 2. Get Blocks, which go AFTER the recognition
        prev_num_of_b1_blocks = len(recognition.blocks)
        num_of_new_blocks = len([item for item in recognized_blocks if item])

        if prev_num_of_b1_blocks - 1 - init_num_of_the_block_to_split > 0:
            for i in range(prev_num_of_b1_blocks - init_num_of_the_block_to_split - 1):
                new_block = recognition.blocks[init_num_of_the_block_to_split + 1 + i]
                new_block.block_num = init_num_of_the_block_to_split + num_of_new_blocks + i
                curr_recognition_blocks_b1.append(new_block)

        recognition.blocks = curr_recognition_blocks_b1

    def _split_per_from_loc_blocks(self) -> None:
        """Split the string with persons and locations into two blocks of persons and locations"""

        recognition = self.recognition

        for block in recognition.blocks:
            if block.type:
                continue
            string_to_split = block.init
            marker_per = 0
            marker_loc = len(string_to_split)
            marker_final = None

            for patterns_list_item in PatternType.all_without_mistype():
                patterns, marker = match_type_to_pattern(patterns_list_item)

                for pattern in patterns:
                    marker_search = re.search(pattern, string_to_split[:marker_loc])

                    if marker_search:
                        if marker == 'loc':
                            marker_loc = min(marker_search.span()[0] + 1, marker_loc)
                        elif marker == 'per':
                            marker_per = max(marker_search.span()[1], marker_per)

                    # INTERMEDIATE RESULT: IF PERSON FINISHES WHERE LOCATION STARTS
                    if marker_per == marker_loc:
                        break
                else:
                    continue
                break

            if marker_per == marker_loc:
                marker_final = marker_per

            elif marker_per > 0:
                marker_final = marker_per

            else:
                # now we check, if the part of Title excl. recognized LOC finishes right before PER
                last_not_loc_word_is_per = check_word_by_natasha(string_to_split[:marker_loc], 'per')

                if last_not_loc_word_is_per:
                    marker_final = marker_loc

                else:
                    # language=regexp
                    patterns_2 = [[r'(?<=\W)\([А-Я][а-яА-Я,\s]*\)\W', ''], [r'\W*$', '']]
                    temp_string = string_to_split[marker_per:marker_loc]

                    for pattern_2 in patterns_2:
                        temp_string = re.sub(pattern_2[0], pattern_2[1], temp_string)

                    last_not_loc_word_is_per = check_word_by_natasha(temp_string, 'per')

                    if last_not_loc_word_is_per:
                        marker_final = marker_loc

                    elif marker_loc < len(string_to_split):
                        marker_final = marker_loc

                    else:
                        # let's check if there's any status defined for this activity
                        # if yes – there's a status – that means we can treat all the following as PER
                        there_is_status = False
                        there_is_training = False
                        num_of_blocks = len(recognition.blocks)

                        for block_2 in recognition.blocks:
                            if block_2.type == BlockType.ST:
                                there_is_status = True
                            elif block_2.type == BlockType.TR:
                                there_is_training = True

                        if there_is_status:
                            # if nothing helps – we're assuming all the words are Person with no Location
                            marker_final = marker_loc

                        elif there_is_training and num_of_blocks == 1:
                            pass

                        else:
                            logging.info(f'NEW RECO was not able to split per and loc for {string_to_split}')
                            pass

            if marker_final:
                self._update_reco_with_per_and_loc_blocks(string_to_split, block, marker_final)

    def _split_per_and_loc_blocks_to_groups(self) -> None:
        """Split the recognized Block with aggregated persons/locations to separate Groups of individuals/addresses"""

        recognition = self.recognition
        for block in recognition.blocks:
            if block.type not in {'PER', 'LOC'}:
                recognition.groups.append(block)
                continue

            individual_stops = []
            patterns = match_type_to_pattern(f'{block.type}_BY_INDIVIDUAL')

            for pattern in patterns:
                delimiters_list = re.finditer(pattern, block.init)

                if delimiters_list:
                    for delimiters_line in delimiters_list:
                        if delimiters_line.span()[1] != len(block.init):
                            individual_stops.append(delimiters_line.span()[1])

            individual_stops = list(set(individual_stops))
            individual_stops.sort()

            block_start = 0
            block_end = 0

            groups = []
            for item in individual_stops:
                block_end = item
                groups.append(block.init[block_start:block_end])
                block_start = block_end

            if len(individual_stops) > 0:
                groups.append(block.init[block_end:])

            if not groups:
                groups = [block.init]

            for i, gr in enumerate(groups):
                group = Block(
                    init=gr,
                    type=f'{block.type[0]}{i + 1}',
                )

                recognition.groups.append(group)
