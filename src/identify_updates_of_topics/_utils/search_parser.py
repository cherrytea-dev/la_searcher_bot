import logging
import re
from datetime import datetime

from _dependencies.commons import TopicType
from _dependencies.pubsub import recognize_title_via_api
from _dependencies.recognition_schema import RecognitionResult, RecognitionTopicType

from .coordinates import CoordinatesResolver
from .topics_commons import ForumSearchItem, SearchSummary


class SearchParser:
    """Builds a SearchSummary dataclass from a ForumSearchItem by:
    - Calling the title recognition API
    - Mapping RecognitionTopicType → TopicType
    - Detecting gender from title verb → annotating display_name
    - Geocoding recognized locations via CoordinatesResolver
    """

    # Mapping from recognition API types to internal TopicType enum
    _TOPIC_TYPE_MAP = {
        RecognitionTopicType.search: TopicType.search_regular,
        RecognitionTopicType.search_reverse: TopicType.search_reverse,
        RecognitionTopicType.search_patrol: TopicType.search_patrol,
        RecognitionTopicType.search_training: TopicType.search_training,
        RecognitionTopicType.event: TopicType.event,
        RecognitionTopicType.info: TopicType.info,
    }

    def __init__(self, coordinates_resolver: CoordinatesResolver) -> None:
        self.coordinates_resolver = coordinates_resolver

    def parse(
        self,
        current_datetime: datetime,
        forum_search_item: ForumSearchItem,
        folders_with_events: set[int] | None = None,
    ) -> SearchSummary | None:
        """Parse a forum search item into a SearchSummary using title recognition + geocoding.

        Args:
            current_datetime: The current timestamp for the parse.
            forum_search_item: The item parsed from the forum.
            folders_with_events: Optional set of folder IDs that contain only events.
                If the search's folder is in this set, topic_type is forced to 'event'.

        Returns:
            SearchSummary if recognition succeeded, None otherwise.
        """
        title_reco_response = recognize_title_via_api(forum_search_item.title, False)

        if title_reco_response and 'status' in title_reco_response and title_reco_response['status'] == 'ok':
            title_reco_dict = RecognitionResult.model_validate(title_reco_response['recognition'])
        else:
            return None

        logging.info(f'{title_reco_dict=}')

        # FIXME – 06.11.2023 – work to delete function "define_family_name_from_search_title_new"
        if title_reco_dict.topic_type == RecognitionTopicType.event:
            person_fam_name = None
        else:
            person_fam_name = title_reco_dict.persons.total_name if title_reco_dict.persons else 'БВП'

        topic_type = title_reco_dict.topic_type
        if folders_with_events and forum_search_item.folder_id in folders_with_events:
            topic_type = RecognitionTopicType.event

        search_summary_object = SearchSummary(
            parsed_time=current_datetime,
            topic_id=forum_search_item.search_id,
            title=forum_search_item.title,
            start_time=forum_search_item.start_datetime,
            num_of_replies=forum_search_item.replies_count,
            name=person_fam_name,
            folder_id=forum_search_item.folder_id,
            topic_type=topic_type,
            topic_type_id=self._TOPIC_TYPE_MAP[title_reco_dict.topic_type],
            new_status=title_reco_dict.status,
            status=title_reco_dict.status,
        )

        if title_reco_dict.persons:
            search_summary_object.display_name = self._add_gender(
                title_reco_dict.persons.total_display_name, search_summary_object.title
            )
            search_summary_object.age = title_reco_dict.persons.age_min
            # Due to the field "age" in searches which is integer, so we cannot indicate a range
            search_summary_object.age_min = title_reco_dict.persons.age_min
            search_summary_object.age_max = title_reco_dict.persons.age_max

        if title_reco_dict.locations:
            list_of_location_cities = [loc.address for loc in title_reco_dict.locations]
            list_of_location_coords = []
            for location_city in list_of_location_cities:
                city_lat, city_lon = self.coordinates_resolver.resolve(location_city)
                if city_lat and city_lon:
                    list_of_location_coords.append([city_lat, city_lon])
            search_summary_object.locations = list_of_location_coords

        logging.debug(f'search_summary_object={search_summary_object}')
        return search_summary_object

    @staticmethod
    def _add_gender(total_display_name: str, title: str) -> str:
        """Annotate display name with gender marker based on the title's first verb."""
        space_pos = total_display_name.find(' ')
        if not total_display_name[space_pos + 1].isdigit():
            return total_display_name

        pattern = re.compile(r'\w+')
        first_word_re = pattern.search(title)
        if not first_word_re:
            return total_display_name

        first_word = first_word_re.group()
        if first_word.lower() in ['пропала', 'похищена', 'жива', 'погибла']:
            gender_mark = 'ж'
        elif first_word.lower() in ['пропал', 'похищен', 'жив', 'погиб']:
            gender_mark = 'м'
        else:
            gender_mark = None

        if gender_mark == 'м' and 'подросток' in total_display_name.lower():
            gender_mark = None

        res_display_name = total_display_name
        if gender_mark:
            res_display_name = total_display_name[: space_pos + 1]
            res_display_name += gender_mark
            res_display_name += total_display_name[space_pos + 1 :]

        return res_display_name
