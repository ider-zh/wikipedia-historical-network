"""Independent review regressions; fixtures never inspect source payloads."""
import copy
import datetime as dt
import gzip
import json
from pathlib import Path
import tempfile
from typing import Any
import unittest

from whn import planner, project


class InstantRegressionTests(unittest.TestCase):
    def test_instant_normalizes_offsets_and_interprets_naive_values_as_utc(self):
        expected = dt.datetime(2026, 9, 30, 16, tzinfo=dt.timezone.utc)
        for value in ('2026-10-01T00:00:00+08:00',
                      '2026-09-30T11:00:00-05:00',
                      '2026-09-30T16:00:00Z',
                      '2026-09-30T16:00:00'):
            with self.subTest(value=value):
                self.assertEqual(planner.instant(value), expected)
                self.assertIs(planner.instant(value).tzinfo, dt.timezone.utc)

    def test_offset_as_of_before_utc_q3_end_stops_at_q2(self):
        targets = planner.quarter_targets('2026-01-01', '2026-10-01T00:00:00+08:00')
        self.assertEqual(targets, ['2026-03-31T23:59:59Z', '2026-06-30T23:59:59Z'])


ALL_COMPONENTS = {'page_network', 'category_observations_xml', 'category_observations_sql',
                  'category_union', 'category_graph', 'statistics'}


def recipe(xml_id='xml-old', sql_id='sql-old'):
    sources = [dict(id=xml_id, wiki='enwiki', date='2020-01-01',
                    kind='history_xml', eligible=True, file_count=1),
               dict(id=sql_id, wiki='enwiki', date='2004-12-31',
                    kind='category_sql', eligible=True, file_count=2)]
    plan = planner.plan_snapshot('enwiki', '2004-12-31T23:59:59Z', sources)
    plan['build_context'] = dict(graph_schema='graph-v1', xml_adapter='parser-v1')
    return plan


class VersionRegressionTests(unittest.TestCase):
    def test_simultaneous_xml_sql_changes_invalidate_both_observations(self):
        previous = planner.version_plan(recipe(), None)
        changed = recipe(xml_id='xml-new', sql_id='sql-new')
        current = planner.version_plan(changed, previous)
        invalidated = current['invalidated_components']
        assert isinstance(invalidated, list)
        self.assertEqual(set(invalidated), ALL_COMPONENTS)
        self.assertEqual(len(invalidated), len(ALL_COMPONENTS))
        self.assertEqual(current['plan_version'], 2)
        self.assertEqual(current['supersedes'], previous['recipe_sha256'])
        self.assertEqual(planner.version_plan(changed, current), current)

    def test_build_context_changes_invalidate_all_without_source_changes(self):
        previous = planner.version_plan(recipe(), None)
        for field in ('graph_schema', 'xml_adapter', 'wikitext_adapter'):
            with self.subTest(field=field):
                changed = recipe()
                context = changed['build_context']
                assert isinstance(context, dict)
                context[field] = 'new-version'
                current = planner.version_plan(changed, previous)
                self.assertEqual(current['xml_source'], previous['xml_source'])
                self.assertEqual(current['sql_source'], previous['sql_source'])
                invalidated = current['invalidated_components']
                assert isinstance(invalidated, list)
                self.assertEqual(set(invalidated), ALL_COMPONENTS)
                self.assertEqual(current['plan_version'], 2)
                self.assertEqual(current['supersedes'], previous['recipe_sha256'])
                self.assertEqual(planner.version_plan(changed, current), current)


def inventory_events():
    host = 'fixture-host'
    row = dict(type='file', host=host, root='/a',
               path='/a/enwiki-20200101-pages-meta-history.xml.7z',
               size_bytes=123, mtime_ns=1, device=1, inode=1,
               inferred_wikis=['enwiki'], inferred_dates=['20200101'],
               representation='xml_history', tables=[],
               source_eligible_candidate=True, truncated=False)
    return [dict(type='discovery', host=host, roots=['/a']),
            dict(type='root_start', host=host, root='/a'), row,
            dict(type='root_end', host=host, root='/a', files=1,
                 status='complete', errors=0, truncated=False),
            dict(type='host_end', host=host, root_count=1)]


