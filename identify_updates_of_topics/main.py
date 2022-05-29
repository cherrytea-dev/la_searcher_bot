import os
import ast
import yaml
import json
import re
import base64
import time
import logging
from datetime import datetime, timedelta

import requests
import sqlalchemy
from bs4 import BeautifulSoup, SoupStrainer  # noqa

from google.cloud import secretmanager
from google.cloud import storage
from google.cloud import pubsub_v1

project_id = os.environ["GCP_PROJECT"]
client = secretmanager.SecretManagerServiceClient()
publisher = pubsub_v1.PublisherClient()

# TODO: to delete and replace errors by noqa
# Made as a placeholder to avoid PyCharm errors. db to be re-defined in a function sql_connect()
db = sqlalchemy.create_engine(
    sqlalchemy.engine.url.URL(
        "postgresql+pg8000", username='db_user', password='db_pass', database='db_name',
        query={"unix_sock": "{}/{}/.s.PGSQL.5432".format('db_socket_dir', 'db_conn')}
    )
)

# Sessions – to reuse for reoccurring requests
requests_session = None

# to be reused by different functions
block_of_profile_rough_code = None

dict_status_words = {'жив': 'one', 'жива': 'one', 'живы': 'many',
                     'завершен': 'na', 'завершён': 'na',
                     'идет': 'na', 'идёт': 'na', 'информации': 'na',
                     'найден': 'one', 'найдена': 'one', 'найдены': 'many',
                     'погиб': 'one', 'погибла': 'one', 'погибли': 'many',
                     'поиск': 'na', 'приостановлен': 'na', 'проверка': 'na',
                     'пропал': 'one', 'пропала': 'one', 'пропали': 'many',
                     'стоп': 'na', 'эвакуация': 'na'}
dict_ignore = {'', ':'}


# TODO: requires update - to change folder_num to file_name
def set_cloud_storage(bucket_name, folder_num):
    """sets the basic parameters for connection to txt file in cloud storage, which stores searches snapshots"""

    if isinstance(folder_num, int) or folder_num == 'geocode':
        blob_name = str(folder_num) + '.txt'
    else:
        blob_name = folder_num
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(blob_name)

    return blob


def write_snapshot_to_cloud_storage(bucket_to_write, what_to_write, folder_num):
    """writes current search's snapshot to txt file in cloud storage"""

    blob = set_cloud_storage(bucket_to_write, folder_num)
    blob.upload_from_string(what_to_write)

    return None


def read_snapshot_from_cloud_storage(bucket_to_read, folder_num):
    """reads previous search's snapshot from txt file in cloud storage"""

    try:
        blob = set_cloud_storage(bucket_to_read, folder_num)
        contents_as_bytes = blob.download_as_string()
        contents = str(contents_as_bytes, 'utf-8')
    except:  # noqa
        contents = None

    return contents


def read_yaml_from_cloud_storage(bucket_to_read, folder_num):
    """reads yaml in cloud storage"""

    try:
        blob = set_cloud_storage(bucket_to_read, folder_num)
        contents_as_bytes = blob.download_as_string()
        # contents = str(contents_as_bytes, 'utf-8')
        contents = contents_as_bytes
    except:  # noqa
        contents = None

    return contents


