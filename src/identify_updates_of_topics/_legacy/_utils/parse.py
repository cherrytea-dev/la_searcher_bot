import logging
import re


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
            if word in address_string:
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
    address_string = address_string.replace('г.о.', 'городской округ')

    # case when there's "муниципальный округ"
    address_string = address_string.replace('м.о.', 'муниципальный округ')

    # case when 'мкрн' or 'мкр'
    address_string = address_string.replace('мкрн', '')
    address_string = address_string.replace('мкр', '')

    # case with 'р-н' and 'АО'
    if 'р-н' in address_string and 'АО' in address_string:
        by_word = address_string.split()
        word_with_ao = None
        for word in by_word:
            if 'АО' in word:
                word_with_ao = word
        if word_with_ao:
            address_string = address_string.replace(word_with_ao, '')

    # case with 'р-н' or 'р-на' or 'р-он'
    replaces = [
        ('р-на', 'район'),
        ('р-н', 'район'),
        ('р-он', 'район'),
    ]
    address_string = _replace_all(address_string, replaces)

    # case with 'обл'
    address_string = address_string.replace('обл.', 'область')

    # case with 'НСО'
    address_string = address_string.replace('НСО', 'Новосибирская область')

    # case with 'МО'
    if 'МО' in address_string:
        mo_dict = {' МО ', ' МО,'}
        for word in mo_dict:
            if word in address_string:
                address_string = address_string.replace(word, 'Московская область')
        if address_string.endswith(' МО'):
            address_string = address_string[:-3] + ' Московская область'

    # case with 'ЛО'
    if address_string.find('ЛО') != -1:
        mo_dict = {' ЛО ', ' ЛО,'}
        for word in mo_dict:
            if word in address_string:
                address_string = address_string.replace(word, 'Ленинградская область')
        if address_string.endswith(' ЛО'):
            address_string = address_string[:-3] + ' Ленинградская область'

    # in case "г.Сочи"
    address_string = address_string.replace('г.Сочи', 'Сочи')
    address_string = address_string.replace('г. Сочи', 'Сочи')

    # case with 'района'
    if 'района' in address_string:
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
    if 'области' in address_string:
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
        first_num = re.search(r'\d', address_string).start()  # type:ignore[union-attr]
    except:
        first_num = 0
    try:
        first_letter = re.search(r'[а-яА-Я]', address_string).start()  # type:ignore[union-attr]
    except:  # noqa
        first_letter = 0

    new_start = max(first_num, first_letter)

    if 'г. москва' in address_string.lower() or 'г.москва' in address_string.lower():
        address_string = address_string.replace('г.', '')

    # add Russia to be sure
    # Openstreetmap.org treats Krym as Ukraine - so for search purposes Russia is avoided
    if address_string and 'крым' not in address_string.lower() and 'севастополь' not in address_string.lower():
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
    common_replaces = [
        ('г. Сольцы, Новгородская область – г. Санкт-Петербург', 'г. Сольцы, Новгородская область'),
        ('Орехово-Зуевский район', 'Орехово-Зуевский городской округ'),
        ('СНТ Нефтяник', 'СНТ Нефтянник'),
        ('Коченевский', 'Коченёвский'),
        ('г. Самара - с. Красный Яр', 'Красный Яр'),
        ('Букреево-Плессо', 'Букреево Плёсо'),
        ('г.Москва Москва: Юго-Западный АО, ', 'ЮЗАО, Москва, '),
        (' Луховицы - д. Алтухово, Зарайский городской округ,', 'Луховицы'),
        ('Сагкт-Петербург', 'Санкт-Петербург'),
        ('Краснозерский', 'Краснозёрский'),
        ('Толмачевское', 'Толмачёвское'),
        ('Кочевский', 'Кочёвский'),
        ('Чесцы', 'Часцы'),
    ]
    address_string = _replace_all(address_string, common_replaces)

    return address_string


def _replace_all(address_string: str, replaces: list[tuple[str, str]]) -> str:
    for src, dst in replaces:
        address_string = address_string.replace(src, dst)
    return address_string


def profile_get_type_of_activity(text_of_activity: str) -> list[str]:
    """get the status of the search activities: is there HQ, is there Active duties"""

    text_of_activity = text_of_activity.lower()
    activity_type: list[str] = []
    hq = None

    # Cases with HQ
    hq_keywords = [
        'штаб свернут',
        'штаб свёрнут',
        'штаб свëрнут',
    ]
    if _contains_any_text_of(text_of_activity, hq_keywords):
        hq = 'no'
        activity_type.append('9 - hq closed')
    else:
        now_keywords = [
            'сбор',
            'штаб работает',
            'выезд сейчас',
            'внимание, выезд',
            'внимание выезд',
            'внимание! выезд',
        ]
        if _contains_any_text_of(text_of_activity, now_keywords):
            hq = 'now'
            activity_type.append('1 - hq now')
        else:
            if text_of_activity.find('штаб мобильный') > -1:
                hq = 'mobile'
                activity_type.append('2 - hq mobile')
            else:
                will_keywords = [
                    'выезд ожидается',
                    'ожидается выезд',
                    'выезд планируется',
                    'планируется выезд',
                    'готовится выезд',
                    'выезд готовится',
                ]
                if _contains_any_text_of(text_of_activity, will_keywords):
                    hq = 'will'
                    activity_type.append('1 - hq will')

    # Cases with Autonom
    if hq not in {'mobile', 'now', 'will'}:
        if 'опрос' in text_of_activity:
            hq = 'autonom'
        if 'оклейка' in text_of_activity:
            hq = 'autonom'

    if 'автоном' in text_of_activity and 'нет автоном' not in text_of_activity:
        hq = 'autonom'
    elif 'двойк' in text_of_activity:
        hq = 'autonom'

    if hq == 'autonom':
        activity_type.append('6 - autonom')

    # Specific Tasks
    if 'забрать оборудование' in text_of_activity:
        activity_type.append('3 - hardware logistics')
    elif 'забрать комплект оборудования' in text_of_activity:
        activity_type.append('3 - hardware logistics')

    activity_type.sort()

    return activity_type


def _contains_any_text_of(text_of_activity: str, keywords: list[str]) -> bool:
    return any(keyword in text_of_activity for keyword in keywords)


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
            if list_of_lines[i + 1].startswith('https://telegram.im/@'):
                list_of_lines[i] += ' ' + list_of_lines[i + 1]
                list_of_lines[i + 1] = ''
            if list_of_lines[i + 1].startswith('https://t.me/'):
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

        logging.debug('DBG.P.101.Managers_list:')
        for manager in managers:
            logging.debug(manager)

    except Exception as e:
        logging.exception('DBG.P.102.EXC:')

    return managers
