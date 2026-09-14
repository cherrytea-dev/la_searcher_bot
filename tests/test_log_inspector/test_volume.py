"""Tests for YC Log Inspector — volume aggregation module."""

import json

from tools.log_inspector._utils.volume import (
    UNKNOWN_STREAM,
    StreamStats,
    VolumeAggregator,
    VolumeReport,
    entry_size,
    message_of,
    preview,
    stream_of,
)


def _entry(**payload: object) -> dict:
    return {'json_payload': payload}


class TestStreamOf:
    def test_from_json_payload(self) -> None:
        assert stream_of(_entry(stream_name='send_notifications')) == 'send_notifications'

    def test_from_json_payload_camel_case(self) -> None:
        assert stream_of(_entry(streamName='compose_notifications')) == 'compose_notifications'

    def test_repeated_field_is_flattened(self) -> None:
        assert stream_of(_entry(stream_name=['title_recognize'])) == 'title_recognize'

    def test_falls_back_to_platform_stream_name(self) -> None:
        assert stream_of({'stream_name': 'platform-stream'}) == 'platform-stream'

    def test_unknown_when_nothing_is_set(self) -> None:
        assert stream_of({}) == UNKNOWN_STREAM

    def test_json_payload_of_unexpected_type_is_ignored(self) -> None:
        assert stream_of({'json_payload': 'not-a-dict', 'stream_name': 'fallback'}) == 'fallback'


class TestMessageOf:
    def test_from_json_payload(self) -> None:
        assert message_of(_entry(message='hello')) == 'hello'

    def test_from_json_payload_msg_alias(self) -> None:
        assert message_of(_entry(msg='hello')) == 'hello'

    def test_repeated_field_is_flattened(self) -> None:
        assert message_of(_entry(message=['first', 'second'])) == 'first'

    def test_falls_back_to_platform_message(self) -> None:
        assert message_of({'message': 'plain'}) == 'plain'

    def test_empty_when_nothing_is_set(self) -> None:
        assert message_of({}) == ''


class TestEntrySize:
    def test_counts_utf8_bytes(self) -> None:
        assert entry_size({'message': 'аб'}) > entry_size({'message': 'ab'})

    def test_bigger_entry_is_bigger(self) -> None:
        assert entry_size({'message': 'x' * 100}) > entry_size({'message': 'x'})

    def test_handles_non_json_values(self) -> None:
        assert entry_size({'ts': object()}) > 0


class TestPreview:
    def test_collapses_whitespace(self) -> None:
        assert preview('line one\n  line two') == 'line one line two'

    def test_truncates_to_width(self) -> None:
        assert len(preview('x' * 500, width=10)) == 10


class TestVolumeAggregator:
    def _aggregator(self) -> VolumeAggregator:
        return VolumeAggregator(top_biggest=2)

    def test_counts_records_per_stream(self) -> None:
        aggregator = self._aggregator()
        aggregator.add_slice([_entry(stream_name='a'), _entry(stream_name='a'), _entry(stream_name='b')])

        report = aggregator.report(window_hours=1)
        counts = {stream.name: stream.count for stream in report.streams}
        assert counts == {'a': 2, 'b': 1}
        assert report.total_count == 3

    def test_returns_slice_size(self) -> None:
        aggregator = self._aggregator()
        slice_bytes = aggregator.add_slice([_entry(stream_name='a', message='hello')])

        assert slice_bytes == entry_size(_entry(stream_name='a', message='hello'))

    def test_empty_slice_still_counts_as_read_hour(self) -> None:
        aggregator = self._aggregator()
        assert aggregator.add_slice([]) == 0
        assert aggregator.report(window_hours=1).hours_read == 1

    def test_streams_sorted_by_size(self) -> None:
        aggregator = self._aggregator()
        aggregator.add_slice([_entry(stream_name='small', message='x')])
        aggregator.add_slice([_entry(stream_name='big', message='y' * 500)])

        report = aggregator.report(window_hours=2)
        assert [stream.name for stream in report.streams] == ['big', 'small']

    def test_levels_counted_per_stream(self) -> None:
        aggregator = self._aggregator()
        aggregator.add_slice([{'level': 'ERROR', 'json_payload': {'stream_name': 'a'}}])

        report = aggregator.report(window_hours=1)
        assert report.streams[0].levels == {'ERROR': 1}

    def test_missing_level_is_marked(self) -> None:
        aggregator = self._aggregator()
        aggregator.add_slice([_entry(stream_name='a')])

        assert aggregator.report(window_hours=1).streams[0].levels == {'?': 1}

    def test_top_messages_are_counted(self) -> None:
        aggregator = self._aggregator()
        aggregator.add_slice([_entry(stream_name='a', message='boom')] * 3)

        report = aggregator.report(window_hours=1)
        assert report.streams[0].messages['boom'] == 3

    def test_biggest_records_are_kept_sorted(self) -> None:
        aggregator = self._aggregator()
        aggregator.add_slice(
            [
                _entry(stream_name='a', message='small'),
                _entry(stream_name='b', message='x' * 500),
                _entry(stream_name='c', message='y' * 300),
            ],
        )

        report = aggregator.report(window_hours=1)
        assert [stream for _, stream, _ in report.biggest] == ['b', 'c']

    def test_biggest_can_be_disabled(self) -> None:
        aggregator = VolumeAggregator(top_biggest=0)
        aggregator.add_slice([_entry(stream_name='a', message='x' * 500)])

        assert aggregator.report(window_hours=1).biggest == []


