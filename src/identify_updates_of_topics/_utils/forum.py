import copy
import logging
import re

import requests
from bs4 import BeautifulSoup

from _dependencies.commons import Topics, publish_to_pubsub
from identify_updates_of_topics._utils.topics_commons import block_of_profile_rough_code, get_requests_session


def define_start_time_of_search(blocks):
    """define search start time & date"""

    start_datetime_as_string = blocks.find('div', 'topic-poster responsive-hide left-box')
    start_datetime = start_datetime_as_string.time['datetime']

    return start_datetime


def visibility_check(resp: requests.Response, topic_id) -> bool:
    """check topic's visibility: if hidden or deleted"""

    check_content = copy.copy(resp.content)
    check_content = check_content.decode('utf-8')
    check_content = None if re.search(r'502 Bad Gateway', check_content) else check_content
    site_unavailable = False if check_content else True
    topic_deleted = True if check_content and re.search(r'Запрошенной темы не существует', check_content) else False
    topic_hidden = (
        True
        if check_content and re.search(r'Для просмотра этого форума вы должны быть авторизованы', check_content)
        else False
    )
    if site_unavailable:
        return False
    elif topic_deleted or topic_hidden:
        visibility = 'deleted' if topic_deleted else 'hidden'
        publish_to_pubsub(Topics.topic_for_topic_management, {'topic_id': topic_id, 'visibility': visibility})
        # TODO can replace with direct sql query
        return False

    return True


def parse_search_profile(search_num) -> str | None:
    """get search activities list"""

    global block_of_profile_rough_code
    requests_session = get_requests_session()

    url_beginning = 'https://lizaalert.org/forum/viewtopic.php?t='
    url_to_topic = url_beginning + str(search_num)

    try:
        r = requests_session.get(url_to_topic)  # noqa
        if not visibility_check(r, search_num):
            return None

        soup = BeautifulSoup(r.content, features='html.parser')

    except Exception as e:
        logging.info(f'DBG.P.50.EXC: unable to parse a specific Topic with address: {url_to_topic} error:')
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

    return left_text


def profile_get_managers(text_of_managers: str) -> list[str]:
    """define list of managers out of profile plain text"""

    managers = []

    try:
        list_of_lines = text_of_managers.split('\n')

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

        list_of_roles = [
            'Координатор-консультант',
            'Координатор',
            'Инфорг',
            'Старшая на месте',
            'Старший на месте',
            'ДИ ',
            'СНМ',
        ]

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

                        managers.append(manager_line)
                        break

        # replace telegram contacts with nice links
        for manager in managers:
            for word in manager.split(' '):
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

                    manager = manager.replace(word, f'<a href="https://t.me/{nickname}">@{nickname}</a>')

        # FIXME – for debug
        logging.info('DBG.P.101.Managers_list:')
        for manager in managers:
            logging.info(manager)
        # FIXME ^^^

    except Exception as e:
        logging.info('DBG.P.102.EXC:')
        logging.exception(e)

    return managers


def profile_get_type_of_activity(text_of_activity: str) -> list[str]:
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

    activity_type.sort()

    return activity_type


def parse_address_from_title(initial_title: str) -> str:
    after_age = 0
    age_dict = [' год ', ' год', ' года ', ' года', ' лет ', ' лет', 'г.р.', '(г.р.),', 'лет)', 'лет,']
    for word in age_dict:
        age_words = initial_title.find(word)
        if age_words == -1:
            pass
        else:
            after_age = max(after_age, age_words + len(word))

    if after_age > 0:
        address_string = initial_title[after_age:].strip()
    else:
        numbers = [int(float(s)) for s in re.findall(r'\d*\d', initial_title)]
        if numbers and numbers[0]:
            age_words = initial_title.find(str(numbers[0]))
            if age_words == -1:
                address_string = initial_title
            else:
                after_age = age_words + len(str(numbers[0]))
                address_string = initial_title[after_age:].strip()
        else:
            address_string = initial_title

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
            if address_string[0 : len(word)] == word:
                trigger_of_useless_symbols = True
                address_string = address_string[len(word) :]

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
        for k in range(len(by_word) - 1):
            if by_word[k + 1] == 'района':
                prev_word = by_word[k]
                this_word = by_word[k + 1]
                break
        if prev_word and this_word:
            address_string = address_string.replace(prev_word, prev_word[:-3] + 'ий')
            address_string = address_string.replace(this_word, this_word[:-1])

    # case with 'области'
    if address_string.find('области') != -1:
        by_word = address_string.split()
        prev_word = None
        this_word = None
        for k in range(len(by_word) - 1):
            if by_word[k + 1] == 'области':
                prev_word = by_word[k]
                this_word = by_word[k + 1]
                break
        if prev_word and this_word:
            address_string = address_string.replace(prev_word, prev_word[:-2] + 'ая')
            address_string = address_string.replace(this_word, this_word[:-1] + 'ь')

    # add all the cases ABOVE
    # delete garbage in the beginning of string
    try:
        first_num = re.search(r'\d', address_string).start()
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
    if (
        address_string
        and address_string.lower().find('крым') == -1
        and address_string.lower().find('севастополь') == -1
    ):
        address_string = address_string[new_start:] + ', Россия'

    # case - first "с.", "п." and "д." are often misinterpreted - so it's easier to remove it
    wrong_first_symbols_dict = {
        ' ',
        ',',
        ')',
        '.',
        'с.',
        'д.',
        'п.',
        'г.',
        'гп',
        'пос.',
        'уч-к',
        'р,',
        'р.',
        'г,',
        'ст.',
        'л.',
        'дер ',
        'дер.',
        'пгт ',
        'ж/д',
        'б/о',
        'пгт.',
        'х.',
        'ст-ца',
        'с-ца',
        'стан.',
    }

    trigger_of_wrong_symbols = True

    while trigger_of_wrong_symbols:
        this_iteration_bring_no_changes = True

        for wrong_symbols in wrong_first_symbols_dict:
            if address_string[: len(wrong_symbols)] == wrong_symbols:
                # if the first symbols are from wrong symbols list - we delete them
                address_string = address_string[len(wrong_symbols) :]
                this_iteration_bring_no_changes = False

        if this_iteration_bring_no_changes:
            trigger_of_wrong_symbols = False

    # ONE-TIME EXCEPTIONS:
    if address_string.find('г. Сольцы, Новгородская обл. – г. Санкт-Петербург'):
        address_string = address_string.replace(
            'г. Сольцы, Новгородская область – г. Санкт-Петербург', 'г. Сольцы, Новгородская область'
        )
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
