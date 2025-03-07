import logging
import re
from itertools import chain
from typing import Any

from .pattern_collections import BlockTypePatternCollection, PatternCollectionbyBlockType
from .title_commons import Block, BlockType, PatternType, check_word_by_natasha


def recognize_a_pattern(block_type: BlockType, input_string: str) -> tuple[list[Block], str | None]:
    """Recognize data in a string with help of given pattern type"""

    match = None

    for pattern, status, activity in BlockTypePatternCollection.get_patterns(block_type):
        match = re.search(pattern, input_string)
        if match:
            break

    if not match:
        return [], None

    rest_part_before = input_string[: match.start()]
    rest_part_after = input_string[match.end() :]

    recognized_blocks: list[Block] = []

    if rest_part_before:
        recognized_blocks.append(Block(init=rest_part_before))

    recognized_blocks.append(
        Block(
            init=match.group(),
            reco=status,
            type=block_type,
            done=True,
            activity=activity,
        )
    )

    if rest_part_after:
        recognized_blocks.append(Block(init=rest_part_after))

    return recognized_blocks, activity


class Tokenizer:
    """split input string to tokens"""

    def __init__(self, pretty_text: str) -> None:
        self.pretty_text = pretty_text
        self.blocks: list[Block] = []

    def split_text_to_blocks(self) -> list[Block]:
        self._split_status_training_activity()
        self._split_per_from_loc_blocks()
        return self.blocks

    def _split_status_training_activity(self) -> None:
        """Create an initial 'Recognition' object and recognize data for Status, Training, Activity, Avia"""

        list_of_pattern_types = [
            BlockType.ST,
            BlockType.ST,  # duplication – is not a mistake: there are cases when two status checks are necessary
            BlockType.TR,
            BlockType.AVIA,
            BlockType.ACT,
        ]

        first_block = Block(init=self.pretty_text, done=False)
        self.blocks.append(first_block)

        # find status / training / aviation / activity – via PATTERNS
        for pattern_type in list_of_pattern_types:
            for block in self.blocks:
                if block.done:
                    continue

                recognized_blocks, recognized_activity = recognize_a_pattern(pattern_type, block.init)
                self._replace_block_with_splitted_blocks(block, recognized_blocks)

    def _replace_block_with_splitted_blocks(
        self,
        old_block: Block,
        recognized_blocks: list[Block],
    ) -> None:
        """Update the 'b1 Blocks' with the new recognized information"""

        if not recognized_blocks:
            return

        replaced_block_index = self.blocks.index(old_block)

        new_blocks: list[Block] = list(
            chain(
                self.blocks[:replaced_block_index],
                recognized_blocks,
                self.blocks[replaced_block_index + 1 :],
            )
        )

        self.blocks = new_blocks

    def _split_per_from_loc_blocks(self) -> None:
        """Split the string with persons and locations into two blocks of persons and locations"""

        for block in self.blocks:
            if block.type:
                continue
            self._split_block_to_person_and_location(block)

    def _split_block_to_person_and_location(self, block: Block) -> None:
        string_to_split = block.init

        marker_loc, marker_per = self._get_location_and_person_positions(string_to_split)

        marker = self._get_position_between_location_and_person(string_to_split, marker_loc, marker_per)

        if not marker:
            return

        """Update the Recognition object with two separated Blocks for Persons and Locations"""

        recognized_blocks = []

        person_part, location_part = string_to_split[:marker], string_to_split[marker:]
        if person_part:
            recognized_blocks.append(Block(init=person_part, done=True, type='PER'))

        if location_part:
            recognized_blocks.append(Block(init=location_part, done=True, type='LOC'))

        self._replace_block_with_splitted_blocks(block, recognized_blocks)

    def _get_position_between_location_and_person(
        self, string_to_split: str, marker_loc: int, marker_per: int
    ) -> int | None:
        if (marker_per == marker_loc) or (marker_per > 0):
            return marker_per

        # now we check, if the part of Title excl. recognized LOC finishes right before PER
        last_not_loc_word_is_per = check_word_by_natasha(string_to_split[:marker_loc], 'per')
        if last_not_loc_word_is_per:
            return marker_loc

        patterns_2 = [
            [r'(?<=\W)\([А-Я][а-яА-Я,\s]*\)\W', ''],
            [r'\W*$', ''],
        ]
        temp_string = string_to_split[marker_per:marker_loc]

        for pattern_2 in patterns_2:
            temp_string = re.sub(pattern_2[0], pattern_2[1], temp_string)

        last_not_loc_word_is_per = check_word_by_natasha(temp_string, 'per')

        if last_not_loc_word_is_per:
            return marker_loc

        if marker_loc < len(string_to_split):
            return marker_loc

        # let's check if there's any status defined for this activity
        # if yes – there's a status – that means we can treat all the following as PER
        there_is_status = any(True for block in self.blocks if block.type == BlockType.ST)

        if there_is_status:
            # if nothing helps – we're assuming all the words are Person with no Location
            return marker_loc

        logging.info(f'NEW RECO was not able to split per and loc for {string_to_split}')
        return None

    def _get_location_and_person_positions(self, string_to_split: str) -> tuple[int, int]:
        marker_loc = len(string_to_split)
        marker_per = 0
        for patterns_list_item in PatternType:
            patterns = PatternCollectionbyBlockType().get_patterns(patterns_list_item)
            # TODO move 'marker' out from PatternCollection

            for pattern in patterns:
                marker_search = re.search(pattern, string_to_split[:marker_loc])

                if not marker_search:
                    continue

                if patterns_list_item == PatternType.LOC_BLOCK:
                    marker_loc = min(marker_search.span()[0] + 1, marker_loc)
                else:
                    marker_per = max(marker_search.span()[1], marker_per)

                    # INTERMEDIATE RESULT: IF PERSON FINISHES WHERE LOCATION STARTS
                if marker_per == marker_loc:
                    return marker_loc, marker_per

        return marker_loc, marker_per