def parse_coordinates(search_num):
    """finds coordinates of the search"""

    from geopy.geocoders import Nominatim
    import copy

    global requests_session

    def parse_address_from_title(title):

        after_age = 0
        age_dict = [' год ', ' год', ' года ', ' года', ' лет ', ' лет', 'г.р.', '(г.р.),', 'лет)', 'лет,']
        for word in age_dict:
            age_words = title.find(word)
            if age_words == -1:
                pass
            else:
                after_age = max(after_age, age_words + len(word))

        address_string = None
        if after_age > 0:
            address_string = title[after_age:].strip()
        else:
            numbers = [int(float(s)) for s in re.findall(r"\d*\d", title)]
            if numbers and numbers[0]:
                age_words = title.find(str(numbers[0]))
                if age_words == -1:
                    address_string = title
                else:
                    after_age = age_words + len(str(numbers[0]))
                    address_string = title[after_age:].strip()
            else:
                address_string = title

        # ABOVE is not optimized - but with this part ages are excluded better (for cases when there are 2 persons)
        trigger_of_age_mentions = True

        while trigger_of_age_mentions:
            trigger_of_age_mentions = False
            for word in age_dict:
                if address_string.find(word) > -1:
                    trigger_of_age_mentions = True
                    after_age = address_string.find(word) + len(word)
                    address_string = address_string[after_age:]

        useless_symbols = {'.', ',', ' ', ':', ';' '!', ')'}
        trigger_of_useless_symbols = True

        while trigger_of_useless_symbols:
            trigger_of_useless_symbols = False
            for word in useless_symbols:
                if address_string[0:len(word)] == word:
                    trigger_of_useless_symbols = True
                    address_string = address_string[len(word):]

        # case when there's "г.о." instead of "городской округ"
        if address_string.find('г.о.') != -1:
            address_string = address_string.replace('г.о.', 'городской округ')

        # case when there's "муниципальный округ"
        if address_string.find('м.о.') != -1:
            address_string = address_string.replace('м.о.', 'муниципальный округ')

        # case when 'мкрн' or 'мкр'
        if address_string.find('мкрн') != -1:
            address_string = address_string.replace('мкрн', '')
        if address_string.find('мкр') != -1:
            address_string = address_string.replace('мкр', '')

        # case with 'р-н' and 'АО'
        if address_string.find('р-н') != -1 and address_string.find('АО') != -1:
            by_word = address_string.split()
            word_with_ao = None
            for word in by_word:
                if word.find('АО') != -1:
                    word_with_ao = word
            if word_with_ao:
                address_string = address_string.replace(word_with_ao, '')

        # case with 'р-н' or 'р-на' or 'р-он'
        if address_string.find('р-на') != -1:
            address_string = address_string.replace('р-на', 'район')
        if address_string.find('р-н') != -1:
            address_string = address_string.replace('р-н', 'район')
        if address_string.find('р-он') != -1:
            address_string = address_string.replace('р-он', 'район')

        # case with 'обл'
        if address_string.find('обл.') != -1:
            address_string = address_string.replace('обл.', 'область')

        # case with 'НСО'
        if address_string.find('НСО') != -1:
            address_string = address_string.replace('НСО', 'Новосибирская область')

        # case with 'МО'
        if address_string.find('МО') != -1:
            mo_dict = {' МО ', ' МО,'}
            for word in mo_dict:
                if address_string.find(word) != -1:
                    address_string = address_string.replace(word, 'Московская область')
            if address_string[-3:] == ' МО':
                address_string = address_string[:-3] + ' Московская область'

        # case with 'ЛО'
        if address_string.find('ЛО') != -1:
            mo_dict = {' ЛО ', ' ЛО,'}
            for word in mo_dict:
                if address_string.find(word) != -1:
                    address_string = address_string.replace(word, 'Ленинградская область')
            if address_string[-3:] == ' ЛО':
                address_string = address_string[:-3] + ' Ленинградская область'

        # in case "г.Сочи"
        if address_string.find('г.Сочи') != -1:
            address_string = address_string.replace('г.Сочи', 'Сочи')
        if address_string.find('г. Сочи') != -1:
            address_string = address_string.replace('г. Сочи', 'Сочи')

        # case with 'района'
        if address_string.find('района') != -1:
            by_word = address_string.split()
            prev_word = None
            this_word = None
            for i in range(len(by_word) - 1):
                if by_word[i + 1] == 'района':
                    prev_word = by_word[i]
                    this_word = by_word[i + 1]
                    break
            if prev_word and this_word:
                address_string = address_string.replace(prev_word, prev_word[:-3] + 'ий')
                address_string = address_string.replace(this_word, this_word[:-1])

        # case with 'области'
        if address_string.find('области') != -1:
            by_word = address_string.split()
            prev_word = None
            this_word = None
            for i in range(len(by_word) - 1):
                if by_word[i + 1] == 'области':
                    prev_word = by_word[i]
                    this_word = by_word[i + 1]
                    break
            if prev_word and this_word:
                address_string = address_string.replace(prev_word, prev_word[:-2] + 'ая')
                address_string = address_string.replace(this_word, this_word[:-1] + 'ь')

        # add all the cases ABOVE
        # TODO: can be refactored in a more pythonic way
        # delete garbage in the beginning of string
        try:
            first_num = re.search(r"\d", address_string).start()
        except:  # noqa
            first_num = 0
        try:
            first_letter = re.search(r'[а-яА-Я]', address_string).start()
        except:  # noqa
            first_letter = 0

        new_start = max(first_num, first_letter)

        if address_string.lower().find('г. москва') != -1 or address_string.lower().find('г.москва') != -1:
            address_string = address_string.replace('г.', '')

        # add Russia to be sure
        # Openstreetmap.org treats Krym as Ukraine - so for search purposes Russia is avoided
        if address_string.lower().find('крым') == -1 and address_string.lower().find('севастополь') == -1:
            address_string = address_string[new_start:] + ', Россия'

        # case - first "с.", "п." and "д." are often misinterpreted - so it's easier to remove it
        wrong_first_symbols_dict = {' ', ',', ')', '.', 'с.', 'д.', 'п.', 'г.', 'гп', 'пос.', 'уч-к', 'р,',
                                    'р.', 'г,', 'ст.', 'л.', 'дер ', 'дер.', 'пгт ', 'ж/д', 'б/о', 'пгт.',
                                    'х.', 'ст-ца', 'с-ца', 'стан.'}

        trigger_of_wrong_symbols = True

        while trigger_of_wrong_symbols:

            this_iteration_bring_no_changes = True

            for wrong_symbols in wrong_first_symbols_dict:
                if address_string[:len(wrong_symbols)] == wrong_symbols:
                    # if the first symbols are from wrong symbols list - we delete them
                    address_string = address_string[len(wrong_symbols):]
                    this_iteration_bring_no_changes = False

            if this_iteration_bring_no_changes:
                trigger_of_wrong_symbols = False

        # ONE-TIME EXCEPTIONS:
        if address_string.find('г. Сольцы, Новгородская обл. – г. Санкт-Петербург'):
            address_string = address_string.replace('г. Сольцы, Новгородская область – г. Санкт-Петербург',
                                                    'г. Сольцы, Новгородская область')
        if address_string.find('Орехово-Зуевский район'):
            address_string = address_string.replace('Орехово-Зуевский район', 'Орехово-Зуевский городской округ')
        if address_string.find('НТ Нефтяник'):
            address_string = address_string.replace('СНТ Нефтяник', 'СНТ Нефтянник')
        if address_string.find('Коченевский'):
            address_string = address_string.replace('Коченевский', 'Коченёвский')
        if address_string.find('Самара - с. Красный Яр'):
            address_string = address_string.replace('г. Самара - с. Красный Яр', 'Красный Яр')
        if address_string.find('укреево-Плессо'):
            address_string = address_string.replace('Букреево-Плессо', 'Букреево Плёсо')
        if address_string.find('Москва Москва: Юго-Западный АО, '):
            address_string = address_string.replace('г.Москва Москва: Юго-Западный АО, ', 'ЮЗАО, Москва, ')
        if address_string.find(' Луховицы - д.Алтухово'):
            address_string = address_string.replace(' Луховицы - д. Алтухово, Зарайский городской округ,', 'Луховицы')
        if address_string.find('Сагкт-Петербург'):
            address_string = address_string.replace('Сагкт-Петербург', 'Санкт-Петербург')
        if address_string.find('Краснозерский'):
            address_string = address_string.replace('Краснозерский', 'Краснозёрский')
        if address_string.find('Толмачевское'):
            address_string = address_string.replace('Толмачевское', 'Толмачёвское')
        if address_string.find('Кочевский'):
            address_string = address_string.replace('Кочевский', 'Кочёвский')
        if address_string.find('Чесцы'):
            address_string = address_string.replace('Чесцы', 'Часцы')

        return address_string

    def save_geolocation_in_psql(address_string, status, latitude, longitude):
        """save results of geocoding to avoid multiple requests to openstreetmap service"""

        global db
        try:
            with db.connect() as conn:
                stmt = sqlalchemy.text(
                    """INSERT INTO geocoding (address, status, latitude, longitude) VALUES (:a, 
                    :b, :c, :d); """
                )
                conn.execute(stmt, a=address_string, b=status, c=latitude, d=longitude)
        except Exception as e7:
            logging.info('DBG.P.EXC.109: ')
            logging.exception(e7)
            notify_admin('ERROR: saving geolocation to psql failed: ' + address_string + ', ' + status)

        return None

    def save_place_in_psql(address_string):
        """save a link search to address in sql table search_places"""

        global db
        try:
            with db.connect() as conn:
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

        except Exception as e7:
            logging.info('DBG.P.EXC.110: ')
            logging.exception(e7)
            notify_admin('ERROR: saving place to psql failed: ' + address_string + ', ' + search_num)

        return None

    def load_geolocation_form_psql(address_string):
        """get results of geocoding from psql"""

        global db

        with db.connect() as conn:
            stmt = sqlalchemy.text(
                """SELECT address, status, latitude, longitude from geocoding WHERE address=:a LIMIT 1; """
            )
            saved_result = conn.execute(stmt, a=address_string).fetchone()

        return saved_result

    def get_coordinates_from_address(address_string):
        """return coordinates on the request of address string"""
        """NB! openstreetmap allows request with requirements: NO more request than 1 min, no doubling requests"""

        latitude = 0
        longitude = 0
        status_in_psql = None

        geolocator = Nominatim(user_agent="LizaAlertBot")

        # first - check if this address was already geolocated and saved to psql
        saved_loc_list = load_geolocation_form_psql(address_string)

        # there is a psql record on this address - no geocoding activities are requires
        if saved_loc_list:
            if saved_loc_list[1] == 'ok':
                latitude = saved_loc_list[2]
                longitude = saved_loc_list[3]

            elif saved_loc_list[1] == 'failed':
                status_in_psql = 'failed'

        # no psql record for this address found
        else:
            if not latitude and not longitude and status_in_psql != 'failed':
                try:
                    # second – check that next request won't be in less a minute from previous
                    prev_str_of_geocheck = read_snapshot_from_cloud_storage('bucket_for_ad_hoc', 'geocode')
                    logging.info(f'prev_str_of_geocheck: {prev_str_of_geocheck}')

                    if prev_str_of_geocheck:
                        prev_time_of_geocheck = datetime.strptime(prev_str_of_geocheck, '%Y-%m-%dT%H:%M:%S+00:00')
                        now = datetime.now()
                        if prev_time_of_geocheck:
                            time_delta_bw_now_and_next_request = prev_time_of_geocheck + timedelta(seconds=1) - now
                        else:
                            time_delta_bw_now_and_next_request = timedelta(seconds=0)
                        if time_delta_bw_now_and_next_request.total_seconds() > 0:
                            time.sleep(time_delta_bw_now_and_next_request.total_seconds())

                    try:
                        search_location = geolocator.geocode(address_string, timeout=10000)
                        logging.info(f'geo_location: {str(search_location)}')
                    except Exception as e55:
                        search_location = None
                        logging.info('ERROR: geo loc ')
                        logging.exception(e55)
                        notify_admin(f'ERROR: in geo loc : {str(e55)}')

                    now_str = datetime.now().strftime('%Y-%m-%dT%H:%M:%S+00:00')
                    write_snapshot_to_cloud_storage('bucket_for_ad_hoc', now_str, 'geocode')

                    if search_location:
                        latitude, longitude = search_location.latitude, search_location.longitude
                        save_geolocation_in_psql(address_string, 'ok', latitude, longitude)
                    else:
                        save_geolocation_in_psql(address_string, 'fail', None, None)
                except Exception as e6:
                    logging.info('error in script get_coordinates_from_address for address_string: '
                                 + address_string + '. Repr: ')
                    logging.exception(e6)
                    notify_admin('ERROR: get_coords_from_address failed. It includes geolocator frequency check')

        return latitude, longitude

    # TODO: needed debug?
    # DEBUG - function execution time counter
    func_start = datetime.now()
    # DEBUG - function execution time counter

    url_beginning = 'https://lizaalert.org/forum/viewtopic.php?t='
    url_to_topic = url_beginning + str(search_num)

    lat = 0
    lon = 0
    coord_type = ''
    r = None
    search_code_blocks = None
    title = None

    try:
        r = requests_session.get(url_to_topic)  # noqa
        soup = BeautifulSoup(r.content, features="html.parser")

        # parse title
        title_code = soup.find('h2', {'class': 'topic-title'})
        title = title_code.text

        # open the first post
        search_code_blocks = soup.find('div', 'content')

        # removing <br> tags
        for e in search_code_blocks.findAll('br'):
            e.extract()

    except Exception as e:
        logging.info(f'unable to parse a specific thread with address {url_to_topic} error is {repr(e)}')

    # FIRST CASE = THERE ARE COORDINATES w/ a WORD Coordinates
    try:
        # make an independent variable
        a = copy.copy(search_code_blocks)

        # extracting a text area where Coordinates are mentioned
        # a = search_code_blocks.find(lambda tag: 'Коор' in tag.text or 'коор' in tag.text)

        # remove a text with strike-through
        b = a.find_all('span', {'style': 'text-decoration:line-through'})
        for i in range(len(b)):
            b[i].decompose()

        # preparing a list of 100-character strings which starts with Coord mentioning
        e = []
        i = 0
        f = str(a).lower()

        while i < len(f):
            if f[i:].find('коорд') > 0:
                d = i + f[i:].find('коорд')
                e.append(f[d:(d + 100)])
                if d == 0 or d == -1:
                    i = len(f)
                else:
                    i = d + 1
            else:
                i = len(f)

        # extract exact numbers & match if they look like coordinates
        for i in range(len(e)):
            g = [float(s) for s in re.findall(r'-?\d+\.?\d*', e[i])]
            if len(g) > 1:
                for j in range(len(g) - 1):
                    try:
                        # Majority of coords in RU: lat in [40-80], long in [20-180], expected minimal format = XX.XXX
                        if 3 < (g[j] // 10) < 8 and len(str(g[j])) > 5 and 1 < (g[j + 1] // 10) < 19 and len(
                                str(g[j + 1])) > 5:
                            lat = g[j]
                            lon = g[j + 1]
                            coord_type = '1. coordinates w/ word coord'
                    except Exception as e2:
                        logging.info('DBG.P.36.EXC. Coords-1:')
                        logging.exception(e2)

    except Exception as e:
        logging.info('Exception happened')
        logging.exception(e)
        pass

    # SECOND CASE = THERE ARE COORDINATES w/o a WORD Coordinates
    if lat == 0:
        # make an independent variable
        a = copy.copy(search_code_blocks)

        try:
            # extracting a text area where Coordinates are mentioned

            # remove a text with strike-through
            b = a.find_all('span', {'style': 'text-decoration:line-through'})
            for i in range(len(b)):
                b[i].decompose()

            # removing <span> tags
            for e in a.findAll('span'):
                e.replace_with(e.text)

            # removing <img> tags
            for e in a.findAll('img'):
                e.extract()

            # removing <a> tags
            for e in a.findAll('a'):
                e.extract()

            # removing <strong> tags
            for e in a.findAll('strong'):
                e.replace_with(e.text)

            # converting to string
            b = re.sub(r'\n\s*\n', r' ', a.get_text().strip(), flags=re.M)
            c = re.sub(r'\n', r' ', b)
            g = [float(s) for s in re.findall(r'-?\d+\.?\d*', c)]
            if len(g) > 1:
                for j in range(len(g) - 1):
                    try:
                        # Majority of coords in RU: lat in [40-80], long in [20-180], expected minimal format = XX.XXX
                        if 3 < (g[j] // 10) < 8 and len(str(g[j])) > 5 and 1 < (g[j + 1] // 10) < 19 and len(
                                str(g[j + 1])) > 5:
                            lat = g[j]
                            lon = g[j + 1]
                            coord_type = '2. coordinates w/o word coord'
                    except Exception as e2:
                        logging.info('DBG.P.36.EXC. Coords-2:')
                        logging.exception(e2)
        except Exception as e:
            logging.info('Exception 2')
            logging.exception(e)
            pass

    # THIRD CASE = DELETED COORDINATES
    if lat == 0:

        # make an independent variable
        a = copy.copy(search_code_blocks)

        try:
            # extracting a text area where Coordinates are mentioned

            # get a text with strike-through
            a = a.find_all('span', {'style': 'text-decoration:line-through'})
            if a:
                for line in a:
                    b = re.sub(r'\n\s*\n', r' ', line.get_text().strip(), flags=re.M)
                    c = re.sub(r'\n', r' ', b)
                    g = [float(s) for s in re.findall(r'-?\d+\.?\d*', c)]
                    if len(g) > 1:
                        for j in range(len(g) - 1):
                            try:
                                # Majority of coords in RU: lat in [40-80], long in [20-180],
                                # expected minimal format = XX.XXX
                                if 3 < (g[j] // 10) < 8 and len(str(g[j])) > 5 and 1 < (g[j + 1] // 10) < 19 and len(
                                        str(g[j + 1])) > 5:
                                    lat = g[j]
                                    lon = g[j + 1]
                                    coord_type = '3. deleted coord'
                            except Exception as e2:
                                logging.info('DBG.P.36.EXC. Coords-1:')
                                logging.exception(e2)
        except Exception as e:
            logging.info('Mike, here is an exception 3')
            logging.exception(e)
            pass

    # FOURTH CASE = COORDINATES FROM ADDRESS
    if lat == 0:
        try:
            address = parse_address_from_title(title)
            save_place_in_psql(address)
            lat, lon = get_coordinates_from_address(address)
            if lat != 0:
                coord_type = '4. coordinates by address'
        except Exception as e5:
            logging.info('DBG.P.42.EXC:')
            logging.exception(e5)

    # TODO: needed debug?
    # DEBUG - function execution time counter
    func_finish = datetime.now()
    func_execution_time_ms = func_finish - func_start
    logging.info(f'DBG.P.5.parse_coordinates() exec time: {func_execution_time_ms}')
    # DEBUG - function execution time counter

    return [lat, lon, coord_type]


