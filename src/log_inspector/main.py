#!/usr/bin/env python3
"""Yandex Cloud Log Inspector — CLI tool for error investigation.

Usage:
  # List available log groups
  python -m src.log_inspector.main list-groups

  # Find top errors in the last 24 hours
  python -m src.log_inspector.main top-errors \\
      --group <log_group_id> --since 24h

  # Trace a specific request_id
  python -m src.log_inspector.main trace \\
      --group <log_group_id> --request-id <req_id>
"""

import argparse
import json
import logging
import sys
from datetime import timedelta

from src.log_inspector._utils.analytics import (
    _extract_request_id,
    _get_message,
    summarize_errors,
)
from src.log_inspector._utils.yc_logging import YcLoggingClient

logger = logging.getLogger(__name__)


def _parse_duration(text: str) -> timedelta:
    """Parse duration string like '24h', '7d', '30m' into timedelta."""
    text = text.strip().lower()
    if text.endswith('h'):
        return timedelta(hours=int(text[:-1]))
    if text.endswith('d'):
        return timedelta(days=int(text[:-1]))
    if text.endswith('m'):
        return timedelta(minutes=int(text[:-1]))
    if text.endswith('s'):
        return timedelta(seconds=int(text[:-1]))
    raise ValueError(f'Unrecognized duration format: {text!r} (use e.g. 24h, 7d, 30m)')


def cmd_list_groups(args: argparse.Namespace) -> None:
    """List all available log groups."""
    client = YcLoggingClient(folder_id=args.folder)
    try:
        groups = client.list_log_groups()
        if not groups:
            print('No log groups found.')
            return

        print(f'Found {len(groups)} log group(s):')
        print()
        for g in groups:
            gid = g.get('id', '?')
            name = g.get('name', '(unnamed)')
            desc = g.get('description', '')
            print(f'  {gid}  — {name}')
            if desc:
                print(f'           {desc}')
    finally:
        client.close()


def cmd_top_errors(args: argparse.Namespace) -> None:
    """Find and display the most frequent errors."""
    since = _parse_duration(args.since)
    level = args.level.upper()

    client = YcLoggingClient(folder_id=args.folder)
    try:
        print(f'Querying {level}-level logs from last {args.since}...', file=sys.stderr)
        entries = client.read_all_logs(
            args.group,
            level=level,
            since=since,
            max_entries=args.max,
        )
        print(f'  Retrieved {len(entries)} entries.', file=sys.stderr)
        print(file=sys.stderr)

        summary = summarize_errors(entries, top_n=args.top)
        print(summary)
    finally:
        client.close()


def cmd_trace(args: argparse.Namespace) -> None:
    """Show all logs for a specific request_id."""
    since = _parse_duration(args.since)

    client = YcLoggingClient(folder_id=args.folder)
    try:
        entries = client.get_logs_by_request_id(
            args.group,
            args.request_id,
            since=since,
            max_entries=args.max,
        )

        if not entries:
            print(f'No log entries found for request_id={args.request_id}')
            return

        print(f'Found {len(entries)} log entries for request_id={args.request_id}:')
        print()

        for entry in sorted(entries, key=lambda e: e.get('timestamp', '')):
            ts = entry.get('timestamp', '?')
            level = entry.get('level', entry.get('severity', '?')).ljust(7)
            msg = _get_message(entry)
            print(f'  [{ts}] {level} {msg[:300]}')
    finally:
        client.close()


def cmd_raw(args: argparse.Namespace) -> None:
    """Raw JSON query — dump results for programmatic use."""
    since = _parse_duration(args.since)

    client = YcLoggingClient(folder_id=args.folder)
    try:
        entries = client.read_all_logs(
            args.group,
            level=args.level.upper(),
            since=since,
            filter_str=args.filter,
            max_entries=args.max,
        )
        print(json.dumps(entries, indent=2, ensure_ascii=False, default=str))
    finally:
        client.close()


class _HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Custom formatter to show the docstring as the description."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='log-inspector',
        description=__doc__,
        formatter_class=_HelpFormatter,
    )
    parser.add_argument(
        '--folder',
        default=None,
        help='Yandex Cloud folder ID (default: YC_FOLDER_ID env var)',
    )

    sub = parser.add_subparsers(dest='cmd', required=True)

    # list-groups
    p_list = sub.add_parser('list-groups', help='List available log groups')

    # top-errors
    p_errors = sub.add_parser('top-errors', help='Find most frequent errors')
    p_errors.add_argument('--group', required=True, help='Log group ID')
    p_errors.add_argument('--since', default='24h', help='Lookback period (default: 24h)')
    p_errors.add_argument('--level', default='ERROR', help='Minimum log level (default: ERROR)')
    p_errors.add_argument('--top', type=int, default=10, help='Show top N error patterns')
    p_errors.add_argument('--max', type=int, default=5000, help='Max entries to scan')

    # trace
    p_trace = sub.add_parser('trace', help='Trace a specific request_id')
    p_trace.add_argument('--group', required=True, help='Log group ID')
    p_trace.add_argument('--request-id', required=True, help='Request ID to trace')
    p_trace.add_argument('--since', default='24h', help='Lookback period (default: 24h)')
    p_trace.add_argument('--max', type=int, default=500, help='Max entries to return')

    # raw
    p_raw = sub.add_parser('raw', help='Dump raw JSON logs')
    p_raw.add_argument('--group', required=True, help='Log group ID')
    p_raw.add_argument('--since', default='24h', help='Lookback period (default: 24h)')
    p_raw.add_argument('--level', default='ERROR', help='Minimum log level (default: ERROR)')
    p_raw.add_argument('--filter', default=None, help='Additional filter string')
    p_raw.add_argument('--max', type=int, default=100, help='Max entries to return')

    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)

    try:
        if args.cmd == 'list-groups':
            cmd_list_groups(args)
        elif args.cmd == 'top-errors':
            cmd_top_errors(args)
        elif args.cmd == 'trace':
            cmd_trace(args)
        elif args.cmd == 'raw':
            cmd_raw(args)
    except Exception:
        logger.exception('Command failed')
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
