"""Tests for VK Bot keyboard modules — VKKeyboardLayouts and VKKeyboardPresets.

These tests cover:
- VKKeyboardLayouts builder methods (one_column, two_columns, one_row, inline_url, etc.)
- VKKeyboardPresets preset menus (main_menu, settings_menu, role_choice, etc.)
- Paginated inline region selection keyboard
"""

import json

import pytest

from vk_bot._utils.keyboards import VKKeyboardLayouts, VKKeyboardPresets

# ═══════════════════════════════════════════════════════════════════════════════
# VKKeyboardLayouts
# ═══════════════════════════════════════════════════════════════════════════════


class TestVKKeyboardLayout:
    """VKKeyboardLayouts layout methods."""

    def test_one_column(self):
        result = VKKeyboardLayouts.one_column(['A', 'B', 'C'])
        assert result['one_time'] is False
        assert result['inline'] is False
        assert len(result['buttons']) == 3
        for i, btn in enumerate(result['buttons']):
            assert len(btn) == 1  # one button per row
            assert btn[0]['action']['type'] == 'text'
            assert btn[0]['action']['label'] == ['A', 'B', 'C'][i]
            assert btn[0]['color'] == 'secondary'

    def test_one_column_with_color(self):
        result = VKKeyboardLayouts.one_column(['X'], color='primary')
        assert result['buttons'][0][0]['color'] == 'primary'

    def test_two_columns_even(self):
        result = VKKeyboardLayouts.two_columns(['A', 'B', 'C', 'D'])
        assert len(result['buttons']) == 2  # 2 rows
        assert len(result['buttons'][0]) == 2  # 2 buttons in first row
        assert len(result['buttons'][1]) == 2  # 2 buttons in second row
        assert result['buttons'][0][0]['action']['label'] == 'A'
        assert result['buttons'][0][1]['action']['label'] == 'B'
        assert result['buttons'][1][0]['action']['label'] == 'C'
        assert result['buttons'][1][1]['action']['label'] == 'D'

    def test_two_columns_odd(self):
        result = VKKeyboardLayouts.two_columns(['A', 'B', 'C'])
        assert len(result['buttons']) == 2  # 2 rows
        assert len(result['buttons'][0]) == 2  # A, B
        assert len(result['buttons'][1]) == 1  # C alone

    def test_two_columns_single(self):
        result = VKKeyboardLayouts.two_columns(['A'])
        assert len(result['buttons']) == 1
        assert len(result['buttons'][0]) == 1

    def test_one_row(self):
        result = VKKeyboardLayouts.one_row(['A', 'B', 'C'])
        assert len(result['buttons']) == 1
        assert len(result['buttons'][0]) == 3

    def test_one_row_single(self):
        result = VKKeyboardLayouts.one_row(['A'])
        assert len(result['buttons'][0]) == 1

    def test_inline_url(self):
        result = VKKeyboardLayouts.inline_url([('Label', 'https://example.com')])
        assert result['inline'] is True
        assert result['buttons'][0][0]['action']['type'] == 'open_link'
        assert result['buttons'][0][0]['action']['label'] == 'Label'
        assert result['buttons'][0][0]['action']['link'] == 'https://example.com'

    def test_inline_url_multiple(self):
        buttons = [('A', 'http://a.com'), ('B', 'http://b.com')]
        result = VKKeyboardLayouts.inline_url(buttons)
        assert len(result['buttons']) == 2  # each in its own row
        assert result['buttons'][0][0]['action']['link'] == 'http://a.com'
        assert result['buttons'][1][0]['action']['link'] == 'http://b.com'

    def test_empty(self):
        result = VKKeyboardLayouts.empty()
        assert result['buttons'] == []
        assert result['one_time'] is False
        assert result['inline'] is False

    def test_text_button_payload(self):
        """text_button generates payload from label if not provided."""
        btn = VKKeyboardLayouts.text_button('Test Button')
        payload = json.loads(btn['action']['payload'])
        assert payload == {'button': 'Test Button'}

    def test_text_button_custom_payload(self):
        btn = VKKeyboardLayouts.text_button('X', payload='custom_payload')
        assert btn['action']['payload'] == 'custom_payload'

    def test_location_button(self):
        btn = VKKeyboardLayouts.location_button()
        assert btn['action']['type'] == 'location'


# ═══════════════════════════════════════════════════════════════════════════════
# VKKeyboardPresets
# ═══════════════════════════════════════════════════════════════════════════════


