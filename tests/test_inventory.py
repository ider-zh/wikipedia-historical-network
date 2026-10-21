import importlib.util
import pathlib
import unittest

MODULE = pathlib.Path(__file__).parents[1] / 'tools' / 'inventory.py'

class InventoryTests(unittest.TestCase):
    def load(self):
        self.assertTrue(MODULE.exists(), 'inventory implementation is missing')
        spec = importlib.util.spec_from_file_location('inventory', MODULE)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_classify_preserves_inferred_wiki_date_table_and_partial(self):
        inv = self.load()
        row = inv.classify('/data/wikipedia/enwiki/20220201/enwiki-20220201-categorylinks.sql.gz.part')
        self.assertEqual(row['inferred_wikis'], ['enwiki'])
        self.assertEqual(row['inferred_dates'], ['20220201'])
        self.assertEqual(row['tables'], ['categorylinks'])
        self.assertEqual(row['representation'], 'sql')
        self.assertTrue(row['truncated'])
        self.assertFalse(row['source_eligible_candidate'])

    def test_archive_context_is_opaque_and_nonwiki_is_rejected(self):
        inv = self.load()
        self.assertTrue(hasattr(inv, 'candidate'), 'candidate selection missing')
        self.assertTrue(inv.candidate('/mnt/archive/wikipedia_histry_20210501/database_backup.tar.gz'))
        row = inv.classify('/mnt/archive/wikipedia_histry_20210501/database_backup.tar.gz')
        self.assertEqual(row['representation'], 'opaque_archive')
        self.assertFalse(row['source_eligible_candidate'])
        self.assertFalse(inv.candidate('/mnt/photos/holiday.jpg'))
        self.assertTrue(inv.candidate('/mnt/backup/categorylinks.sql.gz'))
        self.assertEqual(inv.classify('/mnt/zhwiki/zhwiki-20180101-pages-meta-history.xml.7z')['representation'], 'xml_history')
        self.assertEqual(inv.classify('/mnt/frwiki/frwiki-20200101-page.sql.gz')['inferred_wikis'], ['frwiki'])

    def test_walk_reports_files_checksums_alias_and_exclusions_without_following(self):
        inv = self.load()
        self.assertTrue(hasattr(inv, 'walk_root'), 'bounded walk missing')
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            wiki = root / 'wikipedia_history_20220201'
            wiki.mkdir()
            payload = wiki / 'enwiki-20220201-pages-meta-history.xml.bz2'
            payload.write_bytes(b'not decompressed')
            (wiki / 'sha1sums.txt').write_text('manifest exists, not verified')
            (root / 'alias').symlink_to(wiki, target_is_directory=True)
            (root / 'node_modules').mkdir()
            (root / 'node_modules' / 'enwiki.sql').write_text('excluded')
            nested = root / 'nested_mount'
            nested.mkdir()
            (nested / 'zhwiki.sql').write_text('boundary')
            events = list(inv.walk_root(str(root), boundaries=[str(nested)]))
            files = [e for e in events if e['type'] == 'file']
            self.assertEqual(len(files), 2)
            row = next(e for e in files if e['path'] == str(payload))
            self.assertEqual(row['size_bytes'], len(b'not decompressed'))
            self.assertFalse(row['checksums']['computed'])
            self.assertEqual(row['checksums']['neighbor_manifests'], [str(wiki / 'sha1sums.txt')])
            self.assertTrue(any(e['type'] == 'alias' for e in events))
            self.assertTrue(any(e.get('reason') == 'mount_boundary' for e in events))
            self.assertTrue(any(e.get('reason') == 'excluded_name' for e in events))
            self.assertEqual(events[-1]['type'], 'root_end')
            self.assertEqual(events[-1]['files'], 2)
            self.assertEqual(events[-1]['status'], 'complete')

    def test_plan_mounts_uses_nested_boundaries_and_excludes_engine_binds(self):
        inv = self.load()
        self.assertTrue(hasattr(inv, 'plan_roots'), 'mount-derived root planning missing')
        mounts = {'filesystems': [{'target': '/', 'fstype': 'ext4', 'source': '/dev/a', 'children': [
            {'target': '/mnt/data', 'fstype': 'xfs', 'source': '/dev/b'},
            {'target': '/mnt/data/bind', 'fstype': 'xfs', 'source': '/dev/b[/sub]'},
            {'target': '/home/ider/.hermes/cache/scratch/disk', 'fstype': 'fuseblk', 'source': '/dev/c'},
            {'target': '/var/lib/docker/volumes/db', 'fstype': 'xfs', 'source': '/dev/b[/engine]'},
            {'target': '/tmp/snap.rootfs_abc', 'fstype': 'ext4', 'source': '/dev/a[/tmp]'},
        ]}]}
        plan = inv.plan_roots(mounts)
        self.assertIn('/mnt/data', plan['roots'])
        self.assertIn('/mnt/data/bind', plan['roots'])
        self.assertIn('/mnt/data/bind', plan['boundaries'])
        self.assertIn('/home/ider/.hermes/cache/scratch/disk', plan['roots'])
        self.assertNotIn('/var/lib/docker/volumes/db', plan['roots'])
        self.assertNotIn('/tmp/snap.rootfs_abc', plan['roots'])
        self.assertNotIn('/', plan['roots'])
        self.assertIn('/home/ider', plan['roots'])

    def test_cli_emits_host_protocol_and_budget_errors(self):
        inv = self.load()
        self.assertTrue(hasattr(inv, 'main'), 'CLI protocol missing')
        import tempfile
        import subprocess
        import json
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for i in range(5):
                (root / ('enwiki-%d.sql' % i)).write_text('not read')
            proc = subprocess.run([sys.executable, str(MODULE), '--root', tmp, '--max-entries', '2'], capture_output=True, text=True, check=True)
            events = [json.loads(line) for line in proc.stdout.splitlines()]
            self.assertEqual(events[0]['type'], 'discovery')
            self.assertEqual(events[-1]['type'], 'host_end')
            end = next(e for e in events if e['type'] == 'root_end')
            self.assertEqual(end['status'], 'truncated')
            self.assertTrue(any(e['type'] == 'error' for e in events))
            self.assertTrue(all(e['schema_version'] == 1 and e['host'] for e in events))
            self.assertLessEqual(end['entries'], 2)

    def test_coordinator_persists_compressed_records_and_audited_counts(self):
        import importlib.util
        import tempfile
        import gzip
        import json
        runner = MODULE.with_name('inventory_run.py')
        self.assertTrue(runner.exists(), 'streaming coordinator missing')
        spec = importlib.util.spec_from_file_location('inventory_run', runner)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            src = base / 'source'
            src.mkdir()
            (src / 'zhwiki-20200101-categorylinks.sql.gz').write_bytes(b'opaque')
            output = base / 'out'
            result = module.collect('local', output, MODULE, roots=[str(src)])
            self.assertEqual(result['returncode'], 0)
            audit = module.audit(output)
            self.assertTrue(audit['coverage_audited'])
            self.assertEqual(audit['candidate_files'], 1)
            self.assertEqual(audit['by_wiki'], {'zhwiki': 1})
            with gzip.open(output / 'files.jsonl.gz', 'rt') as f:
                rows = [json.loads(line) for line in f]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['path'], str(src / 'zhwiki-20200101-categorylinks.sql.gz'))
            coverage = json.loads((output / 'root-coverage.json').read_text())
            self.assertEqual(coverage[0]['persisted_files'], coverage[0]['reported_files'])
            self.assertTrue((output / 'stderr.log').exists())
            self.assertEqual(json.loads((output / 'errors.json').read_text()), [])

    def test_sql_in_opaque_container_is_not_claimed_source_eligible(self):
        inv = self.load()
        row = inv.classify('/mnt/wiki/enwiki-20100101.sql.tar.gz')
        self.assertEqual(row['representation'], 'opaque_archive')
        self.assertFalse(row['source_eligible_candidate'])
        self.assertFalse(inv.classify('/mnt/wiki/enwiki.sql.7z')['source_eligible_candidate'])
        self.assertTrue(inv.classify('/mnt/wiki/enwiki-20220101-categorylinks.sql.gz')['source_eligible_candidate'])

    def test_wiki_inference_ignores_tool_prefixes_but_finds_language_codes(self):
        inv = self.load()
        self.assertEqual(inv.classify('/mnt/study/tjref_type_enwiki/part.gz')['inferred_wikis'], ['enwiki'])
        self.assertEqual(inv.classify('/data/extract_zhwiki/page.sql')['inferred_wikis'], ['zhwiki'])
        self.assertEqual(inv.classify('/data/zh_min_nanwiki/zh_min_nanwiki-20200101-page.sql.gz')['inferred_wikis'], ['zh_min_nanwiki'])
        self.assertEqual(inv.classify('/home/code/colleague-wiki/tool.py')['inferred_wikis'], [])

    def test_engine_directory_variants_are_explicit_exclusions_not_archive_files(self):
        inv = self.load()
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for name in ('mongo29001', 'mysql_file', 'elastic-data', 'es-openalex-data', 'docker', 'postgres_data'):
                directory = root / name
                directory.mkdir()
                (directory / 'enwiki.sql').write_text('engine fixture')
            (root / 'wikipedia_mysql_backup.tar.gz').write_bytes(b'archive fixture')
            events = list(inv.walk_root(str(root)))
            self.assertEqual(sum(e['type'] == 'file' for e in events), 1)
            self.assertEqual(sum(e.get('reason') == 'engine_directory' for e in events), 6)
            self.assertEqual(events[-1]['status'], 'complete')

    def test_collector_preserves_exact_scanner_and_fingerprint(self):
        import tempfile
        import importlib.util
        import hashlib
        runner = MODULE.with_name('inventory_run.py')
        spec = importlib.util.spec_from_file_location('inventory_run', runner)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            src = base / 'source'
            src.mkdir()
            output = base / 'out'
            execution = module.collect('local', output, MODULE, roots=[str(src)])
            self.assertIn('scanner_sha256', execution)
            self.assertEqual(execution['scanner_sha256'], hashlib.sha256(MODULE.read_bytes()).hexdigest())
            self.assertEqual((output / 'scanner.py').read_bytes(), MODULE.read_bytes())

    def test_history_requires_filename_evidence_and_rejects_stubs_indexes(self):
        inv = self.load()
        self.assertEqual(inv.classify('/data/wikipedia_history_2004/enwiki-pages-articles.xml.bz2')['representation'], 'xml')
        stub = inv.classify('/data/enwiki/enwiki-20070101-stub-meta-history.xml.gz')
        self.assertEqual(stub['representation'], 'xml_stub')
        self.assertFalse(stub['source_eligible_candidate'])
        index = inv.classify('/data/enwiki/enwiki-20220101-pages-meta-history-index.txt.bz2')
        self.assertEqual(index['representation'], 'xml_index')
        self.assertFalse(index['source_eligible_candidate'])
        history = inv.classify('/data/enwiki/2004/enwiki-history.xml.gz')
        self.assertEqual(history['representation'], 'xml_history')
        self.assertEqual(history['inferred_dates'], [])
        self.assertEqual(history['inferred_years'], ['2004'])

    def test_candidate_uses_sql_history_and_literal_misspelling_parent_context(self):
        inv = self.load()
        self.assertTrue(inv.candidate('/mnt/archive/SQL/2004.tar.7z'))
        self.assertTrue(inv.candidate('/mnt/archive/history/2007.tar.gz'))
        self.assertTrue(inv.candidate('/mnt/archive/wikipedia_histry_20210501/part-00001.7z'))
        self.assertTrue(inv.candidate('/mnt/photos/2004.tar.7z'))
        self.assertTrue(inv.candidate('/mnt/backup/data2015.zip'))
        self.assertEqual(inv.classify('/mnt/backup/data2015.zip')['candidate_evidence'], 'unscoped_archive_filename_only')

    def test_mydumper_dot_tables_and_schema_only_files_are_distinguished(self):
        inv = self.load()
        data = inv.classify('/mnt/mysql_dump/enwiki20040930/enwiki20040930.categorylinks.00000.sql.xz')
        self.assertEqual(data['tables'], ['categorylinks'])
        self.assertEqual(data['representation'], 'sql')
        schema = inv.classify('/mnt/mysql_dump/enwiki20010331/enwiki20010331.categorylinks-schema.sql.xz')
        self.assertEqual(schema['tables'], ['categorylinks'])
        self.assertEqual(schema['representation'], 'sql_schema')
        self.assertFalse(schema['source_eligible_candidate'])
        dat = inv.classify('/mnt/mysql_dump/zhwiki20160305/zhwiki20160305.page.00000.dat.xz')
        self.assertEqual(dat['tables'], ['page'])
        self.assertEqual(dat['representation'], 'tabular_dat')
        self.assertFalse(dat['source_eligible_candidate'])

    def test_page_props_does_not_falsely_prove_page_table_availability(self):
        inv = self.load()
        self.assertEqual(inv.classify('/data/enwiki/enwiki-20200101-page_props.sql.gz')['tables'], ['page_props'])
        self.assertEqual(inv.classify('/data/wiki/categorylinks_2020-01-31.txt.gz')['tables'], ['categorylinks'])

    def test_noncanonical_xml_flow_download_parts_and_fixtures_are_not_sources(self):
        inv = self.load()
        blocked = [
            '/data/zhwiki/zhwiki-20170501-flowhistory.xml.bz2',
            '/data/zhwiki/zhwiki-20170501-pages-meta-history1.xml.bz2.filepart',
            '/data/wiki/ref_enwiki-20220201-pages-meta-history1.xml-p1p42.7z.txt.gz',
            '/home/code/wikipedia-dump-parser/testdata/enwiki-20241101-pages-meta-history1.xml-p1p42.bz2',
            '/data/enwiki/tjref_enwiki-20220201-pages-meta-history1.xml-p1p42.7z',
        ]
        for path in blocked:
            with self.subTest(path=path):
                self.assertFalse(inv.classify(path)['source_eligible_candidate'])
        self.assertTrue(inv.classify('/data/enwiki/enwiki-20220201-pages-meta-history1.xml-p1p42.7z')['source_eligible_candidate'])
        self.assertTrue(inv.classify(blocked[1])['truncated'])

    def test_refiner_creates_immutable_corrected_view_without_rescanning_sources(self):
        import tempfile
        import gzip
        import json
        import importlib.util
        import sys
        refiner_path = MODULE.with_name('inventory_refine.py')
        self.assertTrue(refiner_path.exists(), 'immutable metadata refiner missing')
        sys.path.insert(0, str(MODULE.parent))
        spec = importlib.util.spec_from_file_location('inventory_refine', refiner_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            source = base / 'observed'
            source.mkdir()
            rows = [
                dict(type='discovery', host='observed-host', roots=['/private/source']),
                dict(type='root_start', host='observed-host', root='/private/source'),
                dict(type='file', host='observed-host', root='/private/source', path='/private/source/enwiki-20200101-pages-meta-history.xml.bz2.filepart', size_bytes=5, source_eligible_candidate=True),
                dict(type='root_end', host='observed-host', root='/private/source', files=1, status='complete'),
                dict(type='host_end', host='observed-host'),
            ]
            with gzip.open(source / 'inventory.jsonl.gz', 'wt') as stream:
                stream.write(''.join(json.dumps(row)+'\n' for row in rows))
            (source / 'execution.json').write_text(json.dumps({'returncode': 0}))
            before = (source / 'inventory.jsonl.gz').read_bytes()
            output = base / 'refined'
            result = module.refine(source, output)
            self.assertTrue(result['coverage_audited'])
            self.assertEqual(result['candidate_files'], 1)
            self.assertEqual(result['host'], 'observed-host')
            self.assertEqual(result['source_eligible_candidates'], 0)
            self.assertEqual((source / 'inventory.jsonl.gz').read_bytes(), before)
            provenance = json.loads((output / 'classification.json').read_text())
            self.assertEqual(provenance['source_inventory'], str(source / 'inventory.jsonl.gz'))
            self.assertTrue(provenance['classifier_sha256'])

    def test_page_range_ids_are_not_misinterpreted_as_snapshot_dates(self):
        inv = self.load()
        row = inv.classify('/data/wikipedia_histry_20210501/enwiki-20210501-pages-meta-history16.xml-p19323808p19400931.7z')
        self.assertEqual(row['inferred_dates'], ['20210501'])
        self.assertTrue(row['source_eligible_candidate'])

if __name__ == '__main__':
    unittest.main()
