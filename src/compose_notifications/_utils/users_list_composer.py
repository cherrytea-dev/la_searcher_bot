import datetime
import logging
from ast import literal_eval

from _dependencies.common.commons import ChangeType, SearchFollowingMode

from .commons import LineInChangeLog, User, define_dist_and_dir_to_search
from .database import DBClient


class UsersListComposer:
    def __init__(self, db: DBClient):
        self.db = db

    def get_users_list_for_line_in_change_log(self, new_record: LineInChangeLog) -> list[User]:
        list_of_users = self.compose_users_list_from_users(new_record)

        return list_of_users

    def compose_users_list_from_users(self, new_record: LineInChangeLog) -> list[User]:
        """compose the Users list from the tables Users & User Coordinates: one Record = one user"""

        analytics_prefix = 'users list'
        analytics_start = datetime.datetime.now()

        users_short_version = self.db.compose_users_list_for_change_log(
            change_type=new_record.change_type,
            forum_folder=new_record.forum_folder,
            topic_type_id=new_record.topic_type_id,
            forum_search_num=int(new_record.forum_search_num),
            following_mode_on=SearchFollowingMode.ON,
        )

        logging.info(f'Fetched users for search {new_record.forum_search_num=} with {new_record.new_status=}.')
        analytics_sql_finish = datetime.datetime.now()
        duration_sql = round((analytics_sql_finish - analytics_start).total_seconds(), 2)
        logging.info(f'time: {analytics_prefix} sql - {duration_sql} sec')

        logging.debug(f'{users_short_version}')

        list_of_users: list[User] = []

        for line in users_short_version:
            new_line = User(
                user_id=line[0],
                username_telegram=line[1],
                user_latitude=line[2],
                user_longitude=line[3],
                user_role=line[4],
                user_in_multi_folders=line[6],
                all_notifs=line[7],
                radius=int(line[8]) if line[8] is not None else 0,
                age_periods=line[9] if line[9] is not None else list(),
            )

            try:
                new_line.user_new_search_notifs = int(line[5])
            except:
                new_line.user_new_search_notifs = 0

            list_of_users.append(new_line)

        user_ids = [x.user_id for x in list_of_users]
        logging.info(f'user_ids in compose_users_list_from_users: count={len(user_ids)}, ids={user_ids}')

        analytics_match_finish = datetime.datetime.now()
        duration_match = round((analytics_match_finish - analytics_sql_finish).total_seconds(), 2)
        logging.info(f'time: {analytics_prefix} match - {duration_match} sec')
        duration_full = round((analytics_match_finish - analytics_start).total_seconds(), 2)
        logging.info(f'time: {analytics_prefix} end-to-end - {duration_full} sec')

        logging.info('User List composed')

        return list_of_users