class CoverageRegressionTests(unittest.TestCase):
    def build_fixture(self, *streams) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inventories = []
            for index, events in enumerate(streams):
                path = root / f'inventory-{index}.jsonl.gz'
                with gzip.open(path, 'wt', encoding='utf-8') as stream:
                    for event in events:
                        stream.write(json.dumps(event) + '\n')
                inventories.append(path)
            return project.build_project(inventories, root / 'data', root / 'public',
                                         '2001-04-01T00:00:00Z')

    def assert_gap(self, result):
        self.assertEqual(result['inventory']['hosts'][0]['status'], 'indexed_with_gaps')
        self.assertTrue(result['inventory']['hosts'][0]['errors'])
        self.assertEqual(result['metrics']['index_status'], 'metadata_with_gaps')
        inventory_work = next(w for w in result['work_items'] if w['id'] == 'inventory')
        self.assertEqual(inventory_work['status'], 'blocked')

    def test_declared_roots_must_exactly_match_starts_ends_and_file_roots(self):
        cases = {}
        events = inventory_events()
        events[0]['roots'] = ['/a', '/b']
        events[-1]['root_count'] = 2
        cases['declared_b_never_started'] = events
        events = inventory_events()
        events[3].update(root='/b', files=0)
        cases['equal_start_end_counts_but_different_roots'] = events
        events = inventory_events()
        del events[0]['roots']
        cases['unknown_declared_roots'] = events
        events = inventory_events()
        events[0]['roots'] = []
        cases['empty_declared_roots_with_observed_a'] = events
        events = inventory_events()
        row = copy.deepcopy(events[2])
        row.update(root='/b', path='/b/enwiki-20200101-pages-meta-history.xml.7z', inode=2)
        events.insert(3, row)
        cases['candidate_on_uninspected_root_is_preserved'] = events
        for name, events in cases.items():
            with self.subTest(case=name):
                result = self.build_fixture(events)
                self.assertEqual(result['inventory']['file_count'],
                                 sum(e['type'] == 'file' for e in events))
                self.assert_gap(result)

    def test_error_truncation_and_host_root_count_evidence_remain_gaps(self):
        cases = {}
        events = inventory_events()
        events[-1]['root_count'] = 2
        cases['host_root_count_mismatch'] = events
        events = inventory_events()
        del events[-1]['root_count']
        cases['host_root_count_unknown'] = events
        events = inventory_events()
        events[3]['errors'] = 1
        cases['root_reported_errors'] = events
        events = inventory_events()
        events[3]['truncated'] = True
        cases['root_reported_truncation'] = events
        events = inventory_events()
        events.insert(3, dict(type='error', host='fixture-host', root='/a',
                              operation='scandir', error='PermissionError'))
        cases['persisted_error_event'] = events
        events = inventory_events()
        events[3]['status'] = 'complete_with_errors'
        cases['incomplete_root_status'] = events
        for name, events in cases.items():
            with self.subTest(case=name):
                result = self.build_fixture(events)
                self.assertEqual(result['inventory']['file_count'], 1)
                self.assert_gap(result)

    def test_root_file_count_mismatch_is_still_rejected(self):
        events = inventory_events()
        events[3]['files'] = 2
        with self.assertRaisesRegex(ValueError, 'root count audit failed'):
            self.build_fixture(events)

    def test_duplicate_host_runs_and_protocol_records_are_rejected(self):
        second = inventory_events()
        second[0]['roots'] = ['/b']
        for event in second:
            if 'root' in event:
                event['root'] = '/b'
            if 'path' in event:
                event['path'] = event['path'].replace('/a/', '/b/')
        cases = {'same_host_in_two_inputs': (inventory_events(), second),
                 'same_host_two_concatenated_runs': (inventory_events() + second,)}
        for index, name in ((0, 'discovery'), (1, 'root_start'),
                            (3, 'root_end'), (4, 'host_end')):
            events = inventory_events()
            events.insert(index, copy.deepcopy(events[index]))
            cases['duplicate_' + name] = (events,)
        events = inventory_events()
        events.insert(2, copy.deepcopy(events[2]))
        events[4]['files'] = 2
        cases['duplicate_file_path'] = (events,)
        for name, streams in cases.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, 'duplicate inventory'):
                    self.build_fixture(*streams)

    def test_distinct_host_inventories_remain_supported(self):
        second = inventory_events()
        for event in second:
            event['host'] = 'fixture-host-two'
        result = self.build_fixture(inventory_events(), second)
        self.assertEqual(result['inventory']['file_count'], 2)
        self.assertEqual(len(result['inventory']['hosts']), 2)
        self.assertTrue(all(h['status'] == 'metadata_indexed'
                            for h in result['inventory']['hosts']))

    def test_exact_declared_coverage_is_metadata_indexed(self):
        result = self.build_fixture(inventory_events())
        self.assertEqual(result['inventory']['hosts'][0]['status'], 'metadata_indexed')
        self.assertEqual(result['metrics']['index_status'], 'metadata_only')


if __name__ == '__main__':
    unittest.main()
