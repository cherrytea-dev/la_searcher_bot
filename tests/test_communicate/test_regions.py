"""Tests for the hardcoded region → forum folders map (``communicate._utils.regions``).

The map duplicates what the database already knows through ``geo_folders``, so it
drifts easily: a "searches finished" folder used to be part of almost every region
tuple and got users subscribed to archived searches (empty block title in the
"last searches" view). Events-only folders stay in the map on purpose — event
notifications are delivered through the same subscription — but they must never
appear in the search lists.
"""

import sqlalchemy

from communicate._utils.regions import LATE_ADDED_REGIONS, geography


def _folder_types(connection) -> dict[int, tuple[str, str]]:
    rows = connection.execute(
        sqlalchemy.text('SELECT folder_id, folder_type, folder_subtype FROM geo_folders;')
    ).fetchall()
    return {int(row[0]): (row[1], row[2]) for row in rows}


def test_folder_dict_contains_only_existing_folders(connection):
    """Every folder ID in the map must exist in geo_folders (catches typos/drift)."""
    folder_types = _folder_types(connection)

    missing = [
        (region_name, folder_id)
        for region_name, folder_ids in geography.folder_dict().items()
        for folder_id in folder_ids
        if folder_id not in folder_types
    ]

    assert missing == []


def test_folder_dict_has_no_finished_searches_folders(connection):
    """Subscriptions must not include 'searches finished' folders.

    They were dropped from the UI in both MAX and VK bots and purged by
    migration 010; keeping them in the map re-added them on every re-subscribe.
    """
    folder_types = _folder_types(connection)

    finished = [
        (region_name, folder_id)
        for region_name, folder_ids in geography.folder_dict().items()
        for folder_id in folder_ids
        if folder_types.get(folder_id) == ('searches', 'searches finished')
    ]

    assert finished == []


def test_folder_dict_has_no_unexpected_non_search_folders(connection):
    """Only events folders may be non-search folders in the map.

    Events folders are kept so event notifications keep working. This guards
    against re-introducing archived/common-info folders into subscriptions.
    """
    folder_types = _folder_types(connection)

    unexpected = [
        (region_name, folder_id, folder_types.get(folder_id))
        for region_name, folder_ids in geography.folder_dict().items()
        for folder_id in folder_ids
        if folder_types.get(folder_id, ('', ''))[0] not in {'searches', 'events'}
        # 214 (Мурманская) is a legacy 'common_info' folder that has been in the
        # map since 2022; it holds a handful of old searches. Kept as-is to avoid
        # changing subscriptions for existing users — see the report.
        and folder_id != 214
    ]

    assert unexpected == []


def test_kamchatka_has_own_division_and_searches_folder(connection):
    """RU-KAM must not fall back to the «Прочие поиски ДФО» division.

    Kamchatka had no division and no searches folder of its own (and no entry in the
    region map), so the bot treated the region as unsupported. Migration 012 and these
    test seeds give it division «Камчатский край» with searches folder 510.
    """
    rows = connection.execute(
        sqlalchemy.text(
            """
            SELECT d.division_name, f.folder_id
            FROM geo_regions r
            JOIN geo_divisions d ON d.division_id = r.division_id
            LEFT JOIN geo_folders f
                ON f.division_id = d.division_id
               AND f.folder_type = 'searches'
               AND f.folder_subtype = 'searches active'
            WHERE r.region_id = 'RU-KAM';
            """
        )
    ).fetchall()

    assert [tuple(row) for row in rows] == [('Камчатский край', 510)]
    assert 510 in geography.folder_dict()['Камчатский край']


def test_late_added_regions_do_not_shift_indexes_of_existing_ones():
    """Telegram callbacks carry a region's position, and old keyboards stay clickable.

    A region inserted into the alphabetical order would move every region after it:
    pressing an old button would subscribe the user to somebody else's region.
    """
    names = geography.all_region_names()
    late = [name for name in names if name in LATE_ADDED_REGIONS]
    legacy = [name for name in names if name not in LATE_ADDED_REGIONS]

    assert late, 'expected at least one late-added region'
    assert geography.region_index_order() == legacy + late

    for index, name in enumerate(legacy):
        assert geography.get_selected_region_name_by_order(index) == name

    # The new region must not steal an index that was already sent to users.
    assert geography.region_index_order().index('Камчатский край') == len(legacy)
