#!/usr/bin/env python3
"""
YC Log Inspector — Yandex Cloud Logging error investigation tool.

Ref: https://github.com/volodkindv/la_searcher_bot/issues/4
Ref: https://github.com/volodkindv/la_searcher_bot/issues/5

Modes:
  top-errors   Aggregate ERROR logs, group by pattern, show top-N with request_ids.
  trace        Get all logs for a specific request_id to reconstruct the full picture.
  list-groups  List available log groups in a YC folder.
  raw          Raw JSON dump for programmatic use.

Auth (priority):
  1. YC_IAM_TOKEN env var
  2. YC_LOG_INSPECTOR_SA_JSON env var
  3. YC metadata service (inside VMs / Cloud Functions)
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from tools.log_inspector._utils.analytics import group_errors
from tools.log_inspector._utils.yc_logging import YCLoggingClient


def _color_for_level(level: str) -> str:
    """ANSI color codes for log levels."""
    if level in ('ERROR', 'FATAL', 'CRITICAL'):
        return '\033[91m'  # red
    if level == 'WARN':
        return '\033[93m'  # yellow
    if level == 'INFO':
        return '\033[92m'  # green
    return ''


def _color_reset() -> str:
    return '\033[0m'


def cmd_top_errors(args: argparse.Namespace) -> None:
    """Aggregate ERROR logs and show top patterns."""
    client = YCLoggingClient()
    to_time = datetime.now(timezone.utc)
    from_time = to_time - timedelta(hours=args.hours)

    print(f'⏳ Fetching ERROR logs for the last {args.hours}h …', file=sys.stderr)
    entries = client.read_all_logs(
        args.log_group_id,
        levels=['ERROR'],
        from_time=from_time,
        to_time=to_time,
    )
    error_entries = [e for e in entries if e.get('level') == 'ERROR']

    print(
        f'📊 Found {len(error_entries)} ERROR entries '
        f'(out of {len(entries)} total).\n',
        file=sys.stderr,
    )

    if not error_entries:
        print('✅ No ERROR entries in the selected window.')
        return

    groups = group_errors(error_entries, top_n=args.top)
    for i, group in enumerate(groups):
        print(f'{"=" * 80}')
        print(f'#{i + 1}  —  {group.count} occurrences')
        print(f'{"=" * 80}')
        print(f'{group.sample_message[:600]}')
        if group.sample_request_ids:
            print()
            for rid in group.sample_request_ids:
                print(f'  🔗 request_id: {rid}')
            print()
        print()


def cmd_trace(args: argparse.Namespace) -> None:
    """Trace all log entries for a specific request_id."""
    client = YCLoggingClient()
    to_time = datetime.now(timezone.utc)
    from_time = to_time - timedelta(hours=args.hours)

    filter_expr = args.filter or f'request_id="{args.request_id}"'

    print(
        f'🔍 Tracing request_id="{args.request_id}" '
        f'for the last {args.hours}h …',
        file=sys.stderr,
    )
    entries = client.read_all_logs(
        args.log_group_id,
        filter_str=filter_expr,
        from_time=from_time,
        to_time=to_time,
    )
    print(
        f'📊 Found {len(entries)} entries.\n', file=sys.stderr,
    )

    if not entries:
        print(f'No entries found for request_id="{args.request_id}".')
        return

    for entry in entries:
        ts = entry.get('timestamp', '')[:19]
        level = entry.get('level', 'UNKNOWN')
        message = entry.get('message', '')

        color = _color_for_level(level)
        reset = _color_reset()
        print(f'[{ts}] {color}{level}{reset}')
        print(f'  {message[:500]}')
        print()


def cmd_list_groups(args: argparse.Namespace) -> None:
    """List log groups in a YC folder."""
    client = YCLoggingClient()
    groups = client.list_log_groups(args.folder_id)

    name_w = min(max(len(g.name) for g in groups), 50) if groups else 8
    print(f'{"ID":48s}  {"NAME":{name_w}s}')
    print(f'{"-" * 48}  {"-" * name_w}')
    for g in groups:
        print(f'{g.id:48s}  {g.name}')


def cmd_raw(args: argparse.Namespace) -> None:
    """Dump raw JSON for a time window."""
    client = YCLoggingClient()
    to_time = datetime.now(timezone.utc)
    from_time = to_time - timedelta(hours=args.hours)

    entries = client.read_all_logs(
        args.log_group_id,
        levels=[args.level] if args.level else None,
        from_time=from_time,
        to_time=to_time,
    )
    print(json.dumps(entries, indent=2, ensure_ascii=False))


def main() -> None:  # pragma: no cover
    parser = argparse.ArgumentParser(
        prog='log_inspector',
        description='YC Log Inspector — investigate errors in Yandex Cloud Logging.',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    # top-errors
    p = sub.add_parser('top-errors', help='Show top ERROR patterns')
    p.add_argument('log_group_id')
    p.add_argument('--hours', type=int, default=24)
    p.add_argument('--top', type=int, default=10)
    p.set_defaults(func=cmd_top_errors)

    # trace
    p = sub.add_parser('trace', help='Trace all logs for a request_id')
    p.add_argument('log_group_id')
    p.add_argument('request_id')
    p.add_argument('--hours', type=int, default=24)
    p.add_argument('--filter', help='Custom filter (overrides request_id filter)')
    p.set_defaults(func=cmd_trace)

    # list-groups
    p = sub.add_parser('list-groups', help='List log groups in a folder')
    p.add_argument('folder_id')
    p.set_defaults(func=cmd_list_groups)

    # raw
    p = sub.add_parser('raw', help='Raw JSON dump')
    p.add_argument('log_group_id')
    p.add_argument('--hours', type=int, default=1)
    p.add_argument('--level', default='ERROR')
    p.set_defaults(func=cmd_raw)

    args = parser.parse_args()

    try:
        args.func(args)
    except Exception as exc:
        print(f'💥 Error: {exc}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