def update_coordinates(parsed_summary):
    global db

    for i in range(len(parsed_summary)):
        if parsed_summary[i][2] == 'Ищем':
            logging.info(f'Mike, for this search coordinates should be saved {parsed_summary[i][1]}')
            coords = parse_coordinates(parsed_summary[i][1])

            if coords[0] != 0 and coords[1] != 0:
                with db.connect() as conn:
                    stmt = sqlalchemy.text(
                        "SELECT search_id FROM search_coordinates WHERE search_id=:a LIMIT 1;"
                    )
                    if_is_in_db = conn.execute(stmt, a=parsed_summary[i][1]).fetchone()
                    if if_is_in_db is None:
                        stmt = sqlalchemy.text(
                            """INSERT INTO search_coordinates (search_id, latitude, longitude, coord_type) VALUES (:a, 
                            :b, :c, :d); """
                        )
                        conn.execute(stmt, a=parsed_summary[i][1], b=coords[0], c=coords[1], d=coords[2])
    return None


def publish_to_pubsub(topic_name, message):
    """publish a message to specific pub/sub topic"""

    global project_id

    # Prepare to turn to the existing pub/sub topic
    topic_path = publisher.topic_path(project_id, topic_name)

    # Prepare the message
    message_json = json.dumps({'data': {'message': message}, })
    message_bytes = message_json.encode('utf-8')

    # Publish a message
    try:
        publish_future = publisher.publish(topic_path, data=message_bytes)
        publish_future.result()  # Verify the publishing succeeded
        logging.info('DBG.P.3: Pub/sub message published')
        logging.info('publish_future_.result(): ' + str(publish_future.result()))

    except Exception as e:
        logging.info('DBG.P.3.ERR: pub/sub NOT published')
        logging.exception(e)

    return None


