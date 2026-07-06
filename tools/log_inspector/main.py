#!/usr/bin/env python3
"""YC Log Inspector — Yandex Cloud Logging error investigation tool.

Ref: https://github.com/volodkindv/la_searcher_bot/issues/4
Ref: https://github.com/volodkindv/la_searcher_bot/issues/5

Modes:
  top-errors   Aggregate ERROR logs, group by pattern, show top-N with request_ids.
  trace        Get all logs for a specific request_id to reconstruct the full picture.
  list-groups  List available log groups in a YC folder.
  raw          Raw JSON dump for programmatic use.

Auth:
  YC_IAM_TOKEN env var (obtain via: yc iam create-token)

Usage:
  uv run python tools/log_inspector/main.py top-errors <log-group-id> --hours 24 --top 10
  uv run python tools/log_inspector/main.py trace <log-group-id> <request-id> --hours 24
  uv run python tools/log_inspector/main.py list-groups <folder-id>
  uv run python tools/log_inspector/main.py raw <log-group-id> --hours 1 --level ERROR
"""

import json
import sys
from datetime import datetime, timedelta, timezone

import click

from tools.log_inspector._utils.analytics import group_errors
from tools.log_inspector._utils.yc_logging import AuthError, YCLoggingClient

_COLORS = {
    'ERROR': 'red',
    'FATAL': 'red',
    'CRITICAL': 'red',
    'WARN': 'yellow',
    'INFO': 'green',
}


@click.group()
def cli() -> None:
    """YC Log Inspector — investigate errors in Yandex Cloud Logging."""


@cli.command()
@click.argument('log_group_id')
@click.option('--hours', default=24, show_default=True, help='Time window (hours)')
@click.option('--top', default=10, show_default=True, help='Number of top error patterns')
def top_errors(log_group_id: str, hours: int, top: int) -> None:
    """Aggregate ERROR logs by normalized pattern."""
    client = _make_client()
    to_time = datetime.now(timezone.utc)
    from_time = to_time - timedelta(hours=hours)

    click.echo(f'⏳ Fetching ERROR logs for the last {hours}h …', err=True)
    entries = client.read_all_logs(
        log_group_id,
        levels=['ERROR'],
        from_time=from_time,
        to_time=to_time,
    )
    error_entries = [e for e in entries if e.get('level') == 'ERROR']
    click.echo(
        f'📊 Found {len(error_entries)} ERROR entries (out of {len(entries)} total).\n',
        err=True,
    )

    if not error_entries:
        click.secho('✅ No ERROR entries in the selected window.', fg='green')
        return

    groups = group_errors(error_entries, top_n=top)
    for i, group in enumerate(groups):
        click.echo('=' * 80)
        click.echo(f'#{i + 1}  —  {group.count} occurrences')
        click.echo('=' * 80)
        click.echo(group.sample_message[:600])
        if group.sample_request_ids:
            click.echo()
            for rid in group.sample_request_ids:
                click.echo(f'  🔗 request_id: {rid}')
            click.echo()


@cli.command()
@click.argument('log_group_id')
@click.argument('request_id')
@click.option('--hours', default=24, show_default=True, help='Time window (hours)')
@click.option('--filter', '-f', help='Custom filter expression (overrides request_id filter)')
def trace(log_group_id: str, request_id: str, hours: int, filter: str | None) -> None:
    """Trace all log entries for a specific request_id."""
    client = _make_client()
    to_time = datetime.now(timezone.utc)
    from_time = to_time - timedelta(hours=hours)

    filter_expr = filter or f'request_id="{request_id}"'
    click.echo(f'🔍 Tracing request_id="{request_id}" for the last {hours}h …', err=True)

    entries = client.read_all_logs(
        log_group_id,
        filter_str=filter_expr,
        from_time=from_time,
        to_time=to_time,
    )
    click.echo(f'📊 Found {len(entries)} entries.\n', err=True)

    if not entries:
        click.echo(f'No entries found for request_id="{request_id}".')
        return

    for entry in entries:
        ts = entry.get('timestamp', '')[:19]
        level = entry.get('level', 'UNKNOWN')
        message = entry.get('message', '')

        color = _COLORS.get(level)
        click.echo(f'[{ts}] {click.style(level, fg=color)}')
        click.echo(f'  {message[:500]}')
        click.echo()


@cli.command()
@click.argument('folder_id')
def list_groups(folder_id: str) -> None:
    """List available log groups in a YC folder."""
    client = _make_client()
    groups = client.list_log_groups(folder_id)

    for g in groups:
        click.echo(f'{g.id}  {g.name}')


@cli.command()
@click.argument('log_group_id')
@click.option('--hours', default=1, show_default=True, help='Time window (hours)')
@click.option('--level', default='ERROR', show_default=True, help='Log level filter')
def raw(log_group_id: str, hours: int, level: str) -> None:
    """Dump raw JSON for a time window."""
    client = _make_client()
    to_time = datetime.now(timezone.utc)
    from_time = to_time - timedelta(hours=hours)

    entries = client.read_all_logs(
        log_group_id,
        levels=[level],
        from_time=from_time,
        to_time=to_time,
    )
    click.echo(json.dumps(entries, indent=2, ensure_ascii=False))


def _make_client() -> YCLoggingClient:
    try:
        return YCLoggingClient()
    except AuthError as exc:
        click.secho(f'💥 Auth error: {exc}', fg='red', err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()
