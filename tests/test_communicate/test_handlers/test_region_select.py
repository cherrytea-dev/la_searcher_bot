"""Region subscribe/unsubscribe: one region == all 'searches' folders of its division.

Regression for the region-map change that dropped 'searches finished' ids from the map:
a user who was subscribed to those ids (e.g. 333 + 334 + 305 for Самарская обл.) must lose
them all on unsubscribe, otherwise the invisible folder survives and keeps rendering an
empty-titled «Посл. 20 поисков в » block until the data is cleaned up.
"""

from unittest.mock import MagicMock

from communicate._utils.handler_context import TGHandlerContext
from communicate._utils.handlers import region_select_handlers


class _FakeGeography:
    def __init__(self, folder_dict: dict[str, tuple[int, ...]]) -> None:
        self._folder_dict = folder_dict

    def folder_dict(self) -> dict[str, tuple[int, ...]]:
        return self._folder_dict


def _make_ctx(
    user_regions: list[int], division_search_folders: list[int] | None = None
) -> tuple[MagicMock, TGHandlerContext]:
    db_mock = MagicMock()
    db_mock.get_user_regions_from_db.return_value = user_regions
    db_mock.get_search_folders_of_division.return_value = division_search_folders or []
    ctx = TGHandlerContext(
        update_params=MagicMock(),
        extra_params=MagicMock(),
        db=db_mock,
        tg_api=MagicMock(),
    )
    return db_mock, ctx


def test_unsubscribe_removes_stale_folders_of_the_same_division(monkeypatch):
    """Stale ids of the region (305) go away together with the current ones (333, 334)."""
    db_mock, ctx = _make_ctx([333, 334, 305, 466], division_search_folders=[333, 334, 305, 306])
    monkeypatch.setattr(
        region_select_handlers,
        'geography',
        _FakeGeography({'Самарская обл.': (333, 334)}),
    )

    assert region_select_handlers._update_list_of_regions(ctx, 1, 'Самарская обл.') is True

    removed = sorted(call.args[1] for call in db_mock.delete_folder_from_user_regional_preference.call_args_list)
    assert removed == [305, 333, 334], 'другой регион (466) трогать нельзя, 306 не был подписан'


def test_unsubscribe_from_the_only_region_is_refused(monkeypatch):
    """A user must keep at least one region — even when the count includes stale ids.

    The old check compared ``len(user_regs) - len(region_tuple)``: with 333+334+305 against
    the new 2-id tuple it yielded 1 and allowed the delete, leaving 305 subscribed.
    """
    db_mock, ctx = _make_ctx([333, 334, 305], division_search_folders=[333, 334, 305])
    monkeypatch.setattr(
        region_select_handlers,
        'geography',
        _FakeGeography({'Самарская обл.': (333, 334)}),
    )

    assert region_select_handlers._update_list_of_regions(ctx, 1, 'Самарская обл.') is False
    db_mock.delete_folder_from_user_regional_preference.assert_not_called()


def test_unsubscribe_keeps_folders_of_another_division(monkeypatch):
    """Only the division being unsubscribed is touched, and only its 'searches' folders."""
    db_mock, ctx = _make_ctx([333, 334, 466, 467], division_search_folders=[333, 334])
    monkeypatch.setattr(
        region_select_handlers,
        'geography',
        _FakeGeography({'Самарская обл.': (333, 334)}),
    )

    assert region_select_handlers._update_list_of_regions(ctx, 1, 'Самарская обл.') is True

    removed = sorted(call.args[1] for call in db_mock.delete_folder_from_user_regional_preference.call_args_list)
    assert removed == [333, 334]


def test_subscribe_adds_every_folder_of_the_region(monkeypatch):
    """Subscribing does not consult the division and adds the whole tuple."""
    db_mock, ctx = _make_ctx([466], division_search_folders=[333, 334])
    monkeypatch.setattr(
        region_select_handlers,
        'geography',
        _FakeGeography({'Самарская обл.': (333, 334)}),
    )

    assert region_select_handlers._update_list_of_regions(ctx, 1, 'Самарская обл.') is True

    added = sorted(call.args[1] for call in db_mock.add_folder_to_user_regional_preference.call_args_list)
    assert added == [333, 334]
    db_mock.get_search_folders_of_division.assert_not_called()
    db_mock.delete_folder_from_user_regional_preference.assert_not_called()
