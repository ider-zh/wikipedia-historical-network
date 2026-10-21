import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zlib
spec=importlib.util.spec_from_file_location('pipeline',Path(__file__).resolve().parents[1]/'whn'/'pilot_pipeline.py')
assert spec and spec.loader and spec.origin
pipeline=importlib.util.module_from_spec(spec)
if Path(spec.origin).exists():spec.loader.exec_module(pipeline)

class PipelineTests(unittest.TestCase):
    def test_pipeline_crc_byte_count_and_no_persisted_wikitext(self):
        self.assertTrue(hasattr(pipeline,'execute_pipeline'),'verified pipe executor missing')
        data=b'<mediawiki>PRIVATE_BODY_CANARY</mediawiki>'
        record=dict(page_id=1,ns=0,title='Title',revision_id=1,timestamp='2025-09-01T00:00:00Z',text_state='present',links=[],categories=[],redirect_target=None,parse_status='ok')
        decoder=[sys.executable,'-c','import sys;sys.stdout.buffer.write('+repr(data)+')']
        selector=[sys.executable,'-c','import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())']
        graph=[sys.executable,'-c','import sys;sys.stdin.buffer.read();print('+repr(json.dumps(record))+')']
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'run'
            records,proof=pipeline.execute_pipeline(decoder,selector,graph,out,len(data),'%08X'%zlib.crc32(data))
            self.assertEqual(records,[record]);self.assertTrue(proof['complete_archive_decoded'])
            for path in out.iterdir():self.assertNotIn(b'PRIVATE_BODY_CANARY',path.read_bytes())
            with self.assertRaisesRegex(ValueError,'CRC'):
                pipeline.execute_pipeline(decoder,selector,graph,Path(tmp)/'bad',len(data),'00000000')
            self.assertFalse((Path(tmp)/'bad/pipeline-verification.json').exists())

    def test_failed_stage_or_private_graph_output_never_commits(self):
        data=b'x'
        decoder=[sys.executable,'-c','print("x",end="")']
        selector=[sys.executable,'-c','import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())']
        graph=[sys.executable,'-c','import sys;sys.stdin.buffer.read();print(\'{"text":"PRIVATE_BODY_CANARY"}\')']
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'private'
            with self.assertRaisesRegex(ValueError,'private'):
                pipeline.execute_pipeline(decoder,selector,graph,out,1,'%08X'%zlib.crc32(data),deadline_seconds=5)
            self.assertFalse((out/'pipeline-verification.json').exists())
            self.assertFalse((out/'graph-records.jsonl').exists())
            for path in out.iterdir():self.assertNotIn(b'PRIVATE_BODY_CANARY',path.read_bytes())
            fail=[sys.executable,'-c','import sys;sys.stdin.buffer.read();sys.exit(3)']
            with self.assertRaisesRegex(RuntimeError,'exits'):
                pipeline.execute_pipeline(decoder,selector,fail,Path(tmp)/'fail',1,'%08X'%zlib.crc32(data),deadline_seconds=5)

    def test_nested_private_fields_are_rejected_before_any_record_write(self):
        row=dict(page_id=1,ns=0,title='Title',revision_id=1,timestamp='2025-09-01T00:00:00Z',text_state='present',links=[dict(target='Public',text='NESTED_PRIVATE_CANARY')],categories=[],redirect_target=None,parse_status='ok')
        decoder=[sys.executable,'-c','print("x",end="")']
        selector=[sys.executable,'-c','import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())']
        graph=[sys.executable,'-c','import sys;sys.stdin.buffer.read();print('+repr(json.dumps(row))+')']
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'nested'
            with self.assertRaisesRegex(ValueError,'private|invalid'):
                pipeline.execute_pipeline(decoder,selector,graph,out,1,'%08X'%zlib.crc32(b'x'),deadline_seconds=5)
            for path in out.iterdir():self.assertNotIn(b'NESTED_PRIVATE_CANARY',path.read_bytes())
            self.assertFalse((out/'pipeline-verification.json').exists())

    def test_decimal_ids_are_losslessly_decoded_after_validation(self):
        row=dict(page_id='9007199254740993',ns=0,title='Title',revision_id='9007199254740995',timestamp='2025-09-01T00:00:00Z',text_state='present',links=[],categories=[],redirect_target=None,parse_status='ok')
        decoder=[sys.executable,'-c','print("x",end="")']
        selector=[sys.executable,'-c','import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())']
        graph=[sys.executable,'-c','import sys;sys.stdin.buffer.read();print('+repr(json.dumps(row))+')']
        with tempfile.TemporaryDirectory() as tmp:
            records,proof=pipeline.execute_pipeline(decoder,selector,graph,Path(tmp)/'ids',1,'%08X'%zlib.crc32(b'x'),deadline_seconds=5)
            self.assertEqual(records[0]['page_id'],9007199254740993)
            self.assertEqual(records[0]['revision_id'],9007199254740995)
            with self.assertRaisesRegex(ValueError,'budget'):
                pipeline.execute_pipeline(decoder,selector,graph,Path(tmp)/'budget',1,'%08X'%zlib.crc32(b'x'),deadline_seconds=5,max_graph_bytes=10)

if __name__=='__main__':unittest.main()
