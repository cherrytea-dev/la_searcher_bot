"""Tests for check_topics_by_upd_time._legacy.main.

Covers FolderComparator, process_folder timestamp skip logic,
get_updated_root_folders, save_root_timestamps, and main().
"""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from check_topics_by_upd_time._legacy.main import (
    DecomposedFolder,
    FolderComparator,
    FolderForDecompose,
    FolderUpdateChecker,
    KeyValueStorage,
    Subfolder,
    get_updated_root_folders,
    process_folder,
    save_root_timestamps,
)

pytestmark = pytest.mark.xdist_group('legacy_db')


# ═══════════════════════════════════════════════════════════════════════════════
# FolderComparator — pure logic
# ═══════════════════════════════════════════════════════════════════════════════


class TestFolderComparator:
    """FolderComparator returns int folder nums (from ast.literal_eval).

    A folder that exists in old but NOT in new appears as "changed" because
    its old timestamp != the empty string in the comparison matrix.
    """

    @staticmethod
    def _list(*items: tuple[str, str]) -> str:
        return str([Subfolder(folder_num=int(k), change_time_str=v) for k, v in items])

    def test_new_folders_all_returned(self):
        assert FolderComparator().compare_folders(self._list(('100', 't1'), ('200', 't2')), None) == [100, 200]

    def test_no_changes_returns_empty(self):
        s = self._list(('100', 't1'))
        assert FolderComparator().compare_folders(s, s) == []

    def test_new_folder_added(self):
        old = self._list(('100', 't1'))
        new = self._list(('100', 't1'), ('200', 't2'))
        assert FolderComparator().compare_folders(new, old) == [200]

    def test_removed_folder_appears_as_changed(self):
        old = self._list(('100', 't1'), ('200', 't2'))
        new = self._list(('100', 't1'))
        assert FolderComparator().compare_folders(new, old) == [200]

    def test_timestamp_changed(self):
        old = self._list(('100', 't1'))
        new = self._list(('100', 't2'))
        assert FolderComparator().compare_folders(new, old) == [100]

    def test_mixed(self):
        old = self._list(('100', 't1'), ('200', 't2'), ('300', 't3'))
        new = self._list(('100', 't1'), ('200', 'tc'), ('400', 't4'))
        assert sorted(FolderComparator().compare_folders(new, old)) == [200, 300, 400]


# ═══════════════════════════════════════════════════════════════════════════════
# process_folder — timestamp skip logic
# ═══════════════════════════════════════════════════════════════════════════════


class TestProcessFolderTimestampSkip:
    """process_folder should skip HTTP fetch when the folder timestamp hasn't changed.

    The skip check works on the *in-memory* folder_timestamps dict.
    storage is mocked to avoid DB / HTTP dependencies.
    """

    def _run(self, folder, folder_timestamps=None, child_subfolders=None):
        if folder_timestamps is None:
            folder_timestamps = {}
        if child_subfolders is None:
            child_subfolders = [Subfolder(folder_num=111, change_time_str='child_ts')]

        folders_to_check: list = []
        updated_folders: list = []
        storage = MagicMock(spec=KeyValueStorage)
        # storage.read_folders / read_searches must return strings for FolderComparator
        storage.read_folders.return_value = None
        storage.read_searches.return_value = None

        with patch('check_topics_by_upd_time._legacy.main.FolderDecomposer', autospec=True) as mock_cls:
            inst = mock_cls.return_value
            inst.decompose_folder.return_value = DecomposedFolder(
                subfolders=child_subfolders,
                searches=[],
                folder_name='test',
            )
            process_folder(folders_to_check, updated_folders, folder, storage, folder_timestamps)

        return folders_to_check, updated_folders, inst

    def test_skip_when_timestamp_matches(self):
        """Saved ts == mother_folder_timestamp → skip."""
        folders_to_check, updated_folders, mock_inst = self._run(
            FolderForDecompose(mother_folder_num='123', mother_folder_timestamp='ts1'),
            {'123': 'ts1'},
        )
        mock_inst.decompose_folder.assert_not_called()
        assert folders_to_check == []
        assert updated_folders == []

    def test_process_when_no_timestamp(self):
        """mother_folder_timestamp is None → process."""
        folders_to_check, updated_folders, mock_inst = self._run(
            FolderForDecompose(mother_folder_num='999', mother_folder_timestamp=None),
        )
        mock_inst.decompose_folder.assert_called_once_with('999')
        assert len(folders_to_check) == 1

    def test_process_when_timestamp_mismatch(self):
        """Saved ts != mother_folder_timestamp → process."""
        folders_to_check, updated_folders, mock_inst = self._run(
            FolderForDecompose(mother_folder_num='789', mother_folder_timestamp='ts_new'),
            {'789': 'ts_old'},
        )
        mock_inst.decompose_folder.assert_called_once()

    def test_saves_timestamp_after_process(self):
        """After processing, folder_timestamps gets the folder's timestamp."""
        ts: dict = {}
        self._run(
            FolderForDecompose(mother_folder_num='111', mother_folder_timestamp='ts_new'),
            ts,
        )
        assert ts.get('111') == 'ts_new'

    def test_queues_subfolders_with_timestamps(self):
        folder = FolderForDecompose(mother_folder_num='555', mother_folder_timestamp='ts_parent')
        children = [
            Subfolder(folder_num=111, change_time_str='child_ts1'),
            Subfolder(folder_num=222, change_time_str='child_ts2'),
        ]
        folders_to_check, *_ = self._run(folder, child_subfolders=children)
        assert folders_to_check[0].mother_folder_num == '111'
        assert folders_to_check[0].mother_folder_timestamp == 'child_ts1'
        assert folders_to_check[1].mother_folder_num == '222'
        assert folders_to_check[1].mother_folder_timestamp == 'child_ts2'


