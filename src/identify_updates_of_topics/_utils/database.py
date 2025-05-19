import logging
from datetime import datetime, timezone
from functools import lru_cache

import sqlalchemy
from sqlalchemy.engine import Connection
from sqlalchemy.engine.base import Engine

from _dependencies.commons import sqlalchemy_get_pool
from _dependencies.pubsub import notify_admin

from .topics_commons import (
    ChangeLogLine,
    CoordType,
    ForumCommentItem,
    SearchSummary,
)


class DBClient:
    def __init__(self, db: Engine) -> None:
        self._db = db

    def connect(self) -> Connection:
        return self._db.connect()

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
                WHERE search_id=:a AND address=:b;
                                   """)
            prev_data = conn.execute(stmt, a=search_num, b=address_string).fetchone()

            # if it's a new info
            if not prev_data:
                stmt = sqlalchemy.text("""
                    INSERT INTO search_places 
                    (search_id, address, timestamp)
                    VALUES (:a, :b, :c); 
                                       """)
                conn.execute(stmt, a=search_num, b=address_string, c=datetime.now())

    def save_geolocation_in_psql(
        self, address_string: str, status: str, latitude: float, longitude: float, geocoder: str
    ) -> None:
        """save results of geocoding to avoid multiple requests to openstreetmap service"""
        """the Geocoder HTTP API may not exceed 1000 per day"""

        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                INSERT INTO geocoding (address, status, latitude, longitude, geocoder, timestamp) VALUES
                (:a, :b, :c, :d, :e, :f)
                ON CONFLICT(address) DO
                UPDATE SET status=EXCLUDED.status, latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude,
                geocoder=EXCLUDED.geocoder, timestamp=EXCLUDED.timestamp;
                                   """)
            conn.execute(
                stmt, a=address_string, b=status, c=latitude, d=longitude, e=geocoder, f=datetime.now(timezone.utc)
            )

    def get_geolocation_form_psql(self, address_string: str) -> tuple[str | None, float, float, str]:
        """get results of geocoding from psql"""

        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT address, status, latitude, longitude, geocoder 
                FROM geocoding WHERE address=:a
                ORDER BY id DESC LIMIT 1; 
                                   """)
            saved_result = conn.execute(stmt, a=address_string).fetchone()

        logging.info(f'{address_string=}, {saved_result=}')

        # there is a psql record on this address - no geocoding activities are required
        if not saved_result:
            return None, 0.0, 0.0, ''

        if saved_result[1] == 'ok':
            latitude = saved_result[2]
            longitude = saved_result[3]
            geocoder = saved_result[4]
            return 'ok', latitude, longitude, geocoder

        return 'fail', 0.0, 0.0, ''

    def save_last_api_call_time_to_psql(self, geocoder: str) -> None:
        """Used to track time of the last api call to geocoders. Saves the current timestamp in UTC in psql"""

        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                    UPDATE geocode_last_api_call 
                    SET timestamp=:a AT TIME ZONE 'UTC' 
                    WHERE geocoder=:b;
                                       """)
            conn.execute(stmt, a=datetime.now(timezone.utc), b=geocoder)

    def get_last_api_call_time_from_psql(self, geocoder: str) -> datetime | None:
        """Used to track time of the last api call to geocoders. Gets the last timestamp in UTC saved in psql"""

        with self.connect() as conn:
            try:
                stmt = sqlalchemy.text("""
                    SELECT timestamp FROM geocode_last_api_call 
                    WHERE geocoder=:a LIMIT 1;
                                       """)
                last_call = conn.execute(stmt, a=geocoder).fetchone()
                return last_call[0]

            except Exception as e:
                logging.exception(f'UNSUCCESSFUL getting last api call time of geocoder {geocoder}')
                notify_admin(f'UNSUCCESSFUL getting last api call time of geocoder {geocoder}')

        return None

    def rewrite_snapshot_in_sql(self, folder_num: int, folder_summary: list[SearchSummary]) -> None:
        """rewrite the freshly-parsed snapshot into sql table 'forum_summary_snapshot'"""

        with self.connect() as conn:
            sql_text = sqlalchemy.text("""
                DELETE FROM forum_summary_snapshot 
                WHERE forum_folder_id = :a;
                                        """)
            conn.execute(sql_text, a=folder_num)

            sql_text = sqlalchemy.text("""
                INSERT INTO forum_summary_snapshot 
                    (search_forum_num, parsed_time, forum_search_title, search_start_time, num_of_replies, age, family_name, 
                    forum_folder_id, topic_type, display_name, age_min, age_max, status, city_locations, topic_type_id)
                VALUES (:a, :b, :d, :e, :f, :g, :h, :i, :j, :k, :l, :m, :n, :o, :p); 
                                       """)
            # FIXME – add status
            for line in folder_summary:
                conn.execute(
                    sql_text,
                    a=line.topic_id,
                    b=line.parsed_time,
                    d=line.title,
                    e=line.start_time,
                    f=line.num_of_replies,
                    g=line.age,
                    h=line.name,
                    i=line.folder_id,
                    j=line.topic_type,
                    k=line.display_name,
                    l=line.age_min,
                    m=line.age_max,
                    n=line.new_status,
                    o=str(line.locations),
                    p=line.topic_type_id,
                )

    def write_comment(self, comment_data: ForumCommentItem) -> None:
        with self.connect() as conn:
            if not comment_data.comment_text:
                return
            stmt = sqlalchemy.text("""
                INSERT INTO comments 
                    (comment_url, comment_text, comment_author_nickname,
                    comment_author_link, search_forum_num, comment_num, notification_sent, comment_global_num)
                VALUES (:a, :b, :c, :d, :e, :f, :g, :h); 
                                    """)
            conn.execute(
                stmt,
                a=comment_data.comment_url,
                b=comment_data.comment_text,
                c=comment_data.comment_author_nickname,
                d=comment_data.comment_author_link,
                e=comment_data.search_num,
                f=comment_data.comment_num,
                g='n' if comment_data.ignore else None,
                h=None if comment_data.ignore else comment_data.comment_forum_global_id,
            )

    def update_coordinates_in_db(self, search_id: int, lat: float, lon: float, coord_type: CoordType) -> None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT latitude, longitude, coord_type
                FROM search_coordinates
                WHERE search_id=:a LIMIT 1;
                                   """)
            old_coords = conn.execute(stmt, a=search_id).fetchone()

            current_coords_defined = bool(lat and lon)

            if current_coords_defined and old_coords is None:
                stmt = sqlalchemy.text("""
                        INSERT INTO search_coordinates
                        (search_id, latitude, longitude, coord_type, upd_time)
                        VALUES (:a, :b, :c, :d, CURRENT_TIMESTAMP);
                                           """)
                conn.execute(stmt, a=search_id, b=lat, c=lon, d=coord_type)
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
                            SET latitude=:a, longitude=:b, coord_type=:c, upd_time=CURRENT_TIMESTAMP
                            WHERE search_id=:d;
                                               """)
                    conn.execute(stmt, a=lat, b=lon, c=coord_type, d=search_id)
                    return

            # case when coords are not defined, but there were saved coords type 1 or 2 – so we need to mark as deleted
            if (
                not current_coords_defined
                and old_coords
                and old_coords[2] in {CoordType.type_1_exact, CoordType.type_2_wo_word}
            ):
                stmt = sqlalchemy.text("""
                        UPDATE search_coordinates
                        SET coord_type=:a, upd_time=CURRENT_TIMESTAMP
                        WHERE search_id=:b;
                                       """)
                conn.execute(stmt, a=coord_type, b=search_id)

    def get_current_snapshots_list(self, folder_num: int) -> list[SearchSummary]:
        sql_text = sqlalchemy.text("""
                SELECT search_forum_num, parsed_time, status, forum_search_title, search_start_time,
                num_of_replies, family_name, age, id, forum_folder_id, topic_type, display_name, age_min, age_max,
                status, city_locations, topic_type_id
                FROM forum_summary_snapshot 
                WHERE forum_folder_id = :a; 
                                """)
        with self.connect() as conn:
            rows = conn.execute(sql_text, a=folder_num).fetchall()
            curr_snapshot_list: list[SearchSummary] = []
            for row in rows:
                snapshot_line = SearchSummary(
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
                curr_snapshot_list.append(snapshot_line)
            return curr_snapshot_list

    def write_search(self, line: SearchSummary) -> int:
        """TODO we cannot update search right here because `search_forum_num` is not unique"""
        stmt = sqlalchemy.text("""
            INSERT INTO searches 
                (search_forum_num, parsed_time, forum_search_title,
                search_start_time, num_of_replies, age, family_name, forum_folder_id,
                topic_type, display_name, age_min, age_max, status, city_locations, topic_type_id) 
            values
                (:a, :b, :d, :e, :f, :g, :h, :i, :j, :k, :l, :m, :n, :o, :p)
            RETURNING id; 
                            """)
        with self.connect() as conn:
            row = conn.execute(
                stmt,
                a=line.topic_id,
                b=line.parsed_time,
                d=line.title,
                e=line.start_time,
                f=line.num_of_replies,
                g=line.age,
                h=line.name,
                i=line.folder_id,
                j=line.topic_type,
                k=line.display_name,
                l=line.age_min,
                m=line.age_max,
                n=line.new_status,
                o=str(line.locations),
                p=line.topic_type_id,
            ).fetchone()
            return row[0]

    def get_searches_by_ids(self, search_ids: list[int]) -> list[SearchSummary]:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT 
                    search_forum_num, parsed_time, status, forum_search_title, search_start_time,
                    num_of_replies, family_name, age, id, forum_folder_id,
                    topic_type, display_name, age_min, age_max, status, city_locations, topic_type_id 
                FROM searches
                WHERE search_forum_num = ANY(:a);
                                    """)

            rows = conn.execute(stmt, a=search_ids).fetchall()
            prev_searches_list: list[SearchSummary] = []
            for r in rows:
                search = SearchSummary(
                    topic_id=r[0],
                    parsed_time=r[1],
                    status=r[2],
                    title=r[3],
                    start_time=r[4],
                    num_of_replies=r[5],
                    name=r[6],
                    age=r[7],
                    searches_table_id=r[8],
                    folder_id=r[9],
                    topic_type=r[10],
                    display_name=r[11],
                    age_min=r[12],
                    age_max=r[13],
                    new_status=r[14],
                    locations=r[15],
                    topic_type_id=r[16],
                )
                prev_searches_list.append(search)
            return prev_searches_list

    def write_change_log(self, line: ChangeLogLine) -> int:
        # TODO field "parameters is obsolete"
        stmt = sqlalchemy.text("""
            INSERT INTO change_log 
                (parsed_time, search_forum_num, changed_field, new_value, parameters, change_type) 
                values (:a, :b, :c, :d, :e, :f) 
            RETURNING id;
                            """)
        with self.connect() as conn:
            raw_data = conn.execute(
                stmt,
                a=line.parsed_time,
                b=line.topic_id,
                c=line.changed_field,
                d=line.new_value,
                e=line.parameters,
                f=line.change_type,
            ).fetchone()
            return raw_data[0]

    def update_search_activities(self, search_num: int, search_activities: list[str]) -> None:
        logging.debug(f'DBG.P.103:Search activities: {search_activities}')

        # mark all old activities as deactivated
        sql_text = sqlalchemy.text("""
            UPDATE search_activities 
            SET activity_status = 'deactivated' 
            WHERE search_forum_num=:a; 
            """)
        with self.connect() as conn:
            conn.execute(sql_text, a=search_num)

            # add the latest activities for the search
            for activity_line in search_activities:
                sql_text = sqlalchemy.text("""
                    INSERT INTO search_activities 
                    (search_forum_num, activity_type, activity_status, timestamp) 
                    values ( :a, :b, :c, :d); 
                                        """)
                conn.execute(sql_text, a=search_num, b=activity_line, c='ongoing', d=datetime.now())

    def update_search_managers(self, search_num: int, managers: list[str]) -> None:
        if not managers:
            return

        with self.connect() as conn:
            sql_text = sqlalchemy.text("""
                INSERT INTO search_attributes 
                (search_forum_num, attribute_name, attribute_value, timestamp) 
                values ( :a, :b, :c, :d); 
                                    """)
            conn.execute(sql_text, a=search_num, b='managers', c=str(managers), d=datetime.now())

    def delete_search(self, search_num: int) -> None:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                DELETE FROM searches WHERE search_forum_num=:a;
                                   """)
            conn.execute(stmt, a=int(search_num))

    def get_folders_with_events_only(self) -> list[int]:
        with self.connect() as conn:
            stmt = sqlalchemy.text("""
                SELECT folder_id 
                FROM geo_folders 
                WHERE folder_type='events';
                                    """)

            return conn.execute(stmt).fetchall()


@lru_cache
def get_db_client() -> DBClient:
    pool = sqlalchemy_get_pool(5, 120)
    return DBClient(db=pool)