class TestVKKeyboardPresets:
    """VKKeyboardPresets preset menus."""

    def test_main_menu(self):
        result = VKKeyboardPresets.main_menu()
        labels = [btn[0]['action']['label'] for btn in result['buttons']]
        assert len(labels) == 1
        assert labels[0] == 'настроить бот'
        assert result['buttons'][0][0]['color'] == 'primary'

    def test_settings_menu(self):
        result = VKKeyboardPresets.settings_menu()
        labels = [btn[0]['action']['label'] for btn in result['buttons']]
        assert len(labels) == 5
        assert labels[0] == 'настроить регион поисков'
        assert labels[1] == 'настроить "домашние координаты"'
        assert labels[2] == 'настроить максимальный радиус'
        assert labels[3] == 'полностью отключить уведомления'
        assert labels[4] == 'в начало'

    def test_settings_menu_for_unsubscribed_user(self):
        result = VKKeyboardPresets.settings_menu(notifications_disabled=True)
        labels = [btn[0]['action']['label'] for btn in result['buttons']]

        assert 'включить уведомления' in labels
        assert 'полностью отключить уведомления' not in labels

    def test_coords_menu(self):
        result = VKKeyboardPresets.coords_menu()
        labels = [btn[0]['action']['label'] for btn in result['buttons']]
        assert 'ввести "домашние координаты" вручную' in labels
        assert 'посмотреть сохраненные координаты' in labels
        assert 'удалить "домашние координаты"' in labels

    def test_role_choice(self):
        result = VKKeyboardPresets.role_choice()
        labels = [btn[0]['action']['label'] for btn in result['buttons']]
        assert 'я состою в ЛизаАлерт' in labels
        assert 'я хочу помогать ЛизаАлерт' in labels
        assert 'я ищу человека' in labels
        assert 'у меня другая задача' in labels
        assert 'не хочу говорить' in labels
        assert result['buttons'][0][0]['color'] == 'primary'

    def test_yes_no(self):
        result = VKKeyboardPresets.yes_no()
        assert len(result['buttons']) == 1  # two_columns → one row with 2 buttons
        assert len(result['buttons'][0]) == 2
        assert result['buttons'][0][0]['action']['label'] == 'да, это я'
        assert result['buttons'][0][1]['action']['label'] == 'нет, это не я'

    def test_back_to_start(self):
        result = VKKeyboardPresets.back_to_start()
        assert result['buttons'][0][0]['action']['label'] == 'в начало'

    def test_other_menu(self):
        result = VKKeyboardPresets.other_menu()
        labels = [btn[0]['action']['label'] for btn in result['buttons']]
        assert 'посмотреть последние поиски' in labels
        assert 'написать разработчику бота' in labels
        assert 'ознакомиться с информацией для новичка' in labels
        assert 'посмотреть красивые фото с поисков' in labels

    def test_distance_settings(self):
        result = VKKeyboardPresets.distance_settings()
        labels = [btn[0]['action']['label'] for btn in result['buttons']]
        assert 'включить ограничение по расстоянию' in labels
        assert 'отключить ограничение по расстоянию' in labels
        assert 'изменить ограничение по расстоянию' in labels

    def test_notification_settings(self):
        result = VKKeyboardPresets.notification_settings()
        # Flatten all button labels from all rows
        all_labels = []
        for row in result['buttons']:
            for btn in row:
                all_labels.append(btn['action']['label'])
        assert 'включить: все уведомления' in all_labels
        assert 'включить: о новых поисках' in all_labels
        assert 'включить: об измен. статусов' in all_labels
        assert 'отключить: все уведомления' in all_labels
        assert 'настроить более гибко' in all_labels
        assert 'в начало' in all_labels
        # VK API limits: 10 rows max, 40 chars per label
        assert len(result['buttons']) <= 10
        for label in all_labels:
            assert len(label) <= 40, f'Label too long ({len(label)} chars): {label}'

    def test_fed_districts(self):
        result = VKKeyboardPresets.fed_districts()
        labels = [btn[0]['action']['label'] for btn in result['buttons']]
        assert 'Центральный ФО' in labels
        assert 'Северо-Западный ФО' in labels
        assert 'Южный ФО' in labels
        assert 'Северо-Кавказский ФО' in labels
        assert 'Приволжский ФО' in labels
        assert 'Уральский ФО' in labels
        assert 'Сибирский ФО' in labels
        assert 'Дальневосточный ФО' in labels
        assert 'Прочие поиски по РФ' in labels

    def test_fed_districts_inline(self):
        """fed_districts_inline returns inline callback keyboard with district payloads."""
        result = VKKeyboardPresets.fed_districts_inline()
        assert result['inline'] is True

        # Check all district buttons have correct payload
        labels = []
        for row in result['buttons']:
            for btn in row:
                labels.append(btn['action']['label'])
                payload = json.loads(btn['action']['payload'])
                assert 'cmd' in payload
                if payload['cmd'] == 'district_select':
                    assert 'district' in payload
                elif payload['cmd'] == 'paginate_finish':
                    pass  # "Завершить" button
                else:
                    pytest.fail(f'Unexpected cmd in payload: {payload}')

        assert 'Центральный ФО' in labels
        assert 'Северо-Западный ФО' in labels
        assert 'Южный ФО' in labels
        assert 'Северо-Кавказский ФО' in labels
        assert 'Приволжский ФО' in labels
        assert 'Уральский ФО' in labels
        assert 'Сибирский ФО' in labels
        assert 'Дальневосточный ФО' in labels
        assert 'Прочие поиски по РФ' in labels
        assert 'Завершить' in labels

    def test_is_moscow(self):
        result = VKKeyboardPresets.is_moscow()
        assert result['buttons'][0][0]['action']['label'] == 'да, Москва – мой регион'
        assert result['buttons'][0][1]['action']['label'] == 'нет, я из другого региона'

    def test_help_needed(self):
        result = VKKeyboardPresets.help_needed()
        assert result['buttons'][0][0]['action']['label'] == 'да, помогите мне настроить бот'
        assert result['buttons'][0][1]['action']['label'] == 'нет, помощь не требуется'

    def test_paginated_regions_inline_first_page(self):
        """First page shows items 0-5 + 'ещё →' + 'Завершить'."""
        buttons = [f'Регион {i}' for i in range(1, 19)]  # 18 items = 3 pages (6 per page)
        result = VKKeyboardPresets.paginated_regions_inline(buttons, page=0, district='Центральный')

        assert result['inline'] is True
        all_labels = [btn['action']['label'] for row in result['buttons'] for btn in row]
        assert 'Регион 1' in all_labels
        assert 'Регион 6' in all_labels
        assert 'Регион 7' not in all_labels
        assert 'ещё →' in all_labels
        assert '← назад' not in all_labels  # first page
        assert 'Завершить' in all_labels

        # Verify callback payloads — paginate_toggle now includes district and page
        toggle_btn = result['buttons'][0][0]
        assert json.loads(toggle_btn['action']['payload']) == {
            'cmd': 'paginate_toggle',
            'region': 'Регион 1',
            'district': 'Центральный',
            'page': 0,
        }

        # Bottom row: nav + 'Завершить' combined
        bottom_row = result['buttons'][-1]
        # First button in bottom row should be 'ещё →' (since page=0, no '← назад')
        next_btn = bottom_row[0]
        assert json.loads(next_btn['action']['payload']) == {
            'cmd': 'paginate_nav',
            'district': 'Центральный',
            'page': 1,
        }
        # Last button in bottom row should be 'Завершить'
        finish_btn = bottom_row[-1]
        assert json.loads(finish_btn['action']['payload']) == {'cmd': 'paginate_finish'}

    def test_paginated_regions_inline_last_page(self):
        """Last page shows remaining items + '← назад' + 'Завершить'."""
        buttons = [f'Регион {i}' for i in range(1, 19)]  # 18 items = 3 pages (6 per page)
        result = VKKeyboardPresets.paginated_regions_inline(buttons, page=2, district='Центральный')

        assert result['inline'] is True
        all_labels = [btn['action']['label'] for row in result['buttons'] for btn in row]
        assert 'Регион 13' in all_labels
        assert 'Регион 18' in all_labels
        assert 'Регион 1' not in all_labels
        assert '← назад' in all_labels
        assert 'ещё →' not in all_labels  # last page
        assert 'Завершить' in all_labels

        # Verify callback payloads — bottom row has '← назад' + 'Завершить'
        bottom_row = result['buttons'][-1]
        prev_btn = bottom_row[0]
        assert json.loads(prev_btn['action']['payload']) == {
            'cmd': 'paginate_nav',
            'district': 'Центральный',
            'page': 1,
        }

    def test_paginated_regions_inline_single_page(self):
        """Single page shows all items + 'Завершить', no navigation."""
        buttons = [f'Регион {i}' for i in range(1, 5)]  # 4 items = 1 page
        result = VKKeyboardPresets.paginated_regions_inline(buttons, page=0, district='Центральный')

        assert result['inline'] is True
        all_labels = [btn['action']['label'] for row in result['buttons'] for btn in row]
        assert 'Регион 1' in all_labels
        assert 'Регион 4' in all_labels
        assert '← назад' not in all_labels
        assert 'ещё →' not in all_labels
        assert 'Завершить' in all_labels

    def test_paginated_regions_inline_middle_page(self):
        """Middle page shows both '← назад' and 'ещё →'."""
        buttons = [f'Регион {i}' for i in range(1, 28)]  # 27 items = 5 pages (6 per page)
        result = VKKeyboardPresets.paginated_regions_inline(buttons, page=2, district='Сибирский')

        assert result['inline'] is True
        all_labels = [btn['action']['label'] for row in result['buttons'] for btn in row]
        assert 'Регион 13' in all_labels
        assert 'Регион 18' in all_labels
        assert '← назад' in all_labels
        assert 'ещё →' in all_labels
        assert 'Завершить' in all_labels

        # Bottom row has nav buttons + 'Завершить'
        bottom_row = result['buttons'][-1]
        assert len(bottom_row) == 3  # '← назад' + 'ещё →' + 'Завершить'
        assert json.loads(bottom_row[0]['action']['payload']) == {
            'cmd': 'paginate_nav',
            'district': 'Сибирский',
            'page': 1,
        }
        assert json.loads(bottom_row[1]['action']['payload']) == {
            'cmd': 'paginate_nav',
            'district': 'Сибирский',
            'page': 3,
        }
        assert json.loads(bottom_row[2]['action']['payload']) == {'cmd': 'paginate_finish'}
