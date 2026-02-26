import logging
import re

from bs4 import BeautifulSoup, NavigableString, PageElement, Tag


def content_is_unaccessible(content: str) -> bool:
    text_cases = [
        r'Для просмотра этого форума вы должны быть авторизованы',
        r'Вы не авторизованы для чтения данного форума',
        r'PASSWORDCOLON',
    ]

    return any(bool(re.search(x, content)) for x in text_cases)


def is_forum_unavailable(check_content: str) -> bool:
    check_content = check_content.lower()
    return (
        '502 bad gateway' in check_content
        or '503 service temporarily unavailable' in check_content
        or 'sql error [ mysqli ]' in check_content
        or '429 too many requests' in check_content
        or 'too many connections' in check_content
        or '403 forbidden' in check_content
        or ('general error' in check_content and 'return to index page' in check_content)
    )


def clean_up_content(init_content: str) -> str | None:
    if not init_content or content_is_unaccessible(init_content):
        return None

    reco_content = _cook_soup(init_content)
    reco_content = _prettify_soup(reco_content)
    reco_content = _remove_links(reco_content)
    reco_content_text = reco_content.text
    reco_content_text = _remove_irrelevant_content(reco_content_text)
    reco_content_text = _make_html(reco_content_text)
    logging.info(f'{reco_content_text=}')

    return reco_content_text


def clean_up_content_2(init_content: str) -> list[str]:
    if not init_content or content_is_unaccessible(init_content):
        return []

    reco_content = _cook_soup(init_content)
    reco_content = _prettify_soup(reco_content)
    reco_content = _remove_links(reco_content)
    reco_content = _delete_sorted_out_all_tags(reco_content)

    # reco_content = reco_content.prettify()
    reco_content_text = reco_content.text
    reco_content_text = re.sub(r'\n{2,}', '\n', reco_content_text)

    if not re.search(r'\w', reco_content_text):
        return []

    reco_content_list = reco_content_text.split('\n')

    return _replace_common_cases(reco_content_list)


def _replace_common_cases(reco_content_list: list[str]) -> list[str]:
    patterns = [
        r'(\[/?[biu]]|\[/?color.{0,8}]|\[/?quote]|\[/?size.{0,8}]|\[/?spoiler=?]?)',
        r'(?i)последний раз редактировалось.{1,200}',
        r'(?i).{1,200}\d\d:\d\d, всего редактировалось.{1,200}',
        r'^\s+',
    ]

    for pattern in patterns:
        reco_content_list = [re.sub(pattern, '', line) for line in reco_content_list]

    reco_content_list = [re.sub('ё', 'е', line) for line in reco_content_list]

    translate_table = str.maketrans(
        {
            '{': r'\{',
            '}': r'\}',
        }
    )
    reco_content_list = [line.translate(translate_table).strip() for line in reco_content_list]

    return reco_content_list


def _cook_soup(content: str | bytes) -> BeautifulSoup:
    return BeautifulSoup(content, 'lxml')


def _remove_irrelevant_content(content: str) -> str:
    # language=regexp
    patterns = (
        r'(?i)(Карты.*\n|'
        r'Ориентировка на печать.*\n|'
        r'Ориентировка на репост.*\n|'
        r'\[\+] СМИ.*\n|'
        r'СМИ\s.*\n|'
        r'Задача на поиске с которой может помочь каждый.*\n|'
        r'ВНИМАНИЕ! Всем выезжающим иметь СИЗ.*\n|'
        r'С признаками ОРВИ оставайтесь дома.*\n|'
        r'Берегите себя и своих близких!.*\n|'
        r'Если же представитель СМИ хочет.*\n|'
        r'8\(800\)700-54-52 или.*\n|'
        r'Предоставлять комментарии по поиску.*\n|'
        r'Таблица прозвона больниц.*\n|'
        r'Запрос на согласование фото.*(\n|(\s*)?$)|'
        r'Все фото.*(\n|(\s*)?$)|'
        r'Написать инфоргу.*в (Telegram|Телеграмм?)(\n|(\s*)?$)|'
        r'Горячая линия отряда:.*(\n|(\s*)?$))'
        # here
    )

    content = re.sub(patterns, '', content)
    content = re.sub(r'[\s_-]*$', '', content)
    content = re.sub(r'\n\n', r'\n', content)
    content = re.sub(r'\n\n', r'\n', content)

    return content


def _make_html(content: str) -> str:
    return re.sub(r'\n', '<br>', content)


