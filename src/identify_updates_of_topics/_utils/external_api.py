import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Tuple

from geopy.geocoders import Nominatim
from sqlalchemy.engine.base import Engine
from yandex_geocoder import Client, exceptions

from _dependencies.commons import get_app_config
from _dependencies.misc import notify_admin
from identify_updates_of_topics._utils.database import get_last_api_call_time_from_psql


def get_coordinates_from_address_by_osm(address_string: str) -> Tuple[Any, Any]:
    """return coordinates on the request of address string"""
    """NB! openstreetmap requirements: NO more than 1 request per 1 second, no doubling requests"""
    """MEMO: documentation on API: https://operations.osmfoundation.org/policies/nominatim/"""

    latitude = None
    longitude = None
    osm_identifier = get_app_config().osm_identifier
    geolocator = Nominatim(user_agent=osm_identifier)

    try:
        search_location = geolocator.geocode(address_string, timeout=10000)
        logging.info(f'geo_location by osm: {search_location}')
        if search_location:
            latitude, longitude = search_location.latitude, search_location.longitude

    except Exception as e6:
        logging.info(f'Error in func get_coordinates_from_address_by_osm for address: {address_string}. Repr: ')
        logging.exception(e6)
        notify_admin('ERROR: get_coords_from_address failed.')

    return latitude, longitude


def get_coordinates_from_address_by_yandex(address_string: str) -> tuple[float | None, float | None]:
    """return coordinates on the request of address string, geocoded by yandex"""

    latitude = None
    longitude = None
    yandex_api_key = get_app_config().yandex_api_key
    yandex_client = Client(yandex_api_key)

    try:
        coordinates = yandex_client.coordinates(address_string)
        logging.info(f'geo_location by yandex: {coordinates}')
    except Exception as e2:
        coordinates = None
        if isinstance(e2, exceptions.NothingFound):
            logging.info(f'address "{address_string}" not found by yandex')
        elif (
            isinstance(e2, exceptions.YandexGeocoderException)
            or isinstance(e2, exceptions.UnexpectedResponse)
            or isinstance(e2, exceptions.InvalidKey)
        ):
            logging.info('unexpected yandex error')
        else:
            logging.info('unexpected error:')
            logging.exception(e2)

    if coordinates:
        longitude, latitude = float(coordinates[0]), float(coordinates[1])

    return latitude, longitude


def rate_limit_for_api(db: Engine, geocoder: str) -> None:
    """sleeps certain time if api calls are too frequent"""

    # check that next request won't be in less a SECOND from previous
    prev_api_call_time = get_last_api_call_time_from_psql(db=db, geocoder=geocoder)

    if not prev_api_call_time:
        return None

    if geocoder == 'yandex':
        return None

    now_utc = datetime.now(timezone.utc)
    time_delta_bw_now_and_next_request = prev_api_call_time - now_utc + timedelta(seconds=1)

    logging.info(f'{prev_api_call_time=}')
    logging.info(f'{now_utc=}')
    logging.info(f'{time_delta_bw_now_and_next_request=}')

    if time_delta_bw_now_and_next_request.total_seconds() > 0:
        time.sleep(time_delta_bw_now_and_next_request.total_seconds())
        logging.info(f'rate limit for {geocoder}: sleep {time_delta_bw_now_and_next_request.total_seconds()}')
        notify_admin(f'rate limit for {geocoder}: sleep {time_delta_bw_now_and_next_request.total_seconds()}')

    return None
