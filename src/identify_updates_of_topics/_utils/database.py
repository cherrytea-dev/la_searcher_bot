import json
import logging
from datetime import datetime, timezone

import sqlalchemy
from sqlalchemy.engine.base import Engine

from _dependencies.misc import notify_admin


def save_function_into_register(db: Engine, context, start_time, function_id, change_log_ids):
    """save current function into functions_registry"""

    try:
        event_id = context.event_id
        json_of_params = json.dumps({'ch_id': change_log_ids})

        with db.connect() as conn:
            sql_text = sqlalchemy.text("""INSERT INTO functions_registry
                                                      (event_id, time_start, cloud_function_name, function_id,
                                                      time_finish, params)
                                                      VALUES (:a, :b, :c, :d, :e, :f)
                                                      /*action='save_ide_topics_function' */;""")
            conn.execute(
                sql_text,
                a=event_id,
                b=start_time,
                c='identify_updates_of_topics',
                d=function_id,
                e=datetime.now(),
                f=json_of_params,
            )
            logging.info(f'function {function_id} was saved in functions_registry')

    except Exception as e:
        logging.info(f'function {function_id} was NOT ABLE to be saved in functions_registry')
        logging.exception(e)

    return None


def get_the_list_of_ignored_folders(db: Engine) -> list[int]:
    """get the list of folders which does not contain searches – thus should be ignored"""

    with db.connect() as conn:
        sql_text = sqlalchemy.text(
            """SELECT folder_id FROM geo_folders WHERE folder_type != 'searches' AND folder_type != 'events';"""
        )
        raw_list = conn.execute(sql_text).fetchall()

        list_of_ignored_folders = [int(line[0]) for line in raw_list]

    return list_of_ignored_folders


def save_place_in_psql(db2, address_string, search_num):
    """save a link search to address in sql table search_places"""

    try:
        with db2.connect() as conn:
            # check if this record already exists
            stmt = sqlalchemy.text(
                """SELECT search_id FROM search_places
                WHERE search_id=:a AND address=:b;"""
            )
            prev_data = conn.execute(stmt, a=search_num, b=address_string).fetchone()

            # if it's a new info
            if not prev_data:
                stmt = sqlalchemy.text(
                    """INSERT INTO search_places (search_id, address, timestamp)
                    VALUES (:a, :b, :c); """
                )
                conn.execute(stmt, a=search_num, b=address_string, c=datetime.now())

            conn.close()

    except Exception as e7:
        logging.info('DBG.P.EXC.110: ')
        logging.exception(e7)
        notify_admin('ERROR: saving place to psql failed: ' + address_string + ', ' + search_num)

    return None


def save_geolocation_in_psql(db2: Engine, address_string: str, status: str, latitude, longitude, geocoder: str):
    """save results of geocoding to avoid multiple requests to openstreetmap service"""
    """the Geocoder HTTP API may not exceed 1000 per day"""

    try:
        with db2.connect() as conn:
            stmt = sqlalchemy.text(
                """INSERT INTO geocoding (address, status, latitude, longitude, geocoder, timestamp) VALUES
                (:a, :b, :c, :d, :e, :f)
                ON CONFLICT(address) DO
                UPDATE SET status=EXCLUDED.status, latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude,
                geocoder=EXCLUDED.geocoder, timestamp=EXCLUDED.timestamp;"""
            )
            conn.execute(
                stmt, a=address_string, b=status, c=latitude, d=longitude, e=geocoder, f=datetime.now(timezone.utc)
            )
            conn.close()

    except Exception as e2:
        logging.info(f'ERROR: saving geolocation to psql failed: {address_string}, {status}')
        logging.exception(e2)
        notify_admin(f'ERROR: saving geolocation to psql failed: {address_string}, {status}')

    return None


def get_geolocation_form_psql(db2, address_string: str):
    """get results of geocoding from psql"""

    with db2.connect() as conn:
        stmt = sqlalchemy.text(
            """SELECT address, status, latitude, longitude, geocoder from geocoding WHERE address=:a
            ORDER BY id DESC LIMIT 1; """
        )
        saved_result = conn.execute(stmt, a=address_string).fetchone()
        conn.close()

    logging.info(f'{address_string=}')
    logging.info(f'{saved_result=}')

    # there is a psql record on this address - no geocoding activities are required
    if saved_result:
        if saved_result[1] == 'ok':
            latitude = saved_result[2]
            longitude = saved_result[3]
            geocoder = saved_result[4]
            return 'ok', latitude, longitude, geocoder

        elif saved_result[1] == 'fail':
            return 'fail', None, None, None

    return None, None, None, None


def save_last_api_call_time_to_psql(db: Engine, geocoder: str) -> bool:
    """Used to track time of the last api call to geocoders. Saves the current timestamp in UTC in psql"""

    conn = None
    try:
        conn = db.connect()
        stmt = sqlalchemy.text(
            """UPDATE geocode_last_api_call SET timestamp=:a AT TIME ZONE 'UTC' WHERE geocoder=:b;"""
        )
        conn.execute(stmt, a=datetime.now(timezone.utc), b=geocoder)
        conn.close()

        return True

    except Exception as e:
        logging.info(f'UNSUCCESSFUL saving last api call time to geocoder {geocoder}')
        logging.exception(e)
        notify_admin(f'UNSUCCESSFUL saving last api call time to geocoder {geocoder}')
        if conn:
            conn.close()

        return False


def get_last_api_call_time_from_psql(db: sqlalchemy.engine, geocoder: str):
    """Used to track time of the last api call to geocoders. Gets the last timestamp in UTC saved in psql"""

    conn = None
    last_call = None
    try:
        conn = db.connect()
        stmt = sqlalchemy.text("""SELECT timestamp FROM geocode_last_api_call WHERE geocoder=:a LIMIT 1;""")
        last_call = conn.execute(stmt, a=geocoder).fetchone()
        last_call = last_call[0]
        conn.close()

    except Exception as e:
        logging.info(f'UNSUCCESSFUL getting last api call time of geocoder {geocoder}')
        logging.exception(e)
        notify_admin(f'UNSUCCESSFUL getting last api call time of geocoder {geocoder}')
        if conn:
            conn.close()

    return last_call
