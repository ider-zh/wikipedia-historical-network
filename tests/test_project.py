import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('project',Path(__file__).resolve().parents[1]/'whn'/'project.py')
assert spec is not None and spec.loader is not None and spec.origin is not None
project=importlib.util.module_from_spec(spec)
if Path(spec.origin).exists():spec.loader.exec_module(project)

class ProjectTests(unittest.TestCase):
    def test_real_manifest_pipeline_roundtrip_and_idempotent_versions(self):
        self.assertTrue(hasattr(project,'build_project'),'inventory-to-plan CLI missing')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);inventory=root/'inventory.jsonl.gz';data=root/'ssd';public=root/'dashboard'
            row=dict(type='file',host='192.168.1.999-private',root='/private/data',path='/private/data/enwiki-20200101-pages-meta-history.xml.7z',size_bytes=123,mtime_ns=1,device=1,inode=1,inferred_wikis=['enwiki'],inferred_dates=['20200101'],representation='xml_history',tables=[],source_eligible_candidate=True,truncated=False,checksums=dict(computed=False))
            events=[dict(type='discovery',host=row['host']),dict(type='root_start',host=row['host'],root=row['root']),row,dict(type='root_end',host=row['host'],root=row['root'],files=1,status='complete',errors=0,truncated=False),dict(type='host_end',host=row['host'])]
            with gzip.open(inventory,'wt') as f:
                for event in events:f.write(json.dumps(event)+'\n')
            result=project.build_project([inventory],data,public,'2001-10-01T00:00:00Z')
            self.assertEqual(len(result['plans']),6)
            self.assertEqual(result['inventory']['file_count'],1)
            self.assertEqual(result['inventory']['source_set_count'],1)
            text=(public/'project.json').read_text()
            self.assertNotIn('/private/data',text)
            self.assertNotIn('192.168.1.999',text)
            self.assertEqual(result,project.build_project([inventory],data,public,'2001-10-01T00:00:00Z'))
            import pyarrow.parquet as pq
            self.assertEqual(pq.read_table(data/'catalog/files.parquet').num_rows,1)
            self.assertTrue((data/'catalog/source-sets.parquet').is_file(),'source-set Parquet missing')
            self.assertEqual(pq.read_table(data/'catalog/source-sets.parquet').num_rows,1)
            self.assertEqual(pq.read_table(data/'plans/latest.parquet').num_rows,6)
            versions=list((data/'plans/versions').glob('*/*.json'))
            self.assertEqual(len(versions),6)
            import csv
            with (public/'quarterly-plan.csv').open(encoding='utf-8-sig',newline='') as f:
                exported=list(csv.DictReader(f))
            self.assertEqual(len(exported),6)
            self.assertEqual(exported[0]['xml_source_date'],'2020-01-01')
            self.assertEqual(exported[-1]['xml_source_id'],'')
            self.assertNotIn('/private', (public/'quarterly-plan.csv').read_text())

if __name__=='__main__':unittest.main()
