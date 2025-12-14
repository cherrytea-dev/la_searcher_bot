import logging

from geopy.geocoders import Nominatim
from yandex_geocoder import Client, exceptions

from _dependencies.commons import get_app_config
from _dependencies.pubsub import notify_admin


def get_coordinates_from_address_by_osm(address_string: str) -> tuple[float, float]:
    """return coordinates on the request of address string"""
    """NB! openstreetmap requirements: NO more than 1 request per 1 second, no doubling requests"""
    """MEMO: documentation on API: https://operations.osmfoundation.org/policies/nominatim/"""

    if not address_string:
        return 0.0, 0.0

    geolocator = Nominatim(user_agent=get_app_config().osm_identifier)

    try:
        search_location = geolocator.geocode(address_string, timeout=30)
        logging.info(f'geo_location by osm: {search_location}')
        if search_location:
            return search_location.latitude, search_location.longitude

    except Exception:
        logging.exception(f'Error in func get_coordinates_from_address_by_osm for address: {address_string}.')
        notify_admin('ERROR: get_coords_from_address failed.')

    return 0.0, 0.0


def get_coordinates_from_address_by_yandex(address_string: str) -> tuple[float, float]:
    """return coordinates on the request of address string, geocoded by yandex"""

    yandex_client = Client(get_app_config().yandex_api_key)

    try:
        coordinates = yandex_client.coordinates(address_string)
        logging.info(f'geo_location by yandex: {coordinates}')
        return float(coordinates[1]), float(coordinates[0])
    except exceptions.NothingFound:
        logging.warning(f'address "{address_string}" not found by yandex')

    except (exceptions.YandexGeocoderException, exceptions.UnexpectedResponse, exceptions.InvalidKey):
        logging.warning('unexpected yandex error')

    except Exception:
        logging.exception('unexpected error:')

    return 0.0, 0.0
