"""Read private inventories, append immutable recipes, export allowlisted static data."""
import argparse
import collections
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from whn.catalog import source_sets, private_bindings
from whn.planner import plan_snapshot, quarter_targets, source_observation, version_plan


def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.partial')
    with temp.open('w',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(temp,path)


def write_parquet(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    table=pa.Table.from_pylist(rows)
    temp=path.with_name(path.name+'.partial')
    pq.write_table(table,temp,compression='zstd')
    assert pq.read_table(temp).num_rows==len(rows)
    os.replace(temp,path)


def build_project(inventories,data_root,public_dir,as_of):
    data_root,public_dir=Path(data_root),Path(public_dir)
    events=[]
    seen_hosts=set()
    for path in inventories:
        with gzip.open(path,'rt',encoding='utf-8') as f:
            batch=[json.loads(line) for line in f]
        batch_hosts={e['host'] for e in batch if e.get('host')}
        if seen_hosts & batch_hosts:raise ValueError('duplicate inventory host across inputs')
        seen_hosts.update(batch_hosts)
        events.extend(batch)
    identities=set()
    for event in events:
        kind=event.get('type')
        if kind in ('discovery','host_end'):key=(event['host'],kind)
        elif kind in ('root_start','root_end'):key=(event['host'],kind,event['root'])
        elif kind=='file':key=(event['host'],kind,event['path'])
        else:continue
        if key in identities:raise ValueError('duplicate inventory record: '+kind)
        identities.add(key)
    rows=[e for e in events if e.get('type')=='file']
    hosts=sorted({e['host'] for e in events if e.get('host')})
    source=source_sets(rows)
    atomic_json(data_root/'catalog/source-sets.json',source)
    write_parquet(data_root/'catalog/source-sets.parquet',source)
    atomic_json(data_root/'catalog/source-bindings.private.json',private_bindings(rows))
    write_parquet(data_root/'catalog/files.parquet',[dict(host=r['host'],path=r['path'],size_bytes=r['size_bytes'],mtime_ns=r['mtime_ns'],
        device=r['device'],inode=r['inode'],inferred_wikis=r.get('inferred_wikis',[]),inferred_dates=r.get('inferred_dates',[]),
        representation=r['representation'],tables=r.get('tables',[]),truncated=r.get('truncated',False),
        source_eligible_candidate=r.get('source_eligible_candidate',False)) for r in rows])
    registry=data_root/'plans/latest.json'
    previous=json.loads(registry.read_text()) if registry.exists() else []
    previous={p['snapshot_id']:p for p in previous}
    plans=[]
    for wiki in ('enwiki','zhwiki'):
        for target in quarter_targets('2001-01-01',as_of):
            p=plan_snapshot(wiki,target,source)
            p['build_context']=dict(graph_schema='graph-v1',xml_adapter='upstream_integration_pending',
                wikitext_adapter='upstream_graph_only_integration_pending',ngd='definition_deferred',
                source_verification='metadata_only_not_build_ready')
            p=version_plan(p,previous.get(p['snapshot_id']))
            version_path=data_root/'plans/versions'/p['snapshot_id']/('v%04d.json'%p['plan_version'])
            if version_path.exists():
                if json.loads(version_path.read_text())!=p:raise ValueError('immutable recipe conflict: '+p['snapshot_id'])
            else:
                version_path.parent.mkdir(parents=True,exist_ok=True)
                with version_path.open('x',encoding='utf-8') as f:json.dump(p,f,ensure_ascii=False,indent=2)
            plans.append(p)
    atomic_json(registry,plans)
    write_parquet(data_root/'plans/latest.parquet',[dict(snapshot_id=p['snapshot_id'],wiki=p['wiki'],target_time=p['target_time'],
        plan_version=p['plan_version'],recipe_sha256=p['recipe_sha256'],status=p['status'],
        xml_source_id=p['xml_source']['id'] if p['xml_source'] else None,
        sql_source_id=p['sql_source']['id'] if p['sql_source'] else None,warnings=p['warnings']) for p in plans])
    host_summary=[]
    for index,host in enumerate(hosts):
        roots=[e for e in events if e['host']==host and e['type']=='root_end']
        starts=[e for e in events if e['host']==host and e['type']=='root_start']
        actual=collections.Counter(r['root'] for r in rows if r['host']==host)
        for end in roots:
            if end['files']!=actual[end['root']]:raise ValueError('root count audit failed')
        discoveries=[e for e in events if e['host']==host and e['type']=='discovery']
        declared=discoveries[0].get('roots') if len(discoveries)==1 else None
        expected=collections.Counter(declared) if isinstance(declared,list) else collections.Counter()
        start_counts=collections.Counter(e['root'] for e in starts)
        end_counts=collections.Counter(e['root'] for e in roots)
        host_ends=[e for e in events if e['type']=='host_end' and e['host']==host]
        complete=(len(host_ends)==1 and host_ends[0].get('root_count')==len(expected)
                  and bool(expected) and all(count==1 for count in expected.values())
                  and start_counts==end_counts==expected and set(actual)<=set(expected))
        clean=(complete and all(e['status']=='complete' and e.get('errors',0)==0
                               and not e.get('truncated',False) for e in roots)
               and not any(e['type']=='error' and e['host']==host for e in events))
        host_summary.append(dict(label='Source '+chr(65+index),status='metadata_indexed' if clean else 'indexed_with_gaps',
            file_count=sum(r['host']==host for r in rows),errors=[] if clean else ['Some selected roots were unavailable, excluded or incomplete; see private coverage report.']))
    all_clean=all(h['status']=='metadata_indexed' for h in host_summary)
    projection=dict(schema_version=1,generated_at=as_of,
        project=dict(name='Wikipedia Historical Network',phase='source_planning',languages=['enwiki','zhwiki'],storage_format='Parquet + ZSTD',processing_location_label='220 SSD (private data workspace)'),
        inventory=dict(file_count=len(rows),total_bytes=sum(r['size_bytes'] for r in rows),source_set_count=len(source),hosts=host_summary),
        plans=[dict(snapshot_id=p['snapshot_id'],wiki=p['wiki'],target_time=p['target_time'],plan_version='v'+str(p['plan_version']),status=p['status'],
            xml_source=source_observation(p['xml_source'],p['target_time']),sql_source=source_observation(p['sql_source'],p['target_time']),warnings=p['warnings']+['source_payload_unverified','shard_completeness_unverified']) for p in plans],
        work_items=[dict(id='inventory',title='三台来源机器 metadata inventory（非源完整性验证）',status='complete' if all_clean else 'blocked'),
            dict(id='plan',title='中英文季度选源与不可变版本',status='complete'),
            dict(id='dashboard',title='纯静态计划与进度展示',status='complete'),
            dict(id='validate',title='源覆盖与身份映射预检 + 中文小范围试跑',status='planned'),
            dict(id='english',title='英文季度图批处理与验证',status='planned'),
            dict(id='ngd',title='NGD 公式及统计口径确认',status='deferred')],
        metrics=dict(index_status='metadata_only' if all_clean else 'metadata_with_gaps',index_record_count=len(rows),index_total_count=len(rows)))
    atomic_json(public_dir/'project.json',projection)
    script='window.WHN_DATA = '+json.dumps(projection,ensure_ascii=True,separators=(',',':'))+';\n'
    (public_dir/'project.js').write_text(script,encoding='utf-8')
    csv_rows=[]
    for p in projection['plans']:
        row={key:p[key] for key in ('snapshot_id','wiki','target_time','plan_version','status')}
        for key in ('xml_source','sql_source'):
            selected=p[key]
            for field in ('id','date','offset_days','file_count'):
                row[key+'_'+field]=selected[field] if selected else ''
        row['warnings']=';'.join(p['warnings'])
        csv_rows.append(row)
    if csv_rows:
        with (public_dir/'quarterly-plan.csv').open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(csv_rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(csv_rows)
    return projection


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory',action='append',required=True,type=Path)
    parser.add_argument('--data-root',required=True,type=Path)
    parser.add_argument('--public-dir',default=Path('dashboard/data'),type=Path)
    parser.add_argument('--as-of',required=True)
    args=parser.parse_args()
    projection=build_project(args.inventory,args.data_root,args.public_dir,args.as_of)
    print(json.dumps(dict(inventory=projection['inventory'],quarter_plans=len(projection['plans']),statuses=dict(collections.Counter(p['status'] for p in projection['plans']))),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
