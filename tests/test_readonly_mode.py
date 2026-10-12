"""Read-only mode: view-only handlers keep working, write handlers are skipped (and get the stub).

These tests cover the handler-filtering core only — the actual stub message and the per-bot entry
points are exercised by the smoke run of the bot.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from _dependencies.bot import readonly_mode
from _dependencies.bot.handler_registry import Handler, HandlerConditions, HandlerRegistry
from communicate import main as communicate_main
from communicate._utils.handler_context import TGHandlerContext
from vk_bot._utils import message_processing as vk_processing


def _registry_with(*funcs) -> HandlerRegistry:
    registry = HandlerRegistry()
    for func in funcs:
        registry.register(Handler(func=func, conditions=HandlerConditions(text='кнопка'), priority=0))
    return registry


def _tg_ctx() -> TGHandlerContext:
    update_params = MagicMock()
    update_params.user_id = 1
    return TGHandlerContext(
        update_params=update_params,
        extra_params=MagicMock(),
        db=MagicMock(),
        tg_api=MagicMock(),
    )


def test_is_readonly_reads_the_flag(monkeypatch):
    monkeypatch.setattr(readonly_mode, 'get_app_config', lambda: MagicMock(emergency_readonly_mode=True))
    assert readonly_mode.is_readonly() is True

    monkeypatch.setattr(readonly_mode, 'get_app_config', lambda: MagicMock(emergency_readonly_mode=False))
    assert readonly_mode.is_readonly() is False


def test_telegram_readonly_skips_write_and_runs_view(monkeypatch):
    calls: list[str] = []

    def handle_disable_notifications(ctx):
        calls.append('write')
        ctx.mark_consumed()

    def handle_view_searches(ctx):
        calls.append('view')
        ctx.mark_consumed()

    monkeypatch.setattr(
        communicate_main, 'tg_registry', _registry_with(handle_disable_notifications, handle_view_searches)
    )
    monkeypatch.setattr(communicate_main, 'is_readonly', lambda: True)

    ctx = _tg_ctx()

    assert communicate_main._run_registered_handlers(ctx, text='кнопка') is True
    assert calls == ['view']


def test_telegram_without_readonly_runs_the_write_handler(monkeypatch):
    calls: list[str] = []

    def handle_disable_notifications(ctx):
        calls.append('write')
        ctx.mark_consumed()

    monkeypatch.setattr(communicate_main, 'tg_registry', _registry_with(handle_disable_notifications))
    monkeypatch.setattr(communicate_main, 'is_readonly', lambda: False)

    assert communicate_main._run_registered_handlers(_tg_ctx(), text='кнопка') is True
    assert calls == ['write']


def test_telegram_readonly_only_write_handler_returns_false(monkeypatch):
    """Nothing consumed → the caller sends the stub."""

    def handle_disable_notifications(ctx):
        ctx.mark_consumed()

    monkeypatch.setattr(communicate_main, 'tg_registry', _registry_with(handle_disable_notifications))
    monkeypatch.setattr(communicate_main, 'is_readonly', lambda: True)

    assert communicate_main._run_registered_handlers(_tg_ctx(), text='кнопка') is False


def test_vk_readonly_skips_write_and_runs_view(monkeypatch):
    calls: list[str] = []

    def handle_disable_notifications(ctx):
        calls.append('write')

    def handle_active_searches(ctx):
        calls.append('view')

    monkeypatch.setattr(
        vk_processing, 'vk_registry', _registry_with(handle_disable_notifications, handle_active_searches)
    )
    monkeypatch.setattr(vk_processing, 'is_readonly', lambda: True)

    assert vk_processing._run_registered_handlers(MagicMock(), text='кнопка') is True
    assert calls == ['view']


def test_process_update_readonly_sends_stub_and_skips_writes(monkeypatch):
    """Whole Telegram entry point: read-only mode answers with the stub and writes nothing."""
    from communicate._utils.common import UserInputState

    params = MagicMock()
    params.user_id = 1
    params.got_message = 'привет'
    params.got_callback = None
    params.username = 'u'
    params.user_new_status = None
    params.callback_query = None
    params.user_latitude = None

    monkeypatch.setattr(communicate_main, '_get_basic_update_parameters', lambda update: params)
    monkeypatch.setattr(communicate_main.other_handlers, 'process_unneeded_messages', lambda update, p: False)
    monkeypatch.setattr(communicate_main, 'is_readonly', lambda: True)

    db = MagicMock()
    db.check_if_new_user.return_value = False
    db.get_onboarding_step.return_value = (80, 'done')
    db.get_user_input_state.return_value = UserInputState.not_defined
    monkeypatch.setattr(communicate_main, 'db', lambda: db)
    monkeypatch.setattr(communicate_main, 'tg_api', lambda: MagicMock())

    stub = MagicMock()
    monkeypatch.setattr(communicate_main, '_send_readonly_stub', stub)
    register = MagicMock()
    monkeypatch.setattr(communicate_main, 'register_new_user', register)
    onboarding = MagicMock()
    monkeypatch.setattr(communicate_main, '_run_onboarding', onboarding)

    communicate_main.process_update(MagicMock())

    stub.assert_called_once_with(1)
    db.save_user_message_to_bot.assert_not_called()
    db.delete_last_user_inline_dialogue.assert_not_called()
    register.assert_not_called()
    onboarding.assert_not_called()


# ── MAX: the webhook entry point (what the container actually uses) ─────────────


def test_max_webhook_dispatcher_installs_the_readonly_middleware(monkeypatch):
    """MAX is served over ``/webhook/max`` in the container: the gate must be wired there too."""
    from max_bot import main as max_main
    from max_bot._utils.readonly_middleware import ReadonlyMiddleware

    dp = MagicMock()
    dp.startup = AsyncMock()
    monkeypatch.setattr(max_main, 'Dispatcher', lambda: dp)
    monkeypatch.setattr(max_main, 'Bot', MagicMock)
    monkeypatch.setattr(max_main, '_initialized', False)
    monkeypatch.setattr(max_main, '_bot', None)
    monkeypatch.setattr(max_main, '_dp', None)

    asyncio.run(max_main._init_dispatcher())

    assert dp.register_outer_middleware.call_count == 1
    assert isinstance(dp.register_outer_middleware.call_args.args[0], ReadonlyMiddleware)


def _max_event(user_id: int = 42) -> dict:
    return {
        'update_type': 'message_created',
        'message': {'sender': {'user_id': user_id}, 'body': {'text': 'привет'}},
    }


def _prepare_max_webhook(monkeypatch, *, readonly: bool) -> MagicMock:
    from max_bot import main as max_main

    register = MagicMock()
    monkeypatch.setattr(max_main.handlers, '_ensure_user_registered', register)
    monkeypatch.setattr(max_main, 'is_readonly', lambda: readonly)
    monkeypatch.setattr(max_main, '_initialized', True)
    monkeypatch.setattr(max_main, '_bot', MagicMock())
    monkeypatch.setattr(max_main, '_dp', MagicMock(handle=AsyncMock()))
    monkeypatch.setattr(max_main, 'process_update_webhook', AsyncMock(return_value=MagicMock()))
    return register


def test_max_webhook_readonly_skips_user_registration(monkeypatch):
    """Registration writes to ``users``, so it must be skipped while read-only mode is on."""
    from max_bot import main as max_main

    register = _prepare_max_webhook(monkeypatch, readonly=True)

    asyncio.run(max_main._handle_webhook_async(_max_event()))

    register.assert_not_called()


def test_max_webhook_registers_user_when_not_readonly(monkeypatch):
    from max_bot import main as max_main

    register = _prepare_max_webhook(monkeypatch, readonly=False)

    asyncio.run(max_main._handle_webhook_async(_max_event()))

    register.assert_called_once_with(42)