def notify_admin(message):
    """send the pub/sub message to Debug to Admin"""

    publish_to_pubsub('topic_notify_admin', message)

    return None


def process_pubsub_message(event):
    """convert incoming pub/sub message into regular data"""

    # receiving message text from pub/sub
    if 'data' in event:
        received_message_from_pubsub = base64.b64decode(event['data']).decode('utf-8')
        logging.info('received_message_from_pubsub: ' + str(received_message_from_pubsub))
    elif 'message' in event:
        received_message_from_pubsub = base64.b64decode(event).decode('utf-8')
    else:
        received_message_from_pubsub = 'I cannot read message from pub/sub'
        logging.info(received_message_from_pubsub)
    encoded_to_ascii = eval(received_message_from_pubsub)
    logging.info('encoded_to_ascii: ' + str(encoded_to_ascii))
    try:
        data_in_ascii = encoded_to_ascii['data']
        logging.info('data_in_ascii: ' + str(data_in_ascii))
        message_in_ascii = data_in_ascii['message']
        logging.info('message_in_ascii: ' + str(message_in_ascii))
    except Exception as es:
        message_in_ascii = None
        logging.info('exception happened: ')
        logging.exception(str(es))

    return message_in_ascii


def sql_connect():
    """set the connection pool to cloud sql"""

    db_user = get_secrets("cloud-postgres-username")
    db_pass = get_secrets("cloud-postgres-password")
    db_name = get_secrets("cloud-postgres-db-name")
    db_conn = get_secrets("cloud-postgres-connection-name")
    db_socket_dir = "/cloudsql"

    db_config = {
        "pool_size": 30,
        "max_overflow": 0,
        "pool_timeout": 10,  # seconds
        "pool_recycle": 0,  # seconds
    }

    pool = sqlalchemy.create_engine(
        sqlalchemy.engine.url.URL(
            "postgresql+pg8000",
            username=db_user,
            password=db_pass,
            database=db_name,
            query={
                "unix_sock": "{}/{}/.s.PGSQL.5432".format(
                    db_socket_dir,
                    db_conn)
            }
        ),
        **db_config
    )
    pool.dialect.description_encoding = None

    return pool


def get_secrets(secret_request):
    """get the secret stored in Google Cloud Secrets"""

    name = f"projects/{project_id}/secrets/{secret_request}/versions/latest"
    response = client.access_secret_version(name=name)

    return response.payload.data.decode("UTF-8")


def update_checker(current_hash, folder_num):
    """compare prev snapshot and freshly-parsed snapshot, returns NO or YES and Previous hash"""

    global db

    # pre-set default output from the function
    update_trigger = 'no'

    # read the previous snapshot from Storage and save it as output[1]
    previous_hash = read_snapshot_from_cloud_storage('bucket_for_snapshot_storage', folder_num)

    # if new snapshot differs from the old one – then let's update the old with the new one
    if current_hash != previous_hash:
        # update hash in Storage
        write_snapshot_to_cloud_storage('bucket_for_snapshot_storage', current_hash, folder_num)

        update_trigger = 'yes'

    return update_trigger, previous_hash


def define_family_name_from_search_title_new(title, printit=False):
    """Define the family name of the lost person out ot search' title.
    It is very basic method which works in 99% of cases.
    Probably in the future more complicated model will be implemented"""

    global dict_status_words
    global dict_ignore

    string_by_word = None

    # Can work with input as string or list
    if isinstance(title, str):
        string_by_word = re.split(r"[;,.!\s]\s*", title)

    elif isinstance(title, list):
        string_by_word = title

    else:
        string_by_word = title
        logging.info(type(title))

    title_wo_status = []

    for word in string_by_word:
        if word.strip().lower() not in dict_status_words and word.strip().lower() not in dict_ignore:
            title_wo_status.append(word)
    if printit:
        logging.info(f'title wo status= {title_wo_status}')

    if title_wo_status[0].isnumeric():
        fam_name = title_wo_status[0] + ' ' + title_wo_status[1]
    else:
        fam_name = title_wo_status[0]
    if printit:
        logging.info(f'fam_nam= {fam_name}')

    # TODO: is it still a relevant case?
    # if by mistake the last symbol is "("
    # if fam_name[-1] == '(':
    #    fam_name = fam_name[0:-1]

    return fam_name


def define_age_from_search_title(search_title):
    """finds the age from the search' title"""
    # it's really simple now and gets just a first number out of all – but this simple solution seems to work well
    # probably in the future we'd need to have an ML model to define age more accurately

    # MEMO: int(float(s)) is required to overcome errors for cases "blah-blah 3."
    list_of_numbers_in_title = [int(float(s)) for s in re.findall(r'-?\d+\.?\d*', search_title)]

    # if there are several numbers in title - age is often written first
    if list_of_numbers_in_title:
        search_person_age = list_of_numbers_in_title[0]
    else:
        search_person_age = 0

    # if the first number is year - change to age itself
    if search_person_age > 1900:
        search_person_age = datetime.now().year - search_person_age

    return search_person_age


def define_status_from_search_title(title):
    """define the status from search' title"""

    search_status = title

    # Identify and delete the text of text for Training activities
    if search_status.lower().find('учебн') > -1:
        search_status = search_status.replace('Учебные сборы ', '')
        search_status = search_status.replace('Учебный поиск ', '')
        search_status = search_status.replace('Учебный выход', '')
        search_status = search_status.replace('Учебный ', '')
        search_status = search_status.replace('Учебная ', '')
        search_status = search_status.replace('УЧЕБНАЯ. ', '')
        search_status = search_status.replace('УЧЕБНАЯ: ', '')
        search_status = search_status.replace('УЧЕБНАЯ ', '')
        search_status = search_status.replace('УЧЕБНЫЙ. ', '')
        search_status = search_status.replace('УЧЕБНЫЙ.', '')
        search_status = search_status.replace('УЧЕБНЫЙ ', '')
        search_status = search_status.replace('УЧЕБНЫЙ', '')

    if search_status[0:3].lower() == "жив":
        search_status = "НЖ"
    elif search_status[0:3].lower() == "най":
        if search_status.split()[1].lower()[0:3] == "пог":
            search_status = "НП"
        else:
            search_status = "НЖ"
    elif search_status[0:3].lower() == "пог":
        search_status = "НП"
    elif search_status[0:3].lower() == "сто":
        search_status = "СТОП"
    elif search_status[0:3].lower() == "эва":
        search_status = "ЭВАКУАЦИЯ"
    elif search_status[0:14].lower() == "поиск приостан":
        search_status = "СТОП"
    elif search_status[0:12].lower() == "поиск заверш":
        search_status = "Завершен"
    elif search_status[0:21].lower() == "потеряшки в больницах":
        search_status = "не показываем"
    elif search_status[0:12].lower() == "поиск родных":
        search_status = "не показываем"
    elif search_status[0:14].lower() == "родные найдены":
        search_status = "не показываем"
    elif search_status[0:19].lower() == "поиск родственников":
        search_status = "не показываем"
    else:
        search_status = 'Ищем'

    return search_status


def define_start_time_of_search(blocks):
    """define search start time & date"""

    start_datetime_as_string = blocks.find('div', 'topic-poster responsive-hide left-box')
    start_datetime = start_datetime_as_string.time['datetime']

    return start_datetime


