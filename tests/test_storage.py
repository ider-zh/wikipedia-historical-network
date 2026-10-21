import importlib.util
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('storage',Path(__file__).resolve().parents[1]/'whn'/'storage.py')
assert spec is not None and spec.loader is not None and spec.origin is not None
storage=importlib.util.module_from_spec(spec)
if Path(spec.origin).exists():spec.loader.exec_module(storage)

class ParquetContractTests(unittest.TestCase):
    def test_typed_adjacency_roundtrip_and_no_page_body(self):
        self.assertTrue(hasattr(storage,'write_adjacency'),'typed adjacency writer missing')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'links.parquet'
            storage.write_adjacency(path,[dict(source_id=8,target_id_list=[9,4,9]),dict(source_id=10,target_id_list=[])])
            import pyarrow as pa
            import pyarrow.parquet as pq
            table=pq.read_table(path)
            self.assertEqual(table.to_pylist(),[dict(source_id=8,target_id_list=[4,9]),dict(source_id=10,target_id_list=[])])
            self.assertEqual(table.schema.field('target_id_list').type,pa.list_(pa.uint64()))
            self.assertEqual(pq.ParquetFile(path).metadata.row_group(0).column(0).compression,'ZSTD')
            with self.assertRaises(ValueError):storage.write_adjacency(Path(tmp)/'private.parquet',[dict(source_id=1,target_id_list=[],text='not allowed')])

if __name__=='__main__':unittest.main()