class TestVolumeReport:
    def _report(self, hours_read: float = 24, window_hours: float = 24) -> VolumeReport:
        aggregator = VolumeAggregator()
        for _ in range(int(hours_read)):
            aggregator.add_slice([_entry(stream_name='send_notifications', message='hello')])
        return aggregator.report(window_hours=window_hours)

    def test_share_sums_to_hundred(self) -> None:
        aggregator = VolumeAggregator()
        aggregator.add_slice([_entry(stream_name='a', message='x'), _entry(stream_name='b', message='x')])

        report = aggregator.report(window_hours=1)
        assert sum(report.share(stream) for stream in report.streams) == 100.0

    def test_scale_is_one_for_a_full_window(self) -> None:
        assert self._report().scale == 1.0

    def test_scale_extrapolates_sampled_window(self) -> None:
        report = self._report(hours_read=6, window_hours=24)
        assert report.scale == 4.0
        assert report.per_day_count == report.total_count * 4

    def test_scale_is_zero_without_read_hours(self) -> None:
        report = VolumeReport(hours_read=0, window_hours=24, streams=[])
        assert report.scale == 0.0
        assert report.per_day_size == 0.0

    def test_bytes_per_record_averages(self) -> None:
        aggregator = VolumeAggregator()
        aggregator.add_slice([_entry(stream_name='a', message='x' * 10), _entry(stream_name='a', message='y' * 20)])

        report = aggregator.report(window_hours=1)
        assert report.streams[0].bytes_per_record == report.streams[0].size / 2

    def test_bytes_per_record_is_zero_without_records(self) -> None:

        assert StreamStats(name='empty').bytes_per_record == 0.0

    def test_to_dict_is_json_serializable(self) -> None:

        payload = self._report().to_dict()
        assert json.loads(json.dumps(payload))['total_records'] == 24
        assert payload['streams'][0]['name'] == 'send_notifications'

    def test_render_contains_totals_and_services(self) -> None:
        rendered = self._report().render()
        assert 'send_notifications' in rendered
        assert 'TOTAL' in rendered
        assert 'Hours read: 24' in rendered

    def test_render_of_empty_report_does_not_fail(self) -> None:
        rendered = VolumeReport(hours_read=1, window_hours=1, streams=[]).render()
        assert 'TOTAL' in rendered
        assert 'Top messages' not in rendered

    def test_render_keeps_columns_aligned_for_long_service_names(self) -> None:
        aggregator = VolumeAggregator()
        aggregator.add_slice([_entry(stream_name='identify_updates_of_first_posts._legacy', message='x')])

        rendered = aggregator.report(window_hours=1).render()
        table_lines = [
            line
            for line in rendered.splitlines()
            if line.startswith(('Service', 'identify_updates_of_first_posts._legacy', 'TOTAL'))
        ]
        assert len({len(line) for line in table_lines}) == 1
