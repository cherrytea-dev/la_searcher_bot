import logging
import re

from bs4 import BeautifulSoup, NavigableString


def clean_up_content(init_content: str | bytes) -> str | None:
    if not init_content or re.search(r'Для просмотра этого форума вы должны быть авторизованы', init_content):
        return None

    reco_content = _cook_soup(init_content)
    reco_content = _prettify_soup(reco_content)
    reco_content = _remove_links(reco_content)
    reco_content_text = reco_content.text
    reco_content_text = _remove_irrelevant_content(reco_content_text)
    reco_content_text = _make_html(reco_content_text)
    logging.info(f'{reco_content_text=}')

    return reco_content_text


def clean_up_content_2(init_content: str | bytes) -> list[str]:
    if not init_content or re.search(r'Для просмотра этого форума вы должны быть авторизованы', init_content):
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

    reco_content_text = reco_content_text.split('\n')

    # language=regexp
    patterns = [
        r'(\[/?[biu]]|\[/?color.{0,8}]|\[/?quote]|\[/?size.{0,8}]|\[/?spoiler=?]?)',
        r'(?i)последний раз редактировалось.{1,200}',
        r'(?i).{1,200}\d\d:\d\d, всего редактировалось.{1,200}',
        r'^\s+',
    ]

    for pattern in patterns:
        reco_content_text = [re.sub(pattern, '', line) for line in reco_content_text]

    reco_content_text = [re.sub('ё', 'е', line) for line in reco_content_text]

    translate_table = str.maketrans({'{': r'\{', '}': r'\}'})
    reco_content_text = [line.translate(translate_table) for line in reco_content_text]

    return reco_content_text


def _cook_soup(content: str | bytes) -> BeautifulSoup:
    content = BeautifulSoup(content, 'lxml')

    return content


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
    )

    content = re.sub(patterns, '', content)
    content = re.sub(r'[\s_-]*$', '', content)
    content = re.sub(r'\n\n', r'\n', content)
    content = re.sub(r'\n\n', r'\n', content)

    return content


def _make_html(content: str) -> str:
    content = re.sub(r'\n', '<br>', content)

    return content


