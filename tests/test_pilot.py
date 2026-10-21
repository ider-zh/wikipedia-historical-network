import importlib.util
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('pilot',Path(__file__).resolve().parents[1]/'whn'/'pilot.py')
assert spec and spec.loader and spec.origin
pilot=importlib.util.module_from_spec(spec)
if Path(spec.origin).exists():spec.loader.exec_module(pilot)

class PilotTests(unittest.TestCase):
    def test_graph_identity_resolution_and_category_union(self):
        self.assertTrue(hasattr(pilot,'assemble_graph'),'pilot graph assembler missing')
        records=[dict(page_id=1,ns=0,title='甲',revision_id=11,timestamp='2025-09-01T00:00:00Z',text_state='present',links=[dict(target='乙'),dict(target='未收录')],categories=['共享','甲类'],redirect_target=None,parse_status='ok'),dict(page_id=2,ns=0,title='乙',revision_id=12,timestamp='2025-09-02T00:00:00Z',text_state='present',links=[],categories=[],redirect_target='甲',parse_status='ok'),dict(page_id=3,ns=14,title='Category:甲类',revision_id=13,timestamp='2025-09-02T00:00:00Z',text_state='present',links=[],categories=['共享'],redirect_target=None,parse_status='ok')]
        result=pilot.assemble_graph(records,[dict(source_page_id=1,category_title='共享'),dict(source_page_id=1,category_title='SQL类')])
        self.assertEqual(result['page_links'][0],dict(source_id=1,target_id_list=[2]))
        self.assertEqual(result['counts']['unresolved_page_links'],1)
        masks=result['category_union'][0]['source_mask_list']
        self.assertEqual(sorted(masks),[1,2,3])
        self.assertEqual(len(result['category_graph']),1)
        self.assertEqual(result['redirects'][0]['target_id'],1)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'graph'
            written=pilot.write_graph(out,result)
            self.assertTrue(all(p.exists() for p in written))
            import pyarrow.parquet as pq
            self.assertNotIn('text',pq.read_table(out/'pages.parquet').column_names)

    def test_rejects_hidden_fabricated_edges_and_duplicate_identity(self):
        row=dict(page_id=1,ns=0,title='甲',revision_id=11,timestamp='2025-09-01T00:00:00Z',text_state='hidden',links=[dict(target='乙')],categories=[],redirect_target=None,parse_status='unavailable')
        with self.assertRaisesRegex(ValueError,'unavailable'):pilot.assemble_graph([row])
        row.update(text_state='present',parse_status='ok',links=[])
        with self.assertRaisesRegex(ValueError,'duplicate'):pilot.assemble_graph([row,row])
        row['text']='privacy-canary'
        with self.assertRaisesRegex(ValueError,'private'):pilot.assemble_graph([row])

    def test_sql_generator_provenance_and_category_cycle_diagnostics(self):
        records=[dict(page_id=1,ns=14,title='Category:甲',revision_id=1,timestamp='2025-09-01T00:00:00Z',text_state='present',links=[],categories=['乙'],redirect_target=None,parse_status='ok'),dict(page_id=2,ns=14,title='Category:乙',revision_id=2,timestamp='2025-09-01T00:00:00Z',text_state='present',links=[],categories=['甲'],redirect_target=None,parse_status='ok')]
        observations=(dict(source_page_id=1,category_title=x) for x in ['乙','SQL'])
        graph=pilot.assemble_graph(records,observations)
        self.assertEqual(graph['counts']['sql_category_edges'],2)
        self.assertEqual(graph['counts']['category_cycle_detected'],True)
        self.assertEqual(graph['counts']['category_union_edges'],3)

    def test_namespace_resolution_for_aliases_redirects_and_unresolved(self):
        def row(pid,ns,title,links=(),redirect=None):
            return dict(page_id=pid,ns=ns,title=title,revision_id=pid,timestamp='2025-09-01T00:00:00Z',text_state='present',links=list(links),categories=[],redirect_target=redirect,parse_status='ok')
        rows=[row(1,0,'甲',[dict(target='category:Physics'),dict(target='Outside',namespace=14)],'分類:Physics'),row(2,14,'Category:Physics')]
        result=pilot.assemble_graph(rows)
        self.assertEqual(result['page_links'][0]['target_id_list'],[2])
        self.assertEqual(result['redirects'][0]['target_id'],2)
        self.assertEqual(result['unresolved'][0]['target_namespace'],14)

    def test_graph_writer_never_adds_files_to_existing_generation(self):
        row=dict(page_id=1,ns=0,title='甲',revision_id=1,timestamp='2025-09-01T00:00:00Z',text_state='present',links=[],categories=[],redirect_target=None,parse_status='ok')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'graph';out.mkdir();(out/'pages.parquet').write_bytes(b'old-generation')
            with self.assertRaises(FileExistsError):pilot.write_graph(out,pilot.assemble_graph([row]))
            self.assertEqual({p.name for p in out.iterdir()},{'pages.parquet'})
            self.assertEqual((out/'pages.parquet').read_bytes(),b'old-generation')

if __name__=='__main__':unittest.main()
