"""Typed compressed Parquet contracts; graph parsing belongs to upstream adapters."""
from pathlib import Path
import os
import pyarrow as pa
import pyarrow.parquet as pq

ADJACENCY_SCHEMA=pa.schema([pa.field('source_id',pa.uint64(),nullable=False),
                          pa.field('target_id_list',pa.list_(pa.uint64()),nullable=False)])

def write_adjacency(path,rows,batch_size=65536):
    path=Path(path)
    partial=path.with_name(path.name+'.partial')
    if path.exists() or partial.exists():raise FileExistsError(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    previous=-1
    try:
        with pq.ParquetWriter(partial,ADJACENCY_SCHEMA,compression='zstd') as writer:
            batch=[]
            for row in rows:
                if set(row)!={'source_id','target_id_list'}:raise ValueError('only graph identity fields allowed')
                source=row['source_id']
                if type(source) is not int or not 0<source<2**64 or source<=previous:raise ValueError('source IDs must be sorted, unique positive uint64')
                previous=source
                targets=row['target_id_list']
                if not isinstance(targets,list) or any(type(x) is not int or not 0<x<2**64 for x in targets):raise ValueError('target IDs must be positive uint64')
                batch.append(dict(source_id=source,target_id_list=sorted(set(targets))))
                if len(batch)>=batch_size:
                    writer.write_table(pa.Table.from_pylist(batch,schema=ADJACENCY_SCHEMA));batch=[]
            if batch:writer.write_table(pa.Table.from_pylist(batch,schema=ADJACENCY_SCHEMA))
        with partial.open('rb') as f:os.fsync(f.fileno())
        os.replace(partial,path)
    finally:
        if partial.exists():partial.unlink()