def _delete_sorted_out_one_tag(content, tag):
    # language=regexp
    patterns = [
        [r'(?i)Всем выезжающим иметь СИЗ', 'sort_out'],
        # INFO SUPPORT
        [r'(?i)ТРЕБУЕТСЯ ПОМОЩЬ В РАСПРОСТРАНЕНИИ ИНФОРМАЦИИ ПО СЕТИ', 'sort_out'],
        [r'(?i)Задача на поиске,? с которой может помочь каждый', 'sort_out'],
        [r'(?i)Помочь может каждый из вас', 'sort_out'],
        [r'(?i)таблица прозвона', 'sort_out'],
        # PERSON – REASON
        [r'(?i)(местонахождение неизвестно|не выходит на связь)', 'sort_out'],
        [r'(?i)[^\n]{0,1000}(вы|у)ш(ла|[её]л).{1,200}не вернул(ся|ась)', 'sort_out'],
        [r'(?i)(пропал[аи]? во время|не вернул(ся|[аи]сь) с) прогулки', 'sort_out'],
        [r'не дошел до школы', 'sort_out'],
        [r'уш(ёл|ел|ла|ли) (из дома )?в неизвестном направлении', 'sort_out'],
        [
            r'(вы|у)ш(ёл|ел|ла|ли) (из дома )?(и пропал[аи]?|и не вернул(ся|ась)|в неизвестном направлении)',
            'sort_out',
        ],
        [r'уш(ёл|ел|ла|ли) из медицинского учреждения', 'sort_out'],
        # PERSON – DETAILS
        [r'(?i)МОЖЕТ НАХОДИТЬСЯ В ВАШЕМ (РАЙОНЕ|городе)', 'sort_out'],
        [r'(?i)((НУЖДАЕТСЯ|МОЖЕТ НУЖДАТЬСЯ) В МЕДИЦИНСКОЙ ПОМОЩИ|Отставание в развити|потеря памяти)', 'sort_out'],
        [
            r'(?i)(приметы|был[аи]? одет[аы]?|рост\W|телосложени|цвет глаз|'
            r'(^|\W)(куртка|шапка|сумка|волосы|глаза)($|\W))',
            'sort_out',
        ],
        [r'(?i)(^|\W)оджеда(?!.{1,3}(лес|город))', 'sort_out'],
        # GENERAL PHRASES
        [r'(?i)С признаками ОРВИ оставайтесь дома', 'sort_out'],
        [r'(?i)Берегите себя и своих близких', 'sort_out'],
        [r'(?i)ориентировка на ', 'sort_out'],
        [r'(?i)(^|\n)[-_]{2,}(\n|$)', 'sort_out'],
        [r'(?i)подпишитесь на бесплатную SMS-рассыл', 'sort_out'],
        [r'(?i)выражаем .{0,20}благодарность за', 'sort_out'],
        [r'(?i)Все фото/видео с поиска просьба отправлять', 'sort_out'],
        [r'(?i)Предоставлять комментарии по поиску для СМИ могут только', 'sort_out'],
        [r'Если же представитель СМИ хочет', 'sort_out'],
        [r'8\(800\)700-?54-?52', 'sort_out'],
        [r'smi@lizaalert.org', 'sort_out'],
        [r'https://la-org.ru/images/', 'sort_out'],
        [r'(?i)Запрос на согласование фото- и видеосъемки', 'sort_out'],
        [r'(?i)тема в соц сетях', 'sort_out'],
        [r'(?i)Всё, что нужно знать, собираясь на свой первый поиск', 'sort_out'],
        [r'(?i)тема в вк', 'sort_out'],
        [r'(?i)Следите за темой', 'sort_out'],
        [r'(?i)внимание!$', 'sort_out'],
        [r'(?i)Огромная благодарность всем кто откликнулся', 'sort_out'],
        [r'(?i)Канал оповещения об активных выездах и автономных задачах', 'sort_out'],
        [r'(?i)Как стать добровольцем отряда «ЛизаАлерт»?', 'sort_out'],
        [r'(?i)Уважаемые заявители', 'sort_out'],
        [r'(?i)привет.{1,4}Я mikhel', 'sort_out'],
        [r'(?i)Новичковая отряда', 'sort_out'],
        [r'(?i)Горячая линия', 'sort_out'],
        [r'(?i)Анкета добровольца', 'sort_out'],
        [r'(?i)Бесплатная SMS-рассылка', 'sort_out'],
        [r'(?i)Рассылка Вконтакте', 'sort_out'],
        [r'(?i)Телеграм-канал ПСО', 'sort_out'],
        [r'(?i)Рекомендуемый список оборудования', 'sort_out'],
        # MANAGERS
        [r'(?i)(инфорги?( поиска| выезда)?:|снм\W|^ОД\W|^ДИ\W|Старш(ая|ий) на месте)', 'sort_out'],
        [r'(?i)Коорд(инатор)?([-\s]консультант)?(?!инат)', 'sort_out'],
        [r'(?i)написать .{0,50}в (телеграм|telegram)', 'sort_out'],
        [r'(?i)Лимура \(Наталья\)', 'sort_out'],
        [r'(?i)Тутси \(Светлана\)', 'sort_out'],
        [r'(?i)(Герда Ольга|Ольга Герда)', 'sort_out'],
        [r'(?i)Ксен \( ?Ксения\)', 'sort_out'],
        [r'(?i)Сплин \(Наталья\)', 'sort_out'],
        [r'(?i)Марва Валерия', 'sort_out'],
        [r'(?i)Валькирия \(Лилия\)', 'sort_out'],
        [r'(?i)Старовер \( ?Александр\)', 'sort_out'],
        [r'(?i)Верба \(Ольга\)', 'sort_out'],
        [r'(?i)Миледи Елена', 'sort_out'],
        [r'(?i)Красикова Людмила', 'sort_out'],
        [r'(?i)написать .{0,25}в Тг', 'sort_out'],
        [r'(?i)Мария \(Марёна\)', 'sort_out'],
        [r'(?i)Михалыч \(Александр\)', 'sort_out'],
        [r'(?i)https://telegram.im/@buklya_LA71', 'sort_out'],
        [r'(?i)Наталья \(Чента\)', 'sort_out'],
        [r'(?i)Ирина \(Кеттари\)', 'sort_out'],
        [r'(?i)Юлия \(Тайга\)', 'sort_out'],
        [r'(?i)Ольга \(Весна\)', 'sort_out'],
        [r'(?i)Селена \(Элина\)', 'sort_out'],
        [r'(?i)Гроттер \(Татьяна\)', 'sort_out'],
        [r'(?i)БарбиЕ \(Елена\)', 'sort_out'],
        [r'(?i)Элька', 'sort_out'],
        [r'(?i)Иван \(Кел\)', 'sort_out'],
        [r'(?i)Анна \(Эстер\)', 'sort_out'],
        [r'(?i)Википедия \(Ирина\)', 'sort_out'],
        [r'(?i)Миледи \(Елена\)', 'sort_out'],
        [r'(?i)Сплин Наталья', 'sort_out'],
        [r'(?i)Doc\.Vatson \(Анастасия\)', 'sort_out'],
        [r'(?i)Юля Онега', 'sort_out'],
        [r'(?i)Андрей Хрящик', 'sort_out'],
        [r'(?i)Юрий \(Бер\)', 'sort_out'],
        [r'(?i)Птаха Ольга', 'sort_out'],
        [r'(?i)Наталья Шелковица', 'sort_out'],
        [r'(?i)Булка \(Анастасия\)', 'sort_out'],
        [r'(?i)Палех \(Алексей\)', 'sort_out'],
        [r'(?i)Wikipedia57 Ирина', 'sort_out'],
        [r'(?i)Аврора Анастасия', 'sort_out'],
        [r'(?i)Анастасия Булка', 'sort_out'],
        [r'(?i)Александр \(Кузьмич\)', 'sort_out'],
        [r'(?i)Ирина Айриш', 'sort_out'],
        [r'(?i)Киви Ирина', 'sort_out'],
        [r'(?i)Матрона \(Екатерина\)', 'sort_out'],
        [r'(?i)Сергей \(Синий\)', 'sort_out'],
        [r'(?i)Татьяна \(Ночка\)', 'sort_out'],
        [r'(?i)Сара \(Анна\)', 'sort_out'],
        [r'(?i)Наталья \(Марта\)', 'sort_out'],
        [r'(?i)Ксения "Ята"', 'sort_out'],
        [r'(?i)Катерина \(Бусинка\)', 'sort_out'],
        [r'(?i)Ирина \(Динка\)', 'sort_out'],
        [r'(?i)Яна \(Янка\)', 'sort_out'],
        [r'(?i)Катя Кошка', 'sort_out'],
        [r'(?i)Владимир1974', 'sort_out'],
        [r'(?i)Екатерина \(Феникс\)', 'sort_out'],
        [r'(?i)Алёна \(Тайга\)', 'sort_out'],
        [r'(?i)Ашка Екатерина', 'sort_out'],
        [r'(?i)Пёрышко Надежда', 'sort_out'],
        [r'(?i)Анна Ваниль', 'sort_out'],
        [r'(?i)Космос \(Алексей\)', 'sort_out'],
        [r'(?i)Слон \(Артем\)', 'sort_out'],
        [r'(?i)Мотя \(Алина\)', 'sort_out'],
        [r'(?i)Екатерина Кирейчик', 'sort_out'],
        [r'(?i)Леонид Енот', 'sort_out'],
        [r'(?i)Сергей Сом', 'sort_out'],
        [r'(?i)Лиса Елизаветта', 'sort_out'],
        [r'(?i)Ирина "Ластик"', 'sort_out'],
        [r'(?i)Светлана "Клюква"', 'sort_out'],
        [r'(?i)Сара \(Анна\)', 'sort_out'],
        [r'(?i)Наталья \(Марта\)', 'sort_out'],
        [r'(?i)Ольга Елка', 'sort_out'],
        [r'(?i)Ксен \(Ксения\)', 'sort_out'],
        [r'(?i)Огонек \(Алена\)', 'sort_out'],
        [r'(?i)Бро Елена', 'sort_out'],
        [r'(?i)Добрая фея Настя', 'sort_out'],
        [r'(?i)Лимура Наталья', 'sort_out'],
        [r'(?i)XXX', 'sort_out'],
        [r'(?i)XXX', 'sort_out'],
        [r'(?i)XXX', 'sort_out'],
        [r'(?i)XXX', 'sort_out'],
        # EXCEPTIONS
        [r'(?i)автономн.{2,4} округ', 'sort_out'],
        [r'(?i)ид[ёе]т сбор информации', 'sort_out'],
        [r'(?i)телефон неактивен', 'sort_out'],
        [r'(?i)проявля.{1,4} активность', 'sort_out'],
        [r'(?i)XXX', 'sort_out'],
        [r'(?i)XXX', 'sort_out'],
        [r'(?i)XXX', 'sort_out'],
        [r'(?i)XXX', 'sort_out'],
        [r'(?i)XXX', 'sort_out'],
        [r'(?i)XXX', 'sort_out'],
    ]

    if not tag:
        return content

    for pattern in patterns:
        if isinstance(tag, NavigableString) and re.search(pattern[0], tag):
            tag.extract()
        elif not isinstance(tag, NavigableString) and re.search(pattern[0], tag.text):
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
    for tag in elements:
        content = _delete_sorted_out_one_tag(content, tag)

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
        try:
            if s.attrs['style'] and s['style'] and len(s['style']) > 5 and s['style'][0:5] == 'color':
                s.unwrap()
        except Exception as e:
            logging.exception(e)
            continue

    deleted_text = content.find_all('span', {'style': 'text-decoration:line-through'})
    for case in deleted_text:
        case.decompose()

    for dd in content.find_all('dd', style='display:none'):
        del dd['style']

    return content
