"""Tests for log level configuration in :mod:`_dependencies.common.yandex_tools`.

Behaviour under test:
- ``LOG_LEVEL`` drives the root logger level; unset/unrecognized falls back to WARN
- noisy third-party loggers (botocore/httpx/...) are pinned to the level from ``NOISY_LOGGERS``
- the level is set in one place only: no module silences its own loggers
"""

import logging
import pathlib

import pytest

from _dependencies.common.yandex_tools import (
    DEFAULT_LOG_LEVEL,
    NOISY_LOGGERS,
    resolve_log_level,
    setup_logging_cloud,
)


@pytest.fixture
def restore_logging():
    """Restore root logger and noisy loggers after a test touches global state."""
    root_logger = logging.getLogger()
    saved_level = root_logger.level
    saved_handlers = list(root_logger.handlers)
    saved_noisy = {name: logging.getLogger(name).level for name in NOISY_LOGGERS}

    yield

    root_logger.setLevel(saved_level)
    root_logger.handlers.clear()
    root_logger.handlers.extend(saved_handlers)
    for name, level in saved_noisy.items():
        logging.getLogger(name).setLevel(level)


class TestResolveLogLevel:
    @pytest.mark.parametrize(
        ('raw_level', 'expected'),
        [
            ('DEBUG', logging.DEBUG),
            ('debug', logging.DEBUG),
            ('Info', logging.INFO),
            ('info', logging.INFO),
            ('WARN', logging.WARNING),
            ('WARNING', logging.WARNING),
            ('warn', logging.WARNING),
            ('error', logging.ERROR),
            ('critical', logging.CRITICAL),
            ('  info  ', logging.INFO),
        ],
    )
    def test_recognizes_levels_case_insensitively(self, raw_level: str, expected: int) -> None:
        assert resolve_log_level(raw_level) == expected

    @pytest.mark.parametrize('raw_level', ['', '   ', 'verbose', 'log', '11'])
    def test_unrecognized_values_fall_back_to_default(self, raw_level: str) -> None:
        assert resolve_log_level(raw_level) == getattr(logging, DEFAULT_LOG_LEVEL)

    def test_unset_env_var_falls_back_to_warn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv('LOG_LEVEL', raising=False)

        assert resolve_log_level() == logging.WARNING

    def test_reads_env_var_when_no_argument_is_given(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('LOG_LEVEL', 'info')

        assert resolve_log_level() == logging.INFO


class TestSetupLoggingCloud:
    def test_default_level_is_warn(self, monkeypatch: pytest.MonkeyPatch, restore_logging) -> None:
        monkeypatch.delenv('LOG_LEVEL', raising=False)

        setup_logging_cloud('some_service')

        assert logging.getLogger().level == logging.WARNING

    def test_explicit_level_from_env(self, monkeypatch: pytest.MonkeyPatch, restore_logging) -> None:
        monkeypatch.setenv('LOG_LEVEL', 'info')

        setup_logging_cloud('some_service')

        assert logging.getLogger().level == logging.INFO

    def test_debug_level_from_env(self, monkeypatch: pytest.MonkeyPatch, restore_logging) -> None:
        monkeypatch.setenv('LOG_LEVEL', 'DEBUG')

        setup_logging_cloud('some_service')

        assert logging.getLogger().level == logging.DEBUG

    def test_unknown_level_logs_error_and_keeps_working(
        self,
        monkeypatch: pytest.MonkeyPatch,
        restore_logging,
        capsys,
    ) -> None:
        monkeypatch.setenv('LOG_LEVEL', 'loud')

        setup_logging_cloud('some_service')

        # NB: setup_logging_cloud replaces root handlers, so the record is checked in stdout
        assert logging.getLogger().level == logging.WARNING
        output = capsys.readouterr().out
        assert 'Unknown LOG_LEVEL' in output
        assert '"level": "ERROR"' in output

    def test_noisy_loggers_are_capped_at_warning(self, monkeypatch: pytest.MonkeyPatch, restore_logging) -> None:
        monkeypatch.setenv('LOG_LEVEL', 'DEBUG')
        logging.getLogger('botocore').setLevel(logging.DEBUG)
        logging.getLogger('httpx').setLevel(logging.DEBUG)

        setup_logging_cloud('some_service')

        for logger_name in ('botocore', 'httpx'):
            logger = logging.getLogger(logger_name)
            assert logger.level == logging.WARNING
            assert logger.isEnabledFor(logging.INFO) is False

    def test_keeps_single_stdout_handler(self, monkeypatch: pytest.MonkeyPatch, restore_logging) -> None:
        monkeypatch.delenv('LOG_LEVEL', raising=False)
        root_logger = logging.getLogger()
        root_logger.addHandler(logging.NullHandler())

        setup_logging_cloud('some_service')

        assert len(root_logger.handlers) == 1
        assert isinstance(root_logger.handlers[0], logging.StreamHandler)

    def test_info_is_filtered_out_by_default(self, monkeypatch: pytest.MonkeyPatch, restore_logging) -> None:
        monkeypatch.delenv('LOG_LEVEL', raising=False)
        setup_logging_cloud('some_service')

        assert logging.getLogger().isEnabledFor(logging.INFO) is False
        assert logging.getLogger().isEnabledFor(logging.WARNING) is True

    @pytest.mark.parametrize(('logger_name', 'expected_level'), list(NOISY_LOGGERS.items()))
    def test_noisy_logger_keeps_its_pinned_level(
        self,
        monkeypatch: pytest.MonkeyPatch,
        restore_logging,
        logger_name: str,
        expected_level: int,
    ) -> None:
        monkeypatch.setenv('LOG_LEVEL', 'DEBUG')
        logging.getLogger(logger_name).setLevel(logging.DEBUG)

        setup_logging_cloud('some_service')

        assert logging.getLogger(logger_name).level == expected_level


class TestNoPerModuleLevelOverrides:
    """`LOG_LEVEL` is the only knob: per-module setLevel() calls are legacy (see #46 review)."""

    def test_only_common_logging_module_touches_logger_levels(self) -> None:
        src_root = pathlib.Path(__file__).resolve().parents[2] / 'src'

        level_setters = [
            f'{path.relative_to(src_root)}:{line_number}'
            for path in sorted(src_root.rglob('*.py'))
            for line_number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1)
            if 'setLevel(' in line and path.name != 'yandex_tools.py'
        ]

        assert level_setters == []