# ═══════════════════════════════════════════════════════════════════════════════
# save_root_timestamps — unit tests with mocked storage
# ═══════════════════════════════════════════════════════════════════════════════


class TestSaveRootTimestamps:
    """save_root_timestamps reads current dict, adds new entries, writes back."""

    def test_adds_new_timestamps(self):
        with patch.object(KeyValueStorage, 'read_foder_root_modified_times_dict', return_value={'1': 'old_ts'}):
            with patch.object(KeyValueStorage, 'write_foder_root_modified_times_dict') as mock_write:
                save_root_timestamps([('2', 'new_ts')])

        mock_write.assert_called_once_with({'1': 'old_ts', '2': 'new_ts'})

    def test_empty_list_returns_early(self):
        """Empty list → early return, no DB calls at all."""
        with patch.object(KeyValueStorage, 'read_foder_root_modified_times_dict') as mock_read:
            with patch.object(KeyValueStorage, 'write_foder_root_modified_times_dict') as mock_write:
                save_root_timestamps([])

        mock_read.assert_not_called()
        mock_write.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# get_updated_root_folders — unit tests with mocked forum + storage
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetUpdatedRootFolders:
    """Should return changed root folders WITHOUT saving timestamps."""

    def _mock_storage(self, saved: dict | None = None):
        return patch.object(
            KeyValueStorage,
            'read_foder_root_modified_times_dict',
            return_value=saved if saved else {},
        )

    def test_returns_only_changed_folder(self):
        """Only folders with changed timestamps are returned."""
        saved = {'1': '2024-01-01T00:00:00+00:00', '2': '2024-01-01T00:00:00+00:00'}
        with patch.object(
            FolderUpdateChecker,
            'check_updates_in_folder_with_folders',
            return_value=[
                ['1', '2024-01-01T00:00:00+00:00', datetime.datetime(2024, 1, 1)],
                ['2', '2025-06-01T00:00:00+00:00', datetime.datetime(2025, 6, 1)],
            ],
        ):
            with self._mock_storage(saved):
                result = get_updated_root_folders()

        assert result == [('2', '2025-06-01T00:00:00+00:00')]

    def test_does_not_write_storage(self):
        """get_updated_root_folders should NOT write timestamps."""
        with patch.object(
            FolderUpdateChecker,
            'check_updates_in_folder_with_folders',
            return_value=[
                ['1', 'new_ts', datetime.datetime(2025, 1, 1)],
            ],
        ):
            with self._mock_storage({'1': '2024-01-01T00:00:00+00:00'}):
                with patch.object(KeyValueStorage, 'write_foder_root_modified_times_dict') as mock_write:
                    get_updated_root_folders()

        mock_write.assert_not_called()

    def test_empty_when_no_updates(self):
        with patch.object(
            FolderUpdateChecker,
            'check_updates_in_folder_with_folders',
            return_value=[['1', '2024-01-01T00:00:00+00:00', datetime.datetime(2024, 1, 1)]],
        ):
            with self._mock_storage({'1': '2024-01-01T00:00:00+00:00'}):
                assert get_updated_root_folders() == []

    def test_new_folder_detected(self):
        saved = {'1': '2024-01-01T00:00:00+00:00'}
        with patch.object(
            FolderUpdateChecker,
            'check_updates_in_folder_with_folders',
            return_value=[
                ['1', '2024-01-01T00:00:00+00:00', datetime.datetime(2024, 1, 1)],
                ['2', '2025-06-01T00:00:00+00:00', datetime.datetime(2025, 6, 1)],
            ],
        ):
            with self._mock_storage(saved):
                assert get_updated_root_folders() == [('2', '2025-06-01T00:00:00+00:00')]

    def test_empty_when_forum_unavailable(self):
        with patch.object(FolderUpdateChecker, 'check_updates_in_folder_with_folders', return_value=[]):
            assert get_updated_root_folders() == []

    def test_empty_when_no_saved_data_and_no_forum_data(self):
        with patch.object(FolderUpdateChecker, 'check_updates_in_folder_with_folders', return_value=[]):
            assert get_updated_root_folders() == []