# TODO: Not in use now - TBD for future
def define_last_post_parameters(blocks):
    """WIP – trying to define the list of parameters of the last post for every search"""

    try:
        last_post_block = blocks.find_all('dd', 'lastpost')
        # -- WIP -- Was trying to get the last post & author - still WIP
        # last_post_author_block = str(last_post_block.find('a', 'username').text)
        # last_post_time = str(last_post_block.find('time').text)
        # last_post_plain_text = last_post_author_block + ', ' + last_post_time
    except Exception as e:
        logging.info('Exception happened 6')
        logging.exception(e)
        last_post_block = ''

    return last_post_block


# TODO: under construction
def profile_get_search_events(first_post_text):
    """TBD"""

    return None


def profile_get_type_of_activity(text_of_activity):
    """get the status of the search activities: is there HQ, is there Active duties"""

    activity_type = []
    hq = None

    # Cases with HQ
    if text_of_activity.lower().find('штаб свернут') > -1:
        hq = 'no'
    elif text_of_activity.lower().find('штаб свёрнут') > -1:
        hq = 'no'
    elif text_of_activity.lower().find('штаб свëрнут') > -1:
        hq = 'no'

    if hq == 'no':
        activity_type.append('9 - hq closed')
    else:
        if text_of_activity.lower().find('сбор') > -1:
            hq = 'now'
        elif text_of_activity.lower().find('штаб работает') > -1:
            hq = 'now'
        elif text_of_activity.lower().find('выезд сейчас') > -1:
            hq = 'now'
        elif text_of_activity.lower().find('внимание, выезд') > -1:
            hq = 'now'
        elif text_of_activity.lower().find('внимание выезд') > -1:
            hq = 'now'
        elif text_of_activity.lower().find('внимание! выезд') > -1:
            hq = 'now'

        if hq == 'now':
            activity_type.append('1 - hq now')
        else:
            if text_of_activity.lower().find('штаб мобильный') > -1:
                hq = 'mobile'

            if hq == 'mobile':
                activity_type.append('2 - hq mobile')
            else:
                if text_of_activity.lower().find('выезд ожидается') > -1:
                    hq = 'will'
                elif text_of_activity.lower().find('ожидается выезд') > -1:
                    hq = 'will'
                elif text_of_activity.lower().find('выезд планируется') > -1:
                    hq = 'will'
                elif text_of_activity.lower().find('планируется выезд') > -1:
                    hq = 'will'
                elif text_of_activity.lower().find('готовится выезд') > -1:
                    hq = 'will'
                elif text_of_activity.lower().find('выезд готовится') > -1:
                    hq = 'will'

                if hq == 'will':
                    activity_type.append('1 - hq will')

    # Cases with Autonom
    if hq not in {'mobile, now, will'}:
        if text_of_activity.lower().find('опрос') > -1:
            hq = 'autonom'
        if text_of_activity.lower().find('оклейка') > -1:
            hq = 'autonom'
    if text_of_activity.lower().find('автоном') > -1 and not text_of_activity.lower().find('нет автоном'):
        hq = 'autonom'
    elif text_of_activity.lower().find('двойк') > -1:
        hq = 'autonom'

    if hq == 'autonom':
        activity_type.append('6 - autonom')

    # Specific Tasks
    if text_of_activity.lower().find('забрать оборудование') > -1:
        activity_type.append('3 - hardware logistics')
    elif text_of_activity.lower().find('забрать комплект оборудования') > -1:
        activity_type.append('3 - hardware logistics')
    # if text_of_activity.lower().find('ориентировки') > -1:
    #    activity_type.append('4 - orientation logistics')

    # if text_of_activity.lower().find('репост') > -1:
    #    activity_type.append('8 - info')

    # delete duplicates if any through conversion to set and back to list + sort
    # activity_type = list(set(activity_type))
    activity_type.sort()

    return activity_type


def profile_get_managers(text_of_managers):
    """define list of managers out of profile plain text"""

    managers = []

    try:
        list_of_lines = text_of_managers.split("\n")

        # Define the block of text with managers which starts with ------
        zero_line = None
        for i in range(len(list_of_lines)):
            if list_of_lines[i].find('--------') > -1:
                zero_line = i + 1
                break

        # If there's a telegram link in a new line - to move it to prev line
        for i in range(len(list_of_lines) - 1):
            if list_of_lines[i + 1][0:21] == 'https://telegram.im/@':
                list_of_lines[i] += ' ' + list_of_lines[i + 1]
                list_of_lines[i + 1] = ''
            if list_of_lines[i + 1][0:14] == 'https://t.me/':
                list_of_lines[i] += ' ' + list_of_lines[i + 1]
                list_of_lines[i + 1] = ''

        list_of_roles = ['Координатор-консультант', 'Координатор', 'Инфорг', 'Старшая на месте', 'Старший на месте',
                         'ДИ ', 'СНМ']

        for line in list_of_lines[zero_line:]:
            line_by_word = line.split()
            for i in range(len(line_by_word)):

                for role in list_of_roles:
                    if str(line_by_word[i]).find(role) > -1:
                        manager_line = line_by_word[i]
                        for j in range(len(line_by_word) - i - 1):
                            if line_by_word[i + j + 1].find(role) == -1:
                                manager_line += ' ' + str(line_by_word[i + j + 1])
                            else:
                                break

                        # Block of minor RARE CASE corrections
                        manager_line = manager_line.replace(',,', ',')
                        manager_line = manager_line.replace(':,', ':')
                        manager_line = manager_line.replace(', ,', ',')
                        manager_line = manager_line.replace('  ', ' ')

                        # Block of phone number substitution with clickable link
                        # TODO: turned out "tel:" protocol does not work in telegram,
                        #  and phone numbers are maid clickable only if the message is
                        #  short and it's user device who decides if number should be marked up
                        #  as tel: link or not. So it is not controllable – thus tel: functionality was excluded
                        """nums = re.findall(
                            r'(?:\+7|7|8)[\s]?[\s\-(]?[\s]?[\d]{3}[\s\-)]?[\s]?[\d]{3}[\s\-]?[\d]{2}[\s\-]?[\d]{2}',
                            manager_line)
                        for num in nums:
                            manager_line = manager_line.replace(num,
                                                                '<a href="tel:' + str(num) + '">' + str(num) + '</a>')
"""
                        managers.append(manager_line)
                        break

        # replace telegram contacts with nice links
        for i in range(len(managers)):
            for word in managers[i].split(' '):

                nickname = None

                if word.find('https://telegram.im/') > -1:
                    nickname = word[20:]

                if word.find('https://t.me/') > -1:
                    nickname = word[13:]

                if nickname:

                    # tip: sometimes there are two @ in the beginning (by human mistake)
                    while nickname[0] == '@':
                        nickname = nickname[1:]

                    # tip: sometimes the last symbol is wrong
                    while nickname[-1:] in {'.', ',', ' '}:
                        nickname = nickname[:-1]

                    managers[i] = managers[i].replace(word, f'<a href="https://t.me/{nickname}">@{nickname}</a>')

        """DBG"""
        logging.info('DBG.P.101.Managers_list:')
        for manager in managers:
            logging.info(manager)
        """DBG"""

    except Exception as e:
        logging.info('DBG.P.102.EXC:')
        logging.exception(e)

    return managers


def parse_search_profile(search_num):
    """get search activities list"""

    global block_of_profile_rough_code
    global requests_session

    url_beginning = 'https://lizaalert.org/forum/viewtopic.php?t='
    url_to_topic = url_beginning + str(search_num)

    try:
        r = requests_session.get(url_to_topic)  # noqa
        soup = BeautifulSoup(r.content, features="html.parser")

    except Exception as e:
        logging.info(f'DBG.P.50.EXC: unable to parse a specific thread with address: {url_to_topic} error:')
        logging.exception(e)
        soup = None

    # open the first post
    block_of_profile_rough_code = soup.find('div', 'content')

    # excluding <line-through> tags
    for deleted in block_of_profile_rough_code.findAll('span', {'style': 'text-decoration:line-through'}):
        deleted.extract()

    # add telegram links to text (to be sure next step won't cut these links), type 1
    for a_tag in block_of_profile_rough_code.find_all('a'):
        if a_tag.get('href')[0:20] == 'https://telegram.im/':
            a_tag.replace_with(a_tag['href'])

    # add telegram links to text (to be sure next step won't cut these links), type 2
    for a_tag in block_of_profile_rough_code.find_all('a'):
        if a_tag.get('href')[0:13] == 'https://t.me/':
            a_tag.replace_with(a_tag['href'])

    left_text = block_of_profile_rough_code.text.strip()

    """DEBUG"""
    logging.info('DBG.Profile:' + left_text)
    """DEBUG"""

    return left_text