def _delete_sorted_out_one_tag(content: BeautifulSoup, tag: Tag) -> BeautifulSoup:
    # language=regexp
    patterns = [
        r'(?i)Всем выезжающим иметь СИЗ',
        # INFO SUPPORT
        r'(?i)ТРЕБУЕТСЯ ПОМОЩЬ В РАСПРОСТРАНЕНИИ ИНФОРМАЦИИ ПО СЕТИ',
        r'(?i)Задача на поиске,? с которой может помочь каждый',
        r'(?i)Помочь может каждый из вас',
        r'(?i)таблица прозвона',
        # PERSON – REASON
        r'(?i)(местонахождение неизвестно|не выходит на связь)',
        r'(?i)[^\n]{0,1000}(вы|у)ш(ла|[её]л).{1,200}не вернул(ся|ась)',
        r'(?i)(пропал[аи]? во время|не вернул(ся|[аи]сь) с) прогулки',
        r'не дошел до школы',
        r'уш(ёл|ел|ла|ли) (из дома )?в неизвестном направлении',
        r'(вы|у)ш(ёл|ел|ла|ли) (из дома )?(и пропал[аи]?|и не вернул(ся|ась)|в неизвестном направлении)',
        r'уш(ёл|ел|ла|ли) из медицинского учреждения',
        # PERSON – DETAILS
        r'(?i)МОЖЕТ НАХОДИТЬСЯ В ВАШЕМ (РАЙОНЕ|городе)',
        r'(?i)((НУЖДАЕТСЯ|МОЖЕТ НУЖДАТЬСЯ) В МЕДИЦИНСКОЙ ПОМОЩИ|Отставание в развити|потеря памяти)',
        r'(?i)(приметы|был[аи]? одет[аы]?|рост\W|телосложени|цвет глаз|'
        r'(^|\W)(куртка|шапка|сумка|волосы|глаза)($|\W))',
        r'(?i)(^|\W)оджеда(?!.{1,3}(лес|город))',
        # GENERAL PHRASES
        r'(?i)С признаками ОРВИ оставайтесь дома',
        r'(?i)Берегите себя и своих близких',
        r'(?i)ориентировка на ',
        r'(?i)(^|\n)[-_]{2,}(\n|$)',
        r'(?i)подпишитесь на бесплатную SMS-рассыл',
        r'(?i)выражаем .{0,20}благодарность за',
        r'(?i)Все фото/видео с поиска просьба отправлять',
        r'(?i)Все фото- и видеосъемки на поисках проводятся по согласованию с пресс-службой',
        r'(?i)Огромная просьба к поисковикам! Пожалуйста, отписывайтесь в формате',
        r'(?i)Предоставлять комментарии по поиску для СМИ могут только',
        r'(?i)Если же представитель СМИ хочет приехать на поиск',
        r'Если же представитель СМИ хочет',
        r'8\(800\)700-?54-?52',
        r'smi@lizaalert.org',
        r'https://la-org.ru/images/',
        r'(?i)Запрос на согласование фото- и видеосъемки',
        r'(?i)тема в соц сетях',
        r'(?i)Всё, что нужно знать, собираясь на свой первый поиск',
        r'(?i)тема в вк',
        r'(?i)Следите за темой',
        r'(?i)внимание!$',
        r'(?i)Огромная благодарность всем кто откликнулся',
        r'(?i)Канал оповещения об активных выездах и автономных задачах',
        r'(?i)Как стать добровольцем отряда «ЛизаАлерт»?',
        r'(?i)Уважаемые заявители',
        r'(?i)привет.{1,4}Я mikhel',
        r'(?i)Новичковая отряда',
        r'(?i)Горячая линия',
        r'(?i)Анкета добровольца',
        r'(?i)Бесплатная SMS-рассылка',
        r'(?i)Рассылка Вконтакте',
        r'(?i)Телеграм-канал ПСО',
        r'(?i)Рекомендуемый список оборудования',
        # MANAGERS
        r'(?i)(инфорги?( поиска| выезда)?:|снм\W|^ОД\W|^ДИ\W|Старш(ая|ий) на месте)',
        r'(?i)Коорд(инатор)?([-\s]консультант)?(?!инат)',
        r'(?i)написать .{0,50}в (телеграм|telegram)',
        r'(?i)Лимура \(Наталья\)',
        r'(?i)Тутси \(Светлана\)',
        r'(?i)(Герда Ольга|Ольга Герда)',
        r'(?i)Ксен \( ?Ксения\)',
        r'(?i)Сплин \(Наталья\)',
        r'(?i)Марва Валерия',
        r'(?i)Валькирия \(Лилия\)',
        r'(?i)Старовер \( ?Александр\)',
        r'(?i)Верба \(Ольга\)',
        r'(?i)Миледи Елена',
        r'(?i)Красикова Людмила',
        r'(?i)написать .{0,25}в Тг',
        r'(?i)Мария \(Марёна\)',
        r'(?i)Михалыч \(Александр\)',
        r'(?i)https://telegram.im/@buklya_LA71',
        r'(?i)Наталья \(Чента\)',
        r'(?i)Ирина \(Кеттари\)',
        r'(?i)Юлия \(Тайга\)',
        r'(?i)Ольга \(Весна\)',
        r'(?i)Селена \(Элина\)',
        r'(?i)Гроттер \(Татьяна\)',
        r'(?i)БарбиЕ \(Елена\)',
        r'(?i)Элька',
        r'(?i)Иван \(Кел\)',
        r'(?i)Анна \(Эстер\)',
        r'(?i)Википедия \(Ирина\)',
        r'(?i)Миледи \(Елена\)',
        r'(?i)Сплин Наталья',
        r'(?i)Doc\.Vatson \(Анастасия\)',
        r'(?i)Юля Онега',
        r'(?i)Андрей Хрящик',
        r'(?i)Юрий \(Бер\)',
        r'(?i)Птаха Ольга',
        r'(?i)Наталья Шелковица',
        r'(?i)Булка \(Анастасия\)',
        r'(?i)Палех \(Алексей\)',
        r'(?i)Wikipedia57 Ирина',
        r'(?i)Аврора Анастасия',
        r'(?i)Анастасия Булка',
        r'(?i)Александр \(Кузьмич\)',
        r'(?i)Ирина Айриш',
        r'(?i)Киви Ирина',
        r'(?i)Матрона \(Екатерина\)',
        r'(?i)Сергей \(Синий\)',
        r'(?i)Татьяна \(Ночка\)',
        r'(?i)Сара \(Анна\)',
        r'(?i)Наталья \(Марта\)',
        r'(?i)Ксения "Ята"',
        r'(?i)Катерина \(Бусинка\)',
        r'(?i)Ирина \(Динка\)',
        r'(?i)Яна \(Янка\)',
        r'(?i)Катя Кошка',
        r'(?i)Владимир1974',
        r'(?i)Екатерина \(Феникс\)',
        r'(?i)Алёна \(Тайга\)',
        r'(?i)Ашка Екатерина',
        r'(?i)Пёрышко Надежда',
        r'(?i)Анна Ваниль',
        r'(?i)Космос \(Алексей\)',
        r'(?i)Слон \(Артем\)',
        r'(?i)Мотя \(Алина\)',
        r'(?i)Екатерина Кирейчик',
        r'(?i)Леонид Енот',
        r'(?i)Сергей Сом',
        r'(?i)Лиса Елизаветта',
        r'(?i)Ирина "Ластик"',
        r'(?i)Светлана "Клюква"',
        r'(?i)Сара \(Анна\)',
        r'(?i)Наталья \(Марта\)',
        r'(?i)Ольга Елка',
        r'(?i)Ксен \(Ксения\)',
        r'(?i)Огонек \(Алена\)',
        r'(?i)Бро Елена',
        r'(?i)Добрая фея Настя',
        r'(?i)Лимура Наталья',
        r'(?i)XXX',
        r'(?i)XXX',
        r'(?i)XXX',
        r'(?i)XXX',
        # EXCEPTIONS
        r'(?i)автономн.{2,4} округ',
        r'(?i)ид[ёе]т сбор информации',
        r'(?i)телефон неактивен',
        r'(?i)проявля.{1,4} активность',
        r'(?i)XXX',
        r'(?i)XXX',
        r'(?i)XXX',
        r'(?i)XXX',
        r'(?i)XXX',
        r'(?i)XXX',
    ]

    if not tag:
        return content

    for pattern in patterns:
        if isinstance(tag, NavigableString) and re.search(pattern, tag):
            tag.extract()
        elif not isinstance(tag, NavigableString) and re.search(pattern, tag.text):
            tag.decompose()

    if not isinstance(tag, NavigableString):
        if (
            tag.name == 'span'
            and tag.attrs
            in [
                {'style': 'font-size:140%;line-height:116%'},
                {'style': 'font-size: 140%;line-height:116%'},
                {'style': 'font-size: 140%;line-height: 116%'},
            ]
            or tag.name == 'img'
        ):
            tag.decompose()

    return content


def _delete_sorted_out_all_tags(content: BeautifulSoup) -> BeautifulSoup:
    elements = content.body
    for tag in elements:  # type:ignore[union-attr]
        content = _delete_sorted_out_one_tag(content, tag)  # type:ignore[arg-type]

    return content


def _remove_links(content: BeautifulSoup) -> BeautifulSoup:
    for tag in content.find_all('a'):
        if tag.name == 'a' and not re.search(r'\[[+−]]', tag.text):
            tag.unwrap()

    return content


def _prettify_soup(content: BeautifulSoup) -> BeautifulSoup:
    for s in content.find_all('strong', {'class': 'text-strong'}):
        s.unwrap()

    for s in content.find_all('span'):
        if s.has_attr('style') and s['style'].startswith('color') and s['style'] != 'color':
            s.unwrap()

    deleted_text = content.find_all('span', {'style': 'text-decoration:line-through'})
    for case in deleted_text:
        case.decompose()

    for dd in content.find_all('dd', style='display:none'):
        del dd['style']

    return content