class UserListFilter:
    def __init__(self, db: DBClient, new_record: LineInChangeLog, users: list[User]):
        self.db = db
        self.new_record = new_record
        self.users = users.copy()

    def apply(self) -> list[User]:
        """crop user_list to only affected users"""
        self.users = self._filter_inforg_double_notification_for_users()
        self.users = self._filter_users_by_age_settings()
        self.users = self._filter_users_by_search_radius()
        self.users = self._filter_users_with_prepared_messages()
        self.users = self._filter_users_not_following_this_search()

        return self.users

    def _filter_inforg_double_notification_for_users(self) -> list[User]:
        # 1. INFORG 2X notifications. crop the list of users, excluding Users who receives all types of notifications
        # (otherwise it will be doubling for them)
        record = self.new_record
        users_list_outcome = self.users
        temp_user_list: list[User] = []
        if record.change_type != ChangeType.topic_inforg_comment_new:
            logging.info(f'User List crop due to Inforg 2x: {len(users_list_outcome)} --> {len(users_list_outcome)}')
            return users_list_outcome
        else:
            for user_line in users_list_outcome:
                # if this record is about inforg_comments and user already subscribed to all comments
                check_passed = not user_line.all_notifs
                logging.info(
                    f'Inforg 2x CHECK for {user_line.user_id} is {"OK" if check_passed else "FAIL"}, record {record.change_type}, '
                    f'user {user_line.user_id} {user_line.all_notifs}. '
                    f'record {record.forum_search_num}'
                )
                if check_passed:
                    temp_user_list.append(user_line)
            logging.info(f'User List crop due to Inforg 2x: {len(users_list_outcome)} --> {len(temp_user_list)}')
        return temp_user_list

    def _filter_users_by_age_settings(self) -> list[User]:
        # 2. AGES. crop the list of users, excluding Users who does not want to receive notifications for such Ages
        users_list_outcome = self.users
        record = self.new_record
        if not (record.age_min or record.age_max):
            logging.info('User List crop due to ages: no changes, there were no age_min and max for search')
            return users_list_outcome

        temp_user_list: list[User] = []
        search_age_range = (record.age_min, record.age_max)

        for user_line in users_list_outcome:
            age_requirements_met = check_if_age_requirements_met(search_age_range, user_line.age_periods)
            if not age_requirements_met:
                logging.info(
                    f'AGE CHECK for {user_line.user_id} is FAIL, record {search_age_range}, '
                    f'user {user_line.age_periods}. record {record.forum_search_num}'
                )
            else:
                temp_user_list.append(user_line)

        logging.info(f'User List crop due to ages: {len(users_list_outcome)} --> {len(temp_user_list)}')
        return temp_user_list

    def _filter_users_by_search_radius(self) -> list[User]:
        # 3. RADIUS. crop the list of users, excluding Users who does want to receive notifications within the radius
        record = self.new_record
        users_list_outcome = self.users
        temp_user_list = []
        try:
            search_lat = record.search_latitude
            search_lon = record.search_longitude
            list_of_city_coords = None
            if record.city_locations and record.city_locations != 'None':
                non_geolocated = [x for x in literal_eval(record.city_locations) if isinstance(x, str)]
                list_of_city_coords = literal_eval(record.city_locations) if not non_geolocated else None

            # CASE 3.1. When exact coordinates of Search Headquarters are indicated
            if search_lat and search_lon:
                for user_line in users_list_outcome:
                    if not (user_line.radius and user_line.user_latitude and user_line.user_longitude):
                        temp_user_list.append(user_line)
                        continue
                    user_lat = user_line.user_latitude
                    user_lon = user_line.user_longitude
                    actual_distance, direction = define_dist_and_dir_to_search(
                        search_lat, search_lon, user_lat, user_lon
                    )
                    actual_distance = int(actual_distance)
                    if actual_distance <= user_line.radius:
                        temp_user_list.append(user_line)

            # CASE 3.2. When exact coordinates of a Place are geolocated
            elif list_of_city_coords:
                for user_line in users_list_outcome:
                    if not (user_line.radius and user_line.user_latitude and user_line.user_longitude):
                        temp_user_list.append(user_line)
                        continue
                    user_lat = user_line.user_latitude
                    user_lon = user_line.user_longitude

                    for city_coords in list_of_city_coords:
                        search_lat, search_lon = city_coords
                        if not search_lat or not search_lon:
                            continue
                        actual_distance, direction = define_dist_and_dir_to_search(
                            search_lat, search_lon, user_lat, user_lon
                        )
                        actual_distance = int(actual_distance)
                        if actual_distance <= user_line.radius:
                            temp_user_list.append(user_line)
                            break

            # CASE 3.3. No coordinates available
            else:
                temp_user_list = users_list_outcome

            logging.info(f'User List crop due to radius: {len(users_list_outcome)} --> {len(temp_user_list)}')

        except Exception as e:
            logging.info(f'TEMP - exception radius: {repr(e)}')
            logging.exception(e)
        return temp_user_list

    def _filter_users_with_prepared_messages(self) -> list[User]:
        # 4. DOUBLING. crop the list of users, excluding Users who were already notified on this change_log_id
        # TODO do we still need it?
        users_list_outcome = self.users
        users_with_prepared_messages = self._get_from_sql_list_of_users_with_prepared_message()
        if users_with_prepared_messages:
            logging.warning(
                f'DOUBLING_DIAG: change_log_id={self.new_record.change_log_id} - '
                f'{len(users_with_prepared_messages)} users already have notif_by_user records. '
                f'Users: {sorted(users_with_prepared_messages)}. '
                f'This indicates compose_notifications is reprocessing the same change_log record!'
            )
        temp_user_list = [user for user in users_list_outcome if user.user_id not in users_with_prepared_messages]
        logging.info(f'User List crop due to doubling: {len(users_list_outcome)} --> {len(temp_user_list)}')
        return temp_user_list

    def _filter_users_not_following_this_search(self) -> list[User]:
        # 5. FOLLOW SEARCH. crop the list of users accordingly to the rules of search following
        users_list_outcome = self.users
        record = self.new_record

        debug_user_id = 552487421
        debug_user_inside = False
        for user in users_list_outcome:
            if user.user_id == debug_user_id:
                debug_user_inside = True
                break
        logging.info(f'Before User list crop due to whitelisting for {record.forum_search_num=}: {debug_user_inside=}')

        logging.info(f'{record=}')

        following_users_ids = set(
            self.db.get_users_passing_following_filter(
                forum_search_num=record.forum_search_num,
                search_new_status=record.new_status,
                change_type=record.change_type,
                following_mode_on=SearchFollowingMode.ON,
                following_mode_off=SearchFollowingMode.OFF,
            )
        )
        logging.info(f'Crop user list due to whitelisting: len(following_users_ids)=={len(following_users_ids)}')

        temp_user_list: list[User] = []
        temp_user_list = [user for user in users_list_outcome if user.user_id in following_users_ids]

        debug_user_id = 552487421
        debug_user_inside = debug_user_id in following_users_ids

        logging.info(
            f'User List crop due to whitelisting for {record.forum_search_num=}: {len(users_list_outcome)} --> {len(temp_user_list)}, {debug_user_inside=}'
        )
        return temp_user_list

    def _get_from_sql_list_of_users_with_prepared_message(self) -> set[int]:
        """check what is the list of users for whom we already composed messages for the given change_log record"""

        user_ids = self.db.get_users_with_prepared_message(self.new_record.change_log_id)
        logging.info('list of user with composed messages:')
        logging.info(user_ids)
        logging.info(f'in total {len(user_ids)}')
        return set(user_ids)


def check_if_age_requirements_met(search_ages: tuple[int | None, int | None], user_ages: list[tuple[int, int]]) -> bool:
    """check if user wants to receive notifications for such age"""

    if not user_ages or search_ages[0] is None or search_ages[1] is None:
        return True

    for age_range in user_ages:
        if (min(*age_range) <= max(search_ages[0], search_ages[1])) and (
            max(*age_range) >= min(search_ages[0], search_ages[1])
        ):
            return True
    return False
