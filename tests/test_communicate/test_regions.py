"""Tests for the hardcoded region → forum folders map (``communicate._utils.regions``).

The map duplicates what the database already knows through ``geo_folders``, so it
drifts easily: a "searches finished" folder used to be part of almost every region
tuple and got users subscribed to archived searches (empty block title in the
"last searches" view). Events-only folders stay in the map on purpose — event
notifications are delivered through the same subscription — but they must never
appear in the search lists.
"""

import sqlalchemy

from communicate._utils.regions import geography


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
