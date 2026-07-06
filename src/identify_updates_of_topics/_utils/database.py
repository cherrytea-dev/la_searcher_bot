import logging
from datetime import datetime, timezone
from functools import lru_cache

import sqlalchemy

from _dependencies.common.db_client import DBClientBase, DBKeyValueStorageMixin

from .topics_commons import (
    ChangeLogLine,
    CoordType,
    ForumCommentItem,
    SearchSummary,
)


class DBClient(DBClientBase, DBKeyValueStorageMixin):
    def get_the_list_of_ignored_folders(self) -> list[int]:
        """get the list of folders which does not contain searches – thus should be ignored"""

        with self.connect() as conn:
            sql_text = sqlalchemy.text(
                """SELECT folder_id FROM geo_folders WHERE folder_type != 'searches' AND folder_type != 'events';"""
            )
            raw_list = conn.execute(sql_text).fetchall()

            list_of_ignored_folders = [int(line[0]) for line in raw_list]

        return list_of_ignored_folders

    def save_place_in_psql(self, address_string: str, search_num: int) -> None:
        """save a link search to address in sql table search_places"""

        with self.connect() as conn:
            # check if this record already exists
            stmt = sqlalchemy.text("""
                SELECT search_id FROM search_places
                WHERE search_id=:search_num AND address=:address;
                                   """)
            prev_data = conn.execute(stmt, dict(search_num=search_num, address=address_string)).fetchone()

            # if it's a new info
            if not prev_data:
                stmt = sqlalchemy.text("""
                    INSERT INTO search_places 
                    (search_id, address, timestamp)
                    VALUES (:search_num, :address, :ts); 
                                       """)
                conn.execute(stmt, dict(search_num=search_num, address=address_string, ts=datetime.now()))

    def save_geolocation_in_psql(
        self, address_string: str, status: str, latitude: float, longitude: float, geocoder: str
    ) -> None:
        """save results of geocoding to avoid multiple requests to openstreetmap service"""
        """the Geocoder HTTP API may not exceed 1000 per day"""

        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                INSERT INTO geocoding (address, status, latitude, longitude, geocoder, timestamp) VALUES
                (:address, :status, :latitude, :longitude, :geocoder, :ts)
                ON CONFLICT(address) DO
                UPDATE SET status=EXCLUDED.status, latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude,
                geocoder=EXCLUDED.geocoder, timestamp=EXCLUDED.timestamp;
                                   """)
            conn.execute(
                stmt,
                dict(
                    address=address_string,
                    status=status,
                    latitude=latitude,
                    longitude=longitude,
                    geocoder=geocoder,
                    ts=datetime.now(timezone.utc),
                ),
            )

    def get_geolocation_form_psql(self, address_string: str) -> tuple[str | None, float, float, str]:
        """get results of geocoding from psql"""

        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT address, status, latitude, longitude, geocoder 
                FROM geocoding WHERE address=:address
                ORDER BY id DESC LIMIT 1; 
                                   """)
            saved_result = conn.execute(stmt, dict(address=address_string)).fetchone()

        logging.info(f'{address_string=}, {saved_result=}')

        # there is a psql record on this address - no geocoding activities are required
        if not saved_result:
            return None, 0.0, 0.0, ''

        geocoder = saved_result[4]
        if saved_result[1] == 'ok':
            latitude = saved_result[2]
            longitude = saved_result[3]
            return 'ok', latitude, longitude, geocoder

        return 'fail', 0.0, 0.0, geocoder

    def save_last_api_call_time_to_psql(self, geocoder: str) -> None:
        """Used to track time of the last api call to geocoders. Saves the current timestamp in UTC in psql"""

        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                    UPDATE geocode_last_api_call 
                    SET timestamp=:ts AT TIME ZONE 'UTC' 
                    WHERE geocoder=:geocoder;
                                       """)
            conn.execute(stmt, dict(ts=datetime.now(timezone.utc), geocoder=geocoder))

    def get_last_api_call_time_from_psql(self, geocoder: str) -> datetime | None:
        """Used to track time of the last api call to geocoders. Gets the last timestamp in UTC saved in psql"""

        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT timestamp FROM geocode_last_api_call 
                WHERE geocoder=:geocoder LIMIT 1;
                                    """)
            last_call = conn.execute(stmt, dict(geocoder=geocoder)).fetchone()
            return last_call[0] if last_call else None

    def rewrite_snapshot_in_sql(self, line: SearchSummary) -> None:
        """rewrite the freshly-parsed snapshot into sql table 'forum_summary_snapshot'"""

        with self.connect() as conn:
            sql_text_delete = sqlalchemy.text("""
                DELETE FROM forum_summary_snapshot 
                WHERE search_forum_num = :topic_id;
                                        """)

            sql_text_insert = sqlalchemy.text("""
                INSERT INTO forum_summary_snapshot 
                    (search_forum_num, parsed_time, forum_search_title, search_start_time, num_of_replies, age, family_name, 
                    forum_folder_id, topic_type, display_name, age_min, age_max, status, city_locations, topic_type_id)
                VALUES (:topic_id, :parsed_time, :title, :start_time, :num_of_replies, :age, :name, :folder_id, :topic_type, :display_name, :age_min, :age_max, :status, :locations, :topic_type_id); 
                                       """)
            # FIXME – add status
            conn.execute(sql_text_delete, dict(topic_id=line.topic_id))

            conn.execute(
                sql_text_insert,
                dict(
                    topic_id=line.topic_id,
                    parsed_time=line.parsed_time,
                    title=line.title,
                    start_time=line.start_time,
                    num_of_replies=line.num_of_replies,
                    age=line.age,
                    name=line.name,
                    folder_id=line.folder_id,
                    topic_type=line.topic_type,
                    display_name=line.display_name,
                    age_min=line.age_min,
                    age_max=line.age_max,
                    status=line.new_status,
                    locations=str(line.locations),
                    topic_type_id=line.topic_type_id,
                ),
            )

    def write_comment(self, comment_data: ForumCommentItem) -> None:
        with self.connect() as conn:
            if not comment_data.comment_text:
                return

            # Prevent duplicates caused by pagination offset mapping:
            # multiple comment_num values can resolve to the same forum page,
            # producing the same comment. Check by global post ID.
            if comment_data.comment_forum_global_id is not None:
                existing = conn.execute(
                    sqlalchemy.text(
                        'SELECT id FROM comments WHERE comment_global_num = :global_num AND search_forum_num = :search_num'
                    ),
                    dict(
                        global_num=str(comment_data.comment_forum_global_id),
                        search_num=comment_data.search_num,
                    ),
                ).fetchone()
                if existing:
                    return

            stmt = sqlalchemy.text("""
                INSERT INTO comments
                    (comment_url, comment_text, comment_author_nickname,
                    comment_author_link, search_forum_num, comment_num, notification_sent, comment_global_num)
                VALUES (:url, :text, :nickname, :author_link, :search_num, :comment_num, :notif_sent, :global_num);
                                    """)
            conn.execute(
                stmt,
                dict(
                    url=comment_data.comment_url,
                    text=comment_data.comment_text,
                    nickname=comment_data.comment_author_nickname,
                    author_link=comment_data.comment_author_link,
                    search_num=comment_data.search_num,
                    comment_num=comment_data.comment_num,
                    notif_sent='n' if comment_data.ignore else None,
                    global_num=None if comment_data.ignore else comment_data.comment_forum_global_id,
                ),
            )

    def update_coordinates_in_db(self, search_id: int, lat: float, lon: float, coord_type: CoordType) -> None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT latitude, longitude, coord_type
                FROM search_coordinates
                WHERE search_id=:search_id LIMIT 1;
                                   """)
            old_coords = conn.execute(stmt, dict(search_id=search_id)).fetchone()

            current_coords_defined = bool(lat and lon)

            if current_coords_defined and old_coords is None:
                stmt = sqlalchemy.text("""
                        INSERT INTO search_coordinates
                        (search_id, latitude, longitude, coord_type, upd_time)
                        VALUES (:search_id, :lat, :lon, :coord_type, CURRENT_TIMESTAMP);
                                           """)
                conn.execute(stmt, dict(search_id=search_id, lat=lat, lon=lon, coord_type=coord_type))
                return

            if current_coords_defined and old_coords is not None:
                # when coords are in search_coordinates table
                old_lat, old_lon, old_type = old_coords
                do_update = False
                if not old_type:
                    do_update = True
                elif not (old_type != CoordType.type_4_from_title and coord_type == CoordType.type_4_from_title):
                    do_update = True
                elif (
                    old_type == CoordType.type_4_from_title
                    and coord_type == CoordType.type_4_from_title
                    and (old_lat != lat or old_lon != lon)
                ):
                    do_update = True

                if do_update:
                    stmt = sqlalchemy.text("""
                            UPDATE search_coordinates
                            SET latitude=:lat, longitude=:lon, coord_type=:coord_type, upd_time=CURRENT_TIMESTAMP
                            WHERE search_id=:search_id;
                                               """)
                    conn.execute(stmt, dict(lat=lat, lon=lon, coord_type=coord_type, search_id=search_id))
                    return

            # case when coords are not defined, but there were saved coords type 1 or 2 – so we need to mark as deleted
            if (
                not current_coords_defined
                and old_coords
                and old_coords[2] in {CoordType.type_1_exact, CoordType.type_2_wo_word}
            ):
                stmt = sqlalchemy.text("""
                        UPDATE search_coordinates
                        SET coord_type=:coord_type, upd_time=CURRENT_TIMESTAMP
                        WHERE search_id=:search_id;
                                       """)
                conn.execute(stmt, dict(coord_type=coord_type, search_id=search_id))

    def get_current_snapshot(self, search_forum_num: int) -> SearchSummary | None:
        sql_text = sqlalchemy.text("""
                SELECT search_forum_num, parsed_time, status, forum_search_title, search_start_time,
                num_of_replies, family_name, age, id, forum_folder_id, topic_type, display_name, age_min, age_max,
                status, city_locations, topic_type_id
                FROM forum_summary_snapshot 
                WHERE search_forum_num = :search_forum_num; 
                                """)
        with self.connect() as conn:
            rows = conn.execute(sql_text, dict(search_forum_num=search_forum_num)).fetchall()
            if not rows:
                return None
            row = rows[0]
            return SearchSummary(
                topic_id=row[0],
                parsed_time=row[1],
                status=row[2],
                title=row[3],
                start_time=row[4],
                num_of_replies=row[5],
                name=row[6],
                age=row[7],
                searches_table_id=row[8],
                folder_id=row[9],
                topic_type=row[10],
                display_name=row[11],
                age_min=row[12],
                age_max=row[13],
                new_status=row[14],
                locations=row[15],
                topic_type_id=row[16],
            )

    def write_search(self, line: SearchSummary) -> int:
        """TODO we cannot update search right here because `search_forum_num` is not unique"""
        stmt = sqlalchemy.text("""
            INSERT INTO searches 
                (search_forum_num, parsed_time, forum_search_title,
                search_start_time, num_of_replies, age, family_name, forum_folder_id,
                topic_type, display_name, age_min, age_max, status, city_locations, topic_type_id) 
            values
                (:topic_id, :parsed_time, :title, :start_time, :num_of_replies, :age, :name, :folder_id,
                 :topic_type, :display_name, :age_min, :age_max, :status, :locations, :topic_type_id)
            RETURNING id; 
                            """)
        with self.connect() as conn:
            row = conn.execute(
                stmt,
                dict(
                    topic_id=line.topic_id,
                    parsed_time=line.parsed_time,
                    title=line.title,
                    start_time=line.start_time,
                    num_of_replies=line.num_of_replies,
                    age=line.age,
                    name=line.name,
                    folder_id=line.folder_id,
                    topic_type=line.topic_type,
                    display_name=line.display_name,
                    age_min=line.age_min,
                    age_max=line.age_max,
                    status=line.new_status,
                    locations=str(line.locations),
                    topic_type_id=line.topic_type_id,
                ),
            )
            return row.scalar()

    def get_search_by_id(self, search_id: int) -> SearchSummary | None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT 
                    search_forum_num, parsed_time, status, forum_search_title, search_start_time,
                    num_of_replies, family_name, age, id, forum_folder_id,
                    topic_type, display_name, age_min, age_max, status, city_locations, topic_type_id 
                FROM searches
                WHERE search_forum_num = :search_id;
                                    """)

            rows = conn.execute(stmt, dict(search_id=search_id)).fetchall()
            if not rows:
                return None

            row = rows[0]
            return SearchSummary(
                topic_id=row[0],
                parsed_time=row[1],
                status=row[2],
                title=row[3],
                start_time=row[4],
                num_of_replies=row[5],
                name=row[6],
                age=row[7],
                searches_table_id=row[8],
                folder_id=row[9],
                topic_type=row[10],
                display_name=row[11],
                age_min=row[12],
                age_max=row[13],
                new_status=row[14],
                locations=row[15],
                topic_type_id=row[16],
            )

    def write_change_log(self, line: ChangeLogLine) -> int:
        # TODO field "parameters is obsolete"
        stmt = sqlalchemy.text("""
            INSERT INTO change_log 
                (parsed_time, search_forum_num, changed_field, new_value, parameters, change_type) 
                values (:parsed_time, :topic_id, :changed_field, :new_value, :parameters, :change_type) 
            RETURNING id;
                            """)
        with self.connect() as conn:
            raw_data = conn.execute(
                stmt,
                dict(
                    parsed_time=line.parsed_time,
                    topic_id=line.topic_id,
                    changed_field=line.changed_field,
                    new_value=line.new_value,
                    parameters=line.parameters,
                    change_type=line.change_type,
                ),
            )
            return raw_data.scalar()

    def update_search_activities(self, search_num: int, search_activities: list[str]) -> None:
        logging.debug(f'DBG.P.103:Search activities: {search_activities}')

        # mark all old activities as deactivated
        sql_text = sqlalchemy.text("""
            UPDATE search_activities 
            SET activity_status = 'deactivated' 
            WHERE search_forum_num=:search_num; 
            """)
        with self.connect() as conn:
            conn.execute(sql_text, dict(search_num=search_num))

            # add the latest activities for the search
            for activity_line in search_activities:
                sql_text = sqlalchemy.text("""
                    INSERT INTO search_activities 
                    (search_forum_num, activity_type, activity_status, timestamp) 
                    values ( :search_num, :activity_type, :activity_status, :ts); 
                                        """)
                conn.execute(
                    sql_text,
                    dict(
                        search_num=search_num,
                        activity_type=activity_line,
                        activity_status='ongoing',
                        ts=datetime.now(),
                    ),
                )

    def update_search_managers(self, search_num: int, managers: list[str]) -> None:
        if not managers:
            return

        with self.connect() as conn:
            sql_text = sqlalchemy.text("""
                INSERT INTO search_attributes 
                (search_forum_num, attribute_name, attribute_value, timestamp) 
                values ( :search_num, :attribute_name, :attribute_value, :ts); 
                                    """)
            conn.execute(
                sql_text,
                dict(
                    search_num=search_num,
                    attribute_name='managers',
                    attribute_value=str(managers),
                    ts=datetime.now(),
                ),
            )

    def delete_search(self, search_num: int) -> None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                DELETE FROM searches WHERE search_forum_num=:search_num;
                                   """)
            conn.execute(stmt, dict(search_num=int(search_num)))

    def get_folders_with_events_only(self) -> list[int]:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT folder_id 
                FROM geo_folders 
                WHERE folder_type='events';
                                    """)

            return [row[0] for row in conn.execute(stmt).fetchall()]


@lru_cache
def get_db_client() -> DBClient:
    return DBClient()