# ═══════════════════════════════════════════════════════════════════════════════
# main() — integration: saves roots only on success
# ═══════════════════════════════════════════════════════════════════════════════


class TestMainRootTimestampSave:
    """main() should save root timestamps only after successful traversal."""

    @patch('check_topics_by_upd_time._legacy.main.get_updated_root_folders')
    @patch('check_topics_by_upd_time._legacy.main.get_updates_of_nested_folders')
    @patch('check_topics_by_upd_time._legacy.main.pubsub_parse_folders')
    @patch('check_topics_by_upd_time._legacy.main.save_root_timestamps')
    def test_saves_on_success(
        self,
        mock_save,
        mock_pubsub,
        mock_get_updates,
        mock_get_roots,
    ):
        mock_get_roots.return_value = [('1', 'ts1')]
        mock_get_updates.return_value = []

        from check_topics_by_upd_time._legacy.main import main as legacy_main

        legacy_main({}, None)

        mock_save.assert_called_once_with([('1', 'ts1')])

    @patch('check_topics_by_upd_time._legacy.main.get_updated_root_folders')
    @patch('check_topics_by_upd_time._legacy.main.get_updates_of_nested_folders')
    @patch('check_topics_by_upd_time._legacy.main.pubsub_parse_folders')
    @patch('check_topics_by_upd_time._legacy.main.save_root_timestamps')
    def test_does_not_save_on_failure(
        self,
        mock_save,
        mock_pubsub,
        mock_get_updates,
        mock_get_roots,
    ):
        mock_get_roots.return_value = [('1', 'ts1')]
        mock_get_updates.side_effect = RuntimeError('traversal failed')

        from check_topics_by_upd_time._legacy.main import main as legacy_main

        with pytest.raises(RuntimeError):
            legacy_main({}, None)

        mock_save.assert_not_called()

    @patch('check_topics_by_upd_time._legacy.main.get_updated_root_folders')
    @patch('check_topics_by_upd_time._legacy.main.get_updates_of_nested_folders')
    @patch('check_topics_by_upd_time._legacy.main.pubsub_parse_folders')
    @patch('check_topics_by_upd_time._legacy.main.save_root_timestamps')
    def test_early_return_when_no_roots(
        self,
        mock_save,
        mock_pubsub,
        mock_get_updates,
        mock_get_roots,
    ):
        mock_get_roots.return_value = []

        from check_topics_by_upd_time._legacy.main import main as legacy_main

        legacy_main({}, None)

        mock_get_updates.assert_not_called()
        mock_pubsub.assert_not_called()
        mock_save.assert_not_called()

    @patch('check_topics_by_upd_time._legacy.main.get_updated_root_folders')
    @patch('check_topics_by_upd_time._legacy.main.get_updates_of_nested_folders')
    @patch('check_topics_by_upd_time._legacy.main.pubsub_parse_folders')
    def test_pubsub_called_with_updated_folders(
        self,
        mock_pubsub,
        mock_get_updates,
        mock_get_roots,
    ):
        mock_get_roots.return_value = [('1', 'ts1')]
        mock_get_updates.return_value = [('1', 'folder1')]

        from check_topics_by_upd_time._legacy.main import main as legacy_main

        legacy_main({}, None)

        mock_pubsub.assert_called_once_with([('1', 'folder1')])

    @patch('check_topics_by_upd_time._legacy.main.get_updated_root_folders')
    @patch('check_topics_by_upd_time._legacy.main.get_updates_of_nested_folders')
    @patch('check_topics_by_upd_time._legacy.main.pubsub_parse_folders')
    def test_pubsub_not_called_when_empty(
        self,
        mock_pubsub,
        mock_get_updates,
        mock_get_roots,
    ):
        mock_get_roots.return_value = [('1', 'ts1')]
        mock_get_updates.return_value = []

        from check_topics_by_upd_time._legacy.main import main as legacy_main

        legacy_main({}, None)

        mock_pubsub.assert_not_called()
