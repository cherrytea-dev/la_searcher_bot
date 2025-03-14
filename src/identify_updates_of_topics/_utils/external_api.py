import logging
from typing import Any, Tuple

from geopy.geocoders import Nominatim
from sqlalchemy.engine.base import Engine
from yandex_geocoder import Client, exceptions

from _dependencies.commons import get_app_config
from _dependencies.misc import notify_admin


def get_coordinates_from_address_by_osm(address_string: str) -> Tuple[Any, Any]:
    """return coordinates on the request of address string"""
    """NB! openstreetmap requirements: NO more than 1 request per 1 second, no doubling requests"""
    """MEMO: documentation on API: https://operations.osmfoundation.org/policies/nominatim/"""

    if not address_string:
        return None, None

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