def parse(folder_num):
    """key function to parse forum folders with searches' summaries"""

    global requests_session

    parsed_summary_page = []
    parsed_without_date = []
    current_datetime = datetime.now()
    db_timestamp = str(current_datetime.strftime("%d-%b %H:%M"))
    url = 'https://lizaalert.org/forum/viewforum.php?f=' + str(folder_num)
    try:
        r = requests_session.get(url, timeout=10)  # for every folder - req'd daily at night forum update # noqa

        only_tag = SoupStrainer('div', {'class': 'forumbg'})
        soup = BeautifulSoup(r.content, features='lxml', parse_only=only_tag)
        del r  # trying to free up memory
        search_code_blocks = soup.find_all('dl', 'row-item')
        del soup  # trying to free up memory

        for i in range(len(search_code_blocks) - 1):

            # Current block which contains everything regarding certain search
            data_block = search_code_blocks[i + 1]

            # In rare cases there are aliases from other folders, which have static titles – and we're avoiding them
            if str(data_block).find('<dl class="row-item topic_moved">') > -1:
                continue

            search_title_block = data_block.find('a', 'topictitle')
            search_long_link = search_title_block['href'][1:]

            search_title = search_title_block.next_element

            # rare case: cleaning [size][b]...[/b][/size] tags
            search_title = search_title.replace('[b]', '', 1)
            search_title = search_title.replace('[/b]', '', 1)
            search_title = search_title.replace('[size=140]', '', 1)
            search_title = search_title.replace('[/size]', '', 1)

            # Some forum folders contain sid, some not
            sid = search_long_link.find('&sid')
            if sid == -1:
                search_cut_link = search_long_link
            else:
                search_cut_link = search_long_link[0:sid]
            search_id = search_cut_link[(search_cut_link.find('&t=') + 3):]

            search_replies_num = int(data_block.find('dd', 'posts').next_element)

            person_fam_name = define_family_name_from_search_title_new(search_title)
            person_age = define_age_from_search_title(search_title)
            start_datetime = define_start_time_of_search(data_block)
            search_status_short = define_status_from_search_title(search_title)

            # TODO: exclusion should be on another level (by user preferences)
            # exclude non-relevant searches
            if search_status_short != "не показываем":
                search_summary = [current_datetime, search_id, search_status_short, search_title, search_cut_link,
                                  start_datetime, search_replies_num, person_age, person_fam_name, folder_num]
                parsed_summary_page.append(search_summary)

                parsed_wo_date = [search_title, search_replies_num]
                parsed_without_date.append(parsed_wo_date)

        del search_code_blocks

    # To catch timeout once a day in the night
    except requests.exceptions.Timeout as e:
        logging.info('DBG.P.31.Timeout:')
        logging.exception(e)
        parsed_summary_page = []
    except ConnectionResetError as e:
        logging.info('there is a connection error:' + repr(e) + db_timestamp)
        parsed_summary_page = []
    except Exception as e:
        logging.info('DBG.P.30.ERR in Parsing summary page:' + repr(e) + db_timestamp)
        parsed_summary_page = []

    """DEBUG"""
    # if folder_num not in {276, 41}:
    logging.info('DBG.P.29.Parsed_summary_page:\n' + str(parsed_summary_page))
    """DEBUG"""

    return [parsed_summary_page, parsed_without_date]


def parse_one_comment(search_num, comment_num):
    global db
    global requests_session

    url = 'https://lizaalert.org/forum/viewtopic.php?'
    comment_url = url + '&t=' + str(search_num) + '&start=' + str(comment_num)
    there_are_inforg_comments = False
    comment_author_nickname = None
    try:
        r = requests_session.get(comment_url)  # noqa
        soup = BeautifulSoup(r.content, features='lxml')
        search_code_blocks = soup.find('div', 'post')

        # finding USERNAME
        comment_author_block = search_code_blocks.find('a', 'username')
        try:
            comment_author_nickname = comment_author_block.text
        except Exception as e:
            logging.info('Here is an exception 7 for search ' + str(search_num) + ', and comment ' +
                         str(comment_num) +
                         ' error: ' + repr(e))
            try:
                comment_author_nickname = search_code_blocks.find('a', 'username-coloured').text
            except Exception as e2:
                logging.info('Mike, here is an exception 8' + repr(e2))
                comment_author_nickname = 'unidentified_username'

        if comment_author_nickname[:6].lower() == 'инфорг':
            there_are_inforg_comments = True

        # finding LINK to user profile
        try:
            comment_author_link = int("".join(filter(str.isdigit, comment_author_block['href'][36:43])))

        except Exception as e:
            logging.info('Here is an exception 9 for search ' + str(search_num) + ', and comment ' +
                         str(comment_num) +
                         ' error: ' + repr(e))
            try:
                comment_author_link = int(
                    "".join(filter(str.isdigit, search_code_blocks.find('a', 'username-coloured')['href'][36:43])))
            except Exception as e2:
                logging.info('Here is an exception 10' + repr(e2))
                comment_author_link = 'unidentified_link'

        # finding the global comment NUMBER
        comment_global_num = search_code_blocks.find('p', 'author').findNext('a')['href'][-7:]

        # finding TEXT of the comment
        comment_text_0 = search_code_blocks.find('div', 'content')
        try:
            external_span = comment_text_0.blockquote.extract()
            comment_text_1 = comment_text_0.text
        except Exception as e:
            logging.info('Mike, here is an exception 11 for search ' + str(search_num) + ', and comment ' +
                         str(comment_num) +
                         ' error: ' + repr(e))
            comment_text_1 = comment_text_0.text
        comment_text = " ".join(comment_text_1.split())

        # Define exclusions (comments of Inforg with "резерв" and "рассылка билайн"
        ignore = False
        if there_are_inforg_comments:
            if comment_text.lower()[0:6] == 'резерв' or comment_text.lower()[0:15] == 'рассылка билайн':
                ignore = True

        with db.connect() as conn:

            # TODO remove doubling once it'll work correctly
            try:
                if comment_text:
                    if not ignore:
                        stmt = sqlalchemy.text(
                            """INSERT INTO comments (comment_url, comment_text, comment_author_nickname, 
                            comment_author_link, search_forum_num, comment_num) values (:a, :b, :c, :d, :e, :f); """
                        )
                        conn.execute(stmt, a=comment_url, b=comment_text, c=comment_author_nickname,
                                     d=comment_author_link, e=search_num, f=comment_num)
                    else:
                        stmt = sqlalchemy.text(
                            """INSERT INTO comments (comment_url, comment_text, comment_author_nickname, 
                            comment_author_link, search_forum_num, comment_num, notification_sent) 
                            values (:a, :b, :c, :d, :e, :f, :g); """
                        )
                        conn.execute(stmt, a=comment_url, b=comment_text, c=comment_author_nickname,
                                     d=comment_author_link, e=search_num, f=comment_num, g='n')

            except Exception as e3:
                logging.info('DBG.P.106.EXC:' + repr(e3))
                stmt = sqlalchemy.text(
                    """INSERT INTO comments (comment_url, comment_text, comment_author_nickname, comment_author_link, 
                    search_forum_num, comment_num) values (:a, :b, :c, :d, :e, :f); """
                )
                conn.execute(stmt, a=comment_url, b=comment_text, c=comment_author_nickname, d=comment_author_link,
                             e=search_num, f=comment_num)

    except ConnectionResetError:
        logging.info('There is a connection error')

    return there_are_inforg_comments


