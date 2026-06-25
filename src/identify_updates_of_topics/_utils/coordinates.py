import logging
import time
from datetime import datetime, timedelta, timezone

from _dependencies.common.pubsub import notify_admin

from .database import DBClient
from .external_api import (
    get_coordinates_from_address_by_osm,
    get_coordinates_from_address_by_yandex,
)


class CoordinatesResolver:
    """Geocode addresses to coordinates with caching (PSQL geocoding table),
    dual-provider fallback (OSM → Yandex), and rate limiting."""

    def __init__(self, db: DBClient) -> None:
        self.db = db

    def resolve(self, address: str) -> tuple[float, float] | tuple[None, None]:
        """Convert address string into a pair of coordinates.

        Uses cached results from PSQL first, then falls back to OSM → Yandex.
        Returns (lat, lon) or (None, None).
        """
        try:
            # check if this address was already geolocated and saved to psql
            saved_status, lat, lon, saved_geocoder = self.db.get_geolocation_form_psql(address)

            if lat and lon:
                return lat, lon

            elif saved_status == 'fail' and saved_geocoder == 'yandex':
                return None, None

            elif not saved_status:
                # when there's no saved record
                self._rate_limit_for_api(geocoder='osm')
                lat, lon = get_coordinates_from_address_by_osm(address)
                self.db.save_last_api_call_time_to_psql(geocoder='osm')

                if lat and lon:
                    saved_status = 'ok'
                    self.db.save_geolocation_in_psql(address, saved_status, lat, lon, 'osm')
                else:
                    saved_status = 'fail'

            if saved_status == 'fail' and (saved_geocoder == 'osm' or not saved_geocoder):
                # then we need to geocode with yandex
                self._rate_limit_for_api(geocoder='yandex')
                lat, lon = get_coordinates_from_address_by_yandex(address)
                self.db.save_last_api_call_time_to_psql(geocoder='yandex')

                saved_status = 'ok' if lat and lon else 'fail'
                self.db.save_geolocation_in_psql(address, saved_status, lat, lon, 'yandex')

            return lat, lon

        except Exception:
            # TODO too wide exception.
            # fails even if no free DB connection in pool
            # try to add OperationalError
            logging.exception('TEMP - LOC - New getting coordinates from title failed')
            notify_admin('ERROR: major geocoding script failed')
            raise

    def _rate_limit_for_api(self, geocoder: str) -> None:
        """sleeps certain time if api calls are too frequent"""
        if geocoder == 'yandex':
            return

        # check that next request won't be in less a SECOND from previous
        prev_api_call_time = self.db.get_last_api_call_time_from_psql(geocoder)

        if not prev_api_call_time:
            return

        now_utc = datetime.now(timezone.utc)
        time_delta_bw_now_and_next_request = prev_api_call_time - now_utc + timedelta(seconds=1)

        logging.debug(f'{prev_api_call_time=}')
        logging.debug(f'{now_utc=}')
        logging.debug(f'{time_delta_bw_now_and_next_request=}')

        if time_delta_bw_now_and_next_request.total_seconds() > 0:
            time.sleep(time_delta_bw_now_and_next_request.total_seconds())
            logging.debug(f'rate limit for {geocoder}: sleep {time_delta_bw_now_and_next_request.total_seconds()}')
            notify_admin(f'rate limit for {geocoder}: sleep {time_delta_bw_now_and_next_request.total_seconds()}')
