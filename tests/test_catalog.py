import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('catalog',Path(__file__).resolve().parents[1]/'whn'/'catalog.py')
assert spec is not None and spec.loader is not None and spec.origin is not None
catalog=importlib.util.module_from_spec(spec)
if Path(spec.origin).exists():spec.loader.exec_module(catalog)

class CatalogTests(unittest.TestCase):
    def row(self,path,rep,tables=()):
        return dict(type='file',host='host',path=path,root='/data',size_bytes=42,mtime_ns=1,device=1,inode=2,
            inferred_wikis=['enwiki'],inferred_dates=['20200101'],representation=rep,tables=list(tables),
            source_eligible_candidate=True,truncated=False,checksums=dict(computed=False))
    def test_group_history_and_sql_with_local_identity_mapping(self):
        self.assertTrue(hasattr(catalog,'source_sets'),'source-set grouping missing')
        rows=[self.row('/data/h/enwiki-20200101-pages-meta-history1.xml.7z','xml_history'),
              self.row('/data/h/enwiki-20200101-pages-meta-history2.xml.7z','xml_history'),
              self.row('/data/s/enwiki-20200101-page.sql.gz','sql',['page']),
              self.row('/data/s/enwiki-20200101-categorylinks.sql.gz','sql',['categorylinks'])]
        sets=catalog.source_sets(rows)
        self.assertEqual(len(sets),2)
        h=next(s for s in sets if s['kind']=='history_xml')
        q=next(s for s in sets if s['kind']=='category_sql')
        self.assertEqual(h['file_count'],2)
        self.assertTrue(q['eligible'])
        self.assertFalse(h['payload_verified'])
        self.assertNotIn('path',h)
        self.assertEqual(q['tables'],['categorylinks','page'])

    def test_ambiguous_dates_partial_stub_and_missing_sql_mapping_block(self):
        partial=self.row('/data/h/enwiki-20200101-pages-meta-history.xml.7z.part','xml_history');partial['truncated']=True
        ambiguous=self.row('/data/h/enwiki-20200101-pages-meta-history.xml.7z','xml_history');ambiguous['inferred_dates']=['20190101','20200101']
        stub=self.row('/data/h/enwiki-20200101-stub-meta-history.xml.gz','xml_history')
        onlysql=self.row('/data/s/enwiki-20200101-categorylinks.sql.gz','sql',['categorylinks'])
        sets=catalog.source_sets([partial,ambiguous,stub,onlysql])
        self.assertEqual(len(sets),1)
        self.assertFalse(sets[0]['eligible'])
        self.assertEqual(sets[0]['missing_requirements'],['same_source_page_and_categorylinks_sql'])

    def test_files_with_same_date_but_different_xml_representations_not_mixed(self):
        seven=self.row('/data/h/enwiki-20200101-pages-meta-history.xml.7z','xml_history')
        bz=self.row('/data/h/enwiki-20200101-pages-meta-history.xml.bz2','xml_history')
        sets=catalog.source_sets([seven,bz])
        self.assertEqual(len(sets),2,'compressed representations must not become duplicate XML input shards')

    def test_private_member_bindings_exist_without_public_path_leak(self):
        row=self.row('/data/h/enwiki-20200101-pages-meta-history.xml.7z','xml_history')
        self.assertTrue(hasattr(catalog,'private_bindings'),'build source membership missing')
        source=catalog.source_sets([row])[0]
        bindings=catalog.private_bindings([row])
        self.assertEqual(bindings[source['id']][0]['paths'],[row['path']])
        self.assertNotIn('/data',str(source))

    def test_derived_text_flow_and_fixture_xml_never_selected(self):
        paths=['/data/h/ref_enwiki-20200101-pages-meta-history1.xml.7z.txt.gz',
            '/data/h/enwiki-20200101-flowhistory.xml.bz2',
            '/data/h/enwiki-20200101-pages-meta-history1.xml.bz2.filepart',
            '/data/testdata/enwiki-20200101-pages-meta-history1.xml.bz2']
        self.assertEqual(catalog.source_sets([self.row(p,'xml_history') for p in paths]),[])
        zero=self.row('/data/h/enwiki-20200101-pages-meta-history1.xml.bz2','xml_history');zero['size_bytes']=0
        self.assertEqual(catalog.source_sets([zero]),[])

    def test_derived_mysql_dump_is_registered_but_not_original_source_eligible(self):
        rows=[self.row('/data/mysql_dump/enwiki20200101/enwiki20200101.page.00000.sql.xz','sql',['page']),
              self.row('/data/mysql_dump/enwiki20200101/enwiki20200101.categorylinks.00000.sql.xz','sql',['categorylinks'])]
        s=catalog.source_sets(rows)[0]
        self.assertFalse(s['eligible'])
        self.assertIn('source_provenance_unverified',s['missing_requirements'])

    def test_missing_history_shard_and_unknown_schema_block(self):
        incomplete=self.row('/data/h/enwiki-20200101-pages-meta-history4.xml.bz2','xml_history')
        s=catalog.source_sets([incomplete])[0]
        self.assertFalse(s['eligible'])
        self.assertIn('observed_history_shard_gap',s['missing_requirements'])
        partial=self.row('/data/h/enwiki-20200101-pages-meta-history1.xml.bz2.filepart','xml_history');partial['truncated']=True
        second=self.row('/data/h/enwiki-20200101-pages-meta-history2.xml.bz2','xml_history')
        s=catalog.source_sets([partial,second])[0]
        self.assertFalse(s['eligible'])

if __name__=='__main__':unittest.main()