def process_delta(folder_num):
    """update of SQL tables 'searches' and 'change_log' on the changes vs previous parse"""

    global db

    # DEBUG - function execution time counter
    func_start = datetime.now()
    # DEBUG - function execution time counter

    with db.connect() as conn:

        sql_text = sqlalchemy.text(
            """SELECT search_forum_num, parsed_time, status_short, forum_search_title, cut_link, search_start_time, 
            num_of_replies, id, age, family_name, forum_folder_id FROM forum_summary_snapshot WHERE 
            forum_folder_id = :a; """
        )
        snapshot = conn.execute(sql_text, a=folder_num).fetchall()

        searches_full_list = conn.execute(
            """SELECT search_forum_num, parsed_time, status_short, forum_search_title, cut_link, search_start_time, 
            num_of_replies, family_name, age, id, forum_folder_id FROM searches;"""
        ).fetchall()

        '''1. move UPD to Change Log'''
        change_log_updates = []
        there_are_inforg_comments = False
        for i in range(len(snapshot)):
            snpsht = list(snapshot[i])
            for j in range(len(searches_full_list)):
                srchs = list(searches_full_list[j])
                if snpsht[0] == srchs[0]:
                    if snpsht[2] != srchs[2]:
                        change_log_updates.append([snpsht[1], snpsht[0], 'status_change', snpsht[2], '', 1])
                    if snpsht[3] != srchs[3]:
                        change_log_updates.append([snpsht[1], snpsht[0], 'title_change', snpsht[3], '', 2])
                    # in case of number of COMMENTS changes
                    if int(snpsht[6]) > int(srchs[6]):
                        for k in range(snpsht[6] - srchs[6]):
                            flag_if_comment_was_from_inforg = parse_one_comment(snpsht[0], int(srchs[6]) + 1 + k)
                            if flag_if_comment_was_from_inforg:
                                there_are_inforg_comments = True
                        change_log_updates.append([snpsht[1], snpsht[0], 'replies_num_change', snpsht[6], '', 3])

                        try:
                            if there_are_inforg_comments:
                                change_log_updates.append([snpsht[1], snpsht[0], 'inforg_replies', snpsht[6], '', 4])
                        except Exception as e:
                            logging.info('DBG.P.58:' + repr(e))
        if change_log_updates:
            stmt = sqlalchemy.text(
                """INSERT INTO change_log (parsed_time, search_forum_num, changed_field, new_value, parameters, 
                change_type) values (:a, :b, :c, :d, :e, :f); """
            )
            for i in range(len(change_log_updates)):
                conn.execute(stmt, a=change_log_updates[i][0], b=change_log_updates[i][1], c=change_log_updates[i][2],
                             d=change_log_updates[i][3], e=change_log_updates[i][4], f=change_log_updates[i][5])

        '''2. move ADD to Change Log '''
        new_searches_from_snapshot = []
        for i in range(len(snapshot)):
            new_search_flag = 1
            for j in range(len(searches_full_list)):
                if snapshot[i][0] == searches_full_list[j][0]:
                    new_search_flag = 0
                    break

            if new_search_flag == 1:
                new_searches_from_snapshot.append(
                    [snapshot[i][0], snapshot[i][1], snapshot[i][2], snapshot[i][3], snapshot[i][4], snapshot[i][5],
                     snapshot[i][6], snapshot[i][8], snapshot[i][9], snapshot[i][10]])

        change_log_new_searches = []
        for i in range(len(new_searches_from_snapshot)):
            change_log_new_searches.append(
                [new_searches_from_snapshot[i][1], new_searches_from_snapshot[i][0],
                 "new_search", new_searches_from_snapshot[i][3], 0])
        if change_log_new_searches:
            stmt = sqlalchemy.text(
                """INSERT INTO change_log (parsed_time, search_forum_num, changed_field, new_value, change_type) 
                values (:a, :b, :c, :d, :e);"""
            )
            for i in range(len(change_log_new_searches)):
                conn.execute(stmt, a=change_log_new_searches[i][0], b=change_log_new_searches[i][1],
                             c=change_log_new_searches[i][2], d=change_log_new_searches[i][3],
                             e=change_log_new_searches[i][4])

        '''3. ADD to Searches'''
        if new_searches_from_snapshot:
            stmt = sqlalchemy.text(
                """INSERT INTO searches (search_forum_num, parsed_time, status_short, forum_search_title, cut_link, 
                search_start_time, num_of_replies, age, family_name, forum_folder_id) values (:a, :b, :c, :d, :e, :f, 
                :g, :h, :i, :j); """
            )
            for i in range(len(new_searches_from_snapshot)):
                conn.execute(stmt, a=new_searches_from_snapshot[i][0], b=new_searches_from_snapshot[i][1],
                             c=new_searches_from_snapshot[i][2], d=new_searches_from_snapshot[i][3],
                             e=new_searches_from_snapshot[i][4], f=new_searches_from_snapshot[i][5],
                             g=new_searches_from_snapshot[i][6], h=new_searches_from_snapshot[i][7],
                             i=new_searches_from_snapshot[i][8], j=new_searches_from_snapshot[i][9])

            # TODO testing of parsing all the parameters of the new searches
            try:
                for i in range(len(new_searches_from_snapshot)):
                    search_num = new_searches_from_snapshot[i][0]

                    parsed_profile_text = parse_search_profile(search_num)
                    search_activities = profile_get_type_of_activity(parsed_profile_text)
                    # search_events = profile_get_search_events(parsed_profile_text)
                    """DBG"""
                    logging.info('DBG.P.103:Search activities:' + str(search_activities))
                    """DBG"""

                    # mark all old activities as deactivated
                    sql_text = sqlalchemy.text(
                        """UPDATE search_activities SET activity_status = 'deactivated' WHERE search_forum_num=:a; """
                    )
                    conn.execute(sql_text, a=search_num)

                    # add the latest activities for the search
                    for j in range(len(search_activities)):
                        sql_text = sqlalchemy.text(
                            """INSERT INTO search_activities (search_forum_num, activity_type, activity_status, 
                            timestamp) values ( :a, :b, :c, :d); """
                        )
                        conn.execute(sql_text, a=search_num, b=search_activities[j], c='ongoing', d=datetime.now())

                    # Define managers of the search
                    managers = profile_get_managers(parsed_profile_text)

                    """DBG"""
                    logging.info('DBG.P.104:Managers:' + str(managers))
                    """DBG"""

                    if managers:
                        try:
                            sql_text = sqlalchemy.text(
                                """INSERT INTO search_attributes (search_forum_num, attribute_name, attribute_value, 
                                timestamp) values ( :a, :b, :c, :d); """
                            )
                            conn.execute(sql_text, a=search_num, b='managers', c=str(managers), d=datetime.now())
                        except Exception as e:
                            logging.info('DBG.P.104:' + repr(e))

            except Exception as e:
                logging.info('DBG.P.52.EXC:' + repr(e))

        '''4 DEL UPD from Searches'''
        delete_lines_from_summary = []

        for i in range(len(snapshot)):
            snpsht = list(snapshot[i])
            for j in range(len(searches_full_list)):
                srchs = list(searches_full_list[j])
                if snpsht[0] == srchs[0]:
                    if snpsht[2] != srchs[2] or snpsht[3] != srchs[3] or snpsht[6] != srchs[6]:
                        delete_lines_from_summary.append(snpsht[0])

        if delete_lines_from_summary:
            stmt = sqlalchemy.text(
                "DELETE FROM searches WHERE search_forum_num=:a;"
            )
            for i in range(len(delete_lines_from_summary)):
                conn.execute(stmt, a=int(delete_lines_from_summary[i]))

        '''5. UPD added to Searches'''
        searches_full_list = conn.execute(
            """SELECT search_forum_num, parsed_time, status_short, forum_search_title, cut_link, search_start_time, 
            num_of_replies, family_name, age, id, forum_folder_id FROM searches;"""
        ).fetchall()

        new_searches_from_snapshot = []
        for i in range(len(snapshot)):
            snpsht = list(snapshot[i])
            new_search_flag = 1
            for j in range(len(searches_full_list)):
                srchs = list(searches_full_list[j])
                if snpsht[0] == srchs[0]:
                    new_search_flag = 0
                    break
            if new_search_flag == 1:
                new_searches_from_snapshot.append(
                    [snpsht[0], snpsht[1], snpsht[2], snpsht[3], snpsht[4], snpsht[5], snpsht[6], snpsht[8], snpsht[9],
                     snpsht[10]])
        if new_searches_from_snapshot:
            stmt = sqlalchemy.text(
                """INSERT INTO searches (search_forum_num, parsed_time, status_short, forum_search_title, cut_link, 
                search_start_time, num_of_replies, age, family_name, forum_folder_id) values (:a, :b, :c, :d, :e, :f, 
                :g, :h, :i, :j); """

            )
            for i in range(len(new_searches_from_snapshot)):
                conn.execute(stmt, a=new_searches_from_snapshot[i][0], b=new_searches_from_snapshot[i][1],
                             c=new_searches_from_snapshot[i][2], d=new_searches_from_snapshot[i][3],
                             e=new_searches_from_snapshot[i][4], f=new_searches_from_snapshot[i][5],
                             g=new_searches_from_snapshot[i][6], h=new_searches_from_snapshot[i][7],
                             i=new_searches_from_snapshot[i][8], j=new_searches_from_snapshot[i][9])

    # DEBUG - function execution time counter
    func_finish = datetime.now()
    func_execution_time_ms = func_finish - func_start
    logging.info('DBG.P.5.process_delta() exec time:' + str(func_execution_time_ms))
    # DEBUG - function execution time counter

    return None


