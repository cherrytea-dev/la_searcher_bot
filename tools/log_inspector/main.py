#!/usr/bin/env python3
"""YC Log Inspector — Yandex Cloud Logging error investigation tool.

Uses yandexcloud SDK (gRPC) instead of REST API.

Ref: https://github.com/volodkindv/la_searcher_bot/issues/4
Ref: https://github.com/volodkindv/la_searcher_bot/issues/5

Modes:
  top-errors   Aggregate ERROR logs, group by pattern, show top-N with request_ids.
  trace        Get all logs for a specific request_id to reconstruct the full picture.
  list-groups  List available log groups in a YC folder.
  volume       Report log volume per service, extrapolated to a day.
  raw          Raw JSON dump for programmatic use.

Auth:
  YC_LOG_INSPECTOR_SA_JSON env var (service account key JSON)

Usage:
  uv run python tools/log_inspector/main.py top-errors <log-group-id> --hours 24 --top 10
  uv run python tools/log_inspector/main.py trace <log-group-id> <request-id> --hours 24
  uv run python tools/log_inspector/main.py list-groups <folder-id>
  uv run python tools/log_inspector/main.py volume <log-group-id> --hours 24
  uv run python tools/log_inspector/main.py raw <log-group-id> --hours 1 --level ERROR

Known YC Logging quirks (handled automatically):
  * Filtered reads (levels / filter): page_token pagination returns empty
    pages after a criteria with levels+until, so each window is read with one
    criteria request (since+until+levels); a full page (page_size) triggers
    recursive window bisection until every half fits in one page.
  * Unfiltered reads: page_token pagination works; `until` is not sent and
    `to_time` is applied client-side. The window is split into
    `--slice-hours` chunks (default 1h).
  * gRPC UNAVAILABLE / transient errors are retried per request.
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone

import click

from tools.log_inspector._utils.analytics import group_errors
from tools.log_inspector._utils.volume import VolumeAggregator
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
@click.option('--slice-hours', default=1.0, show_default=True, help='Window slice size (hours) for stable pagination')
def top_errors(log_group_id: str, hours: int, top: int, slice_hours: float) -> None:
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
        slice_hours=slice_hours,
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
@click.option('--slice-hours', default=1.0, show_default=True, help='Window slice size (hours) for stable pagination')
@click.option('--filter', '-f', help='Custom filter expression (overrides request_id filter)')
def trace(log_group_id: str, request_id: str, hours: int, slice_hours: float, filter: str | None) -> None:
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
        slice_hours=slice_hours,
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
@click.option('--slice-hours', default=1.0, show_default=True, help='Window slice size (hours) for stable pagination')
def raw(log_group_id: str, hours: int, level: str, slice_hours: float) -> None:
    """Dump raw JSON for a time window."""
    client = _make_client()
    to_time = datetime.now(timezone.utc)
    from_time = to_time - timedelta(hours=hours)

    entries = client.read_all_logs(
        log_group_id,
        levels=[level],
        from_time=from_time,
        to_time=to_time,
        slice_hours=slice_hours,
    )
    click.echo(json.dumps(entries, indent=2, ensure_ascii=False))


@cli.command()
@click.argument('log_group_id')
@click.option('--hours', default=24, show_default=True, help='Window length (hours) to report on')
@click.option('--sample-every', default=1, show_default=True, help='Read every Nth hour only, then extrapolate')
@click.option('--start-offset', default=0, show_default=True, help='Offset (hours) of the first sampled slice')
@click.option('--top-messages', default=3, show_default=True, help='Top messages shown per service')
@click.option('--top-biggest', default=5, show_default=True, help='Fattest records shown')
@click.option('--json', 'as_json', is_flag=True, help='Emit JSON instead of a table')
def volume(
    log_group_id: str,
    hours: int,
    sample_every: int,
    start_offset: int,
    top_messages: int,
    top_biggest: int,
    as_json: bool,
) -> None:
    """Report log volume per service, extrapolated to a full day.

    Reads the window hour by hour and folds entries as they arrive (~1.6M
    records / ~1 GB a day on the prod group — far too much to hold in memory),
    so the run is I/O bound: around a minute per hourly slice.
    """
    sample_every = max(1, sample_every)
    client = _make_client()
    to_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    from_time = to_time - timedelta(hours=hours)
    aggregator = VolumeAggregator(top_biggest=top_biggest)

    click.echo(
        f'⏳ Reading log volume for the last {hours}h (every {sample_every}h slice, phase {start_offset}) …',
        err=True,
    )
    hour = from_time + timedelta(hours=start_offset)
    index = 0
    while hour < to_time:
        index += 1
        if (index - 1) % sample_every == 0:
            slice_end = min(hour + timedelta(hours=1), to_time)
            started = time.monotonic()
            entries = client.read_all_logs(log_group_id, from_time=hour, to_time=slice_end, slice_hours=0)
            slice_bytes = aggregator.add_slice(entries)
            click.echo(
                f'  [{hour:%m-%d %H:%M}] {len(entries)} records, {slice_bytes / 1e6:.1f} MB, '
                f'{time.monotonic() - started:.0f}s',
                err=True,
            )
        hour += timedelta(hours=1)

    report = aggregator.report(hours)
    if as_json:
        click.echo(
            json.dumps(report.to_dict(top_messages=top_messages, top_biggest=top_biggest), indent=2, ensure_ascii=False)
        )
        return
    click.echo(report.render(top_messages=top_messages, top_biggest=top_biggest))


def _make_client() -> YCLoggingClient:
    try:
        return YCLoggingClient()
    except AuthError as exc:
        click.secho(f'💥 Auth error: {exc}', fg='red', err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()
