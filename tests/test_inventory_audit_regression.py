"""Synthetic persisted-stream regressions; never read real inventory sources."""
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


class InventoryAuditRegressionTests(unittest.TestCase):
    def test_coverage_requires_exact_declared_started_ended_file_roots(self):
        spec = importlib.util.spec_from_file_location(
            'inventory_run', Path(__file__).parents[1] / 'tools' / 'inventory_run.py')
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        def event(kind, **fields):
            return dict(type=kind, host='synthetic-host', **fields)

        def file(root):
            return event('file', root=root, path=root + '/synthetic.sql',
                         size_bytes=1, source_eligible_candidate=False,
                         inferred_wikis=[], inferred_dates=[],
                         representation='sql', tables=[])

        cases = [
            ('undeclared_file_root', ['/a'], ['/a'], ['/a'], ['/a', '/b'], False),
            ('undeclared_complete_root', ['/a'], ['/a', '/b'], ['/a', '/b'], ['/a', '/b'], False),
            ('missing_start', ['/a'], [], ['/a'], ['/a'], False),
            ('missing_end', ['/a'], ['/a'], [], ['/a'], False),
            ('declared_unvisited_root', ['/a', '/b'], ['/a'], ['/a'], ['/a'], False),
            ('undeclared_empty_root', ['/a'], ['/a', '/b'], ['/a', '/b'], ['/a'], False),
            ('valid', ['/a', '/b'], ['/a', '/b'], ['/a', '/b'], ['/a'], True),
        ]
        for name, declared, started, ended, file_roots, valid in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp)
                rows = [event('discovery', roots=declared)]
                rows += [event('root_start', root=root) for root in started]
                rows += [file(root) for root in file_roots]
                rows += [event('root_end', root=root, files=file_roots.count(root),
                               status='complete') for root in ended]
                rows += [event('host_end')]
                with gzip.open(output / 'inventory.jsonl.gz', 'wt') as stream:
                    stream.writelines(json.dumps(row) + '\n' for row in rows)
                (output / 'execution.json').write_text(json.dumps({'returncode': 0}))

                summary = module.audit(output)
                coverage = json.loads((output / 'root-coverage.json').read_text())
                self.assertEqual(summary['candidate_files'], len(file_roots))
                self.assertEqual({row['root'] for row in coverage},
                                 set(declared) | set(started) | set(ended) | set(file_roots))
                self.assertEqual(sum(row['persisted_files'] for row in coverage),
                                 summary['candidate_files'])
                self.assertEqual(summary['coverage_audited'], valid)
                self.assertEqual(summary['scoped_walk_complete_without_errors'], valid)