def rewrite_snapshot_in_sql(parsed_summary, folder_num):
    """rewrite the freshly-parsed snapshot into sql table 'forum_summary_snapshot'"""

    global db
    db = sql_connect()

    with db.connect() as conn:
        sql_text = sqlalchemy.text(
            """DELETE FROM forum_summary_snapshot WHERE forum_folder_id = :a;"""
        )
        conn.execute(sql_text, a=folder_num)

        sql_text = sqlalchemy.text(
            """INSERT INTO forum_summary_snapshot (search_forum_num, parsed_time, status_short, forum_search_title, 
            cut_link, search_start_time, num_of_replies, age, family_name, forum_folder_id) values (:a, :b, 
            :c, :d, :e, :f, :g, :h, :i, :j); """
        )
        for i in range(len(parsed_summary[0])):
            line_of_pars_sum = list(parsed_summary[0][i])
            conn.execute(sql_text, a=line_of_pars_sum[1], b=line_of_pars_sum[0], c=line_of_pars_sum[2],
                         d=line_of_pars_sum[3], e='', f=line_of_pars_sum[5], g=line_of_pars_sum[6],
                         h=line_of_pars_sum[7], i=line_of_pars_sum[8], j=line_of_pars_sum[9])

    return None


def process_one_folder(folder_to_parse):
    """is a key function for a single forum folder parsing & processing"""

    global db

    # parse a new version of summary page from the chosen folder
    parsed_summary = parse(folder_to_parse)
    logging.info('parsing of ' + str(folder_to_parse))
    logging.info(str(parsed_summary[0]))

    update_trigger = ''
    debug_message = ''

    # make comparison, record it in PSQL
    if parsed_summary[0]:

        # transform the current snapshot into the string to be able to compare it: string vs string
        prep_for_curr_snapshot_as_string = [y for x in parsed_summary[1] for y in x]
        curr_snapshot_as_string = ','.join(map(str, prep_for_curr_snapshot_as_string))

        # get the prev snapshot as string from cloud storage & get the trigger if there are updates at all
        update_trigger, prev_snapshot_as_string = update_checker(curr_snapshot_as_string, folder_to_parse)

        try:
            logging.info('update trigger: ' + str(update_trigger))
            logging.info('prev snapshot: ' + str(prev_snapshot_as_string))
        except:  # noqa
            logging.info('we are printing an exception')

        # only for case when current snapshot differs from previous
        if update_trigger == "yes":
            debug_message = 'DBG.P.2.folder ' + str(folder_to_parse) + ' YES - UPDATE\n' + debug_message

            rewrite_snapshot_in_sql(parsed_summary, folder_to_parse)

            """DEBUG"""
            logging.info('starting "process_delta" for folder' + str(folder_to_parse))
            """DEBUG"""

            process_delta(folder_to_parse)
            update_coordinates(parsed_summary[0])

        else:
            debug_message = 'DBG.P.2.folder ' + str(folder_to_parse) + ' NO - UPDATE\n' + debug_message
    logging.info(debug_message)

    return update_trigger, debug_message


def parse_and_upd_function(event, context):  # noqa
    """main function which starts every minute"""

    global db
    global requests_session

    requests_session = requests.Session()

    message_from_pubsub = process_pubsub_message(event)

    logging.info('event: ' + str(event))
    logging.info('message_from_pubsub: ' + str(message_from_pubsub))

    if message_from_pubsub:
        list_from_pubsub = ast.literal_eval(message_from_pubsub)
    else:
        list_from_pubsub = None
    folders_list = []

    if list_from_pubsub:
        for line in list_from_pubsub:
            folders_list.append(line[0])
        logging.info(f'folder_list_2:  {str(folders_list)}')

    """DEBUG"""
    # in order to separate different iterations in logs while Debugging
    logging.info('----------------------------------------------------')
    """DEBUG"""

    if not folders_list:

        # TODO: it's a theoretical scenario - need to understand if it happens at all
        publish_to_pubsub('topic_notify_admin', 'ERROR: parsing script received empty folders list')

        # The list to be checked every minute
        folders_list = [276, 41]

        minute_now = datetime.now().minute
        hours_now = datetime.now().hour

        # The folders to be checked every 15 minutes
        if minute_now % 15 == 0:
            folders_list.append(123)
            folders_list.append(333)
            folders_list.append(334)
            folders_list.append(177)

        if (minute_now + 3) % 15 == 0:
            folders_list.append(120)
            folders_list.append(143)
            folders_list.append(265)
            folders_list.append(121)

        if (minute_now + 6) % 15 == 0:
            folders_list.append(153)
            folders_list.append(162)
            folders_list.append(132)
            folders_list.append(293)

        if (minute_now + 8) % 15 == 0:
            folders_list.append(138)
            folders_list.append(371)

        # The folders to be checked every hour on 59 min
        if minute_now % 59 == 0 and hours_now == 23:
            folders_list.append(305)
            folders_list.append(300)
            folders_list.append(193)
            folders_list.append(372)
            folders_list.append(373)

            pass

    list_of_folders_with_updates = []
    for folder in folders_list:

        """DEBUG"""
        logging.info('DBG.P.31.Folder:' + str(folder))
        """DEBUG"""

        update_trigger, debug_message = process_one_folder(folder)

        if update_trigger == 'yes':
            list_of_folders_with_updates.append(folder)

    """DEBUG"""
    logging.info('Here\'s a list of folders with updates: ' + str(list_of_folders_with_updates))
    """DEBUG"""

    if list_of_folders_with_updates:
        # Download the actual Notification Config
        # This file is done for Canary Deployment of the new version of Notification script
        # Config defines the shares of users to be covered by Prod & Temp Staging Notification scripts
        notifications_config_text = read_yaml_from_cloud_storage('bucket_for_ad_hoc', 'config_notification_script.yml')
        notifications_config = yaml.safe_load(notifications_config_text)
        publish_to_pubsub('topic_for_notification', str(notifications_config))

        """DEBUG"""
        logging.info('Here\'s notif config: ' + str(notifications_config))
        # notify_admin(notifications_config)
        """DEBUG"""

    # Close the open session
    requests_session.close()

    return None
