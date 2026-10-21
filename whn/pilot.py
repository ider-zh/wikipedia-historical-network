"""Bounded-scope graph assembly; input records contain graph metadata, never wikitext."""
import collections
import os
import re
import tempfile
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from whn.storage import write_adjacency

GRAPH_KEYS={'page_id','ns','title','revision_id','timestamp','text_state','links','categories','redirect_target','parse_status'}

def decode_graph_record(row):
    """Convert only canonical decimal IDs at the lossless JSON boundary."""
    if not isinstance(row,dict) or set(row)!=GRAPH_KEYS:
        raise ValueError('unexpected/private graph fields')
    decoded=dict(row)
    for key in ('page_id','revision_id'):
        value=decoded[key]
        if isinstance(value,str):
            if not re.fullmatch(r'[1-9][0-9]{0,19}',value):
                raise ValueError('invalid decimal graph identity')
            decoded[key]=int(value)
    validate_graph_record(decoded)
    return decoded


def validate_graph_record(row):
    """Validate the entire allowlisted tree before persisting graph metadata."""
    if not isinstance(row,dict) or set(row)!=GRAPH_KEYS:
        raise ValueError('unexpected/private graph fields')
    if any(type(row[k]) is not int or not 0<row[k]<2**64 for k in ('page_id','revision_id')):
        raise ValueError('invalid graph identity')
    if type(row['ns']) is not int or row['ns'] not in (0,14):
        raise ValueError('invalid pilot namespace')
    if any(not isinstance(row[k],str) or not row[k] for k in ('title','timestamp')):
        raise ValueError('invalid graph scalar')
    if row['text_state'] not in ('present','empty','hidden','missing') or row['parse_status'] not in ('ok','unavailable'):
        raise ValueError('invalid graph state')
    if not isinstance(row['links'],list) or not isinstance(row['categories'],list):
        raise ValueError('invalid graph arrays')
    for link in row['links']:
        if not isinstance(link,dict) or not {'target'}<=set(link)<= {'target','namespace'}:
            raise ValueError('unexpected/private link fields')
        if not isinstance(link['target'],str) or not link['target'] or ('namespace' in link and type(link['namespace']) is not int):
            raise ValueError('invalid graph link')
    if any(not isinstance(c,str) or not c for c in row['categories']):
        raise ValueError('invalid category metadata')
    if row['redirect_target'] is not None and not isinstance(row['redirect_target'],str):
        raise ValueError('invalid redirect metadata')
    if row['text_state'] in ('hidden','missing'):
        if row['parse_status']!='unavailable' or row['links'] or row['categories'] or row['redirect_target'] is not None:
            raise ValueError('unavailable text cannot produce inferred graph edges')
    elif row['parse_status']!='ok':
        raise ValueError('invalid present graph status')


def normalized_title(title):
    return title.replace('_',' ').strip().split('#',1)[0].strip()

def category_title(title):
    title=normalized_title(title)
    if ':' in title:
        prefix,rest=title.split(':',1)
        if prefix.casefold() in ('category','分类','分類'):
            return rest.strip()
    return title


def target_key(title,namespace=0):
    title=normalized_title(title)
    if ':' in title and title.split(':',1)[0].casefold() in ('category','分类','分類'):
        return (14,category_title(title))
    return (namespace,category_title(title) if namespace==14 else title)


def assemble_graph(records,sql_observations=()):
    records=list(records)
    sql_observations=list(sql_observations)
    pages={};titles={}
    for row in records:
        validate_graph_record(row)
        pid=row['page_id']
        if type(pid) is not int or pid<=0 or pid in pages:raise ValueError('duplicate or invalid page identity')
        if row['parse_status'] not in ('ok','unavailable'):raise ValueError('unaccepted wikitext parse status')
        if row['text_state'] in ('hidden','missing') and (row['parse_status']!='unavailable' or row['links'] or row['categories'] or row['redirect_target']):raise ValueError('unavailable text cannot produce inferred graph edges')
        title=normalized_title(row['title'])
        key=(row['ns'],category_title(title) if row['ns']==14 else title)
        if key in titles:raise ValueError('ambiguous title identity')
        pages[pid]=row;titles[key]=pid
    categories=sorted({category_title(c) for r in records for c in r['categories']}|{category_title(o['category_title']) for o in sql_observations}|{category_title(r['title']) for r in records if r['ns']==14})
    category_ids={title:i+1 for i,title in enumerate(categories)}
    registry=[dict(category_id=i,title=t) for t,i in category_ids.items()]
    adjacency=[];unresolved=[];xml=collections.defaultdict(set);sql=collections.defaultdict(set);redirects=[]
    for pid,row in sorted(pages.items()):
        targets=set()
        for link in row['links']:
            ns,target=target_key(link['target'],link.get('namespace',0))
            matched=titles.get((ns,target))
            if matched is None:unresolved.append(dict(source_id=pid,target_title=target,target_namespace=ns,reason='outside_pilot_or_unresolved_historical_title'))
            else:targets.add(matched)
        adjacency.append(dict(source_id=pid,target_id_list=sorted(targets)))
        for c in row['categories']:xml[pid].add(category_ids[category_title(c)])
        if row['redirect_target']:
            ns,target=target_key(row['redirect_target'])
            redirects.append(dict(source_id=pid,target_title=target,target_namespace=ns,target_id=titles.get((ns,target))))
    for o in sql_observations:
        if o['source_page_id'] in pages:sql[o['source_page_id']].add(category_ids[category_title(o['category_title'])])
    union=[];category_graph=[]
    for pid in sorted(pages):
        targets=sorted(xml[pid]|sql[pid]);masks=[(1 if t in xml[pid] else 0)|(2 if t in sql[pid] else 0) for t in targets]
        union.append(dict(source_id=pid,target_id_list=targets,source_mask_list=masks))
        if pages[pid]['ns']==14:
            source=category_ids[category_title(pages[pid]['title'])]
            category_graph.append(dict(source_id=source,target_id_list=targets))
    category_graph.sort(key=lambda r:r['source_id'])
    cat_edges={r['source_id']:set(r['target_id_list']) for r in category_graph}
    indegree={cid:0 for cid in category_ids.values()}
    for targets in cat_edges.values():
        for target in targets:indegree[target]+=1
    queue=collections.deque(cid for cid,n in indegree.items() if n==0);removed=0
    while queue:
        cid=queue.popleft();removed+=1
        for target in cat_edges.get(cid,()):
            indegree[target]-=1
            if indegree[target]==0:queue.append(target)
    counts=dict(category_cycle_detected=removed<len(indegree),pages=len(pages),page_edges=sum(len(r['target_id_list']) for r in adjacency),unresolved_page_links=len(unresolved),
        category_registry=len(registry),xml_category_edges=sum(map(len,xml.values())),sql_category_edges=sum(map(len,sql.values())),category_union_edges=sum(len(r['target_id_list']) for r in union),
        category_graph_edges=sum(len(r['target_id_list']) for r in category_graph),redirects=len(redirects))
    return dict(pages=[{k:r[k] for k in ('page_id','ns','title','revision_id','timestamp','text_state','parse_status')} for pid,r in sorted(pages.items())],
        page_links=adjacency,category_registry=registry,category_xml=[dict(source_id=pid,target_id_list=sorted(xml[pid])) for pid in sorted(pages)],
        category_sql=[dict(source_id=pid,target_id_list=sorted(sql[pid])) for pid in sorted(pages)],category_union=union,category_graph=category_graph,redirects=redirects,unresolved=unresolved,counts=counts)

def write_graph(directory,graph):
    directory=Path(directory)
    directory.parent.mkdir(parents=True,exist_ok=True)
    directory.mkdir(exist_ok=False)  # Reserve a new generation; never modify old output.
    with tempfile.TemporaryDirectory(prefix='.'+directory.name+'-',dir=directory.parent) as tmp:
        staging=Path(tmp)
        written=_write_graph_tables(staging,graph)
        os.replace(staging,directory)  # Publish all tables over our empty reservation.
    return [directory/p.name for p in written]


def _write_graph_tables(directory,graph):
    directory=Path(directory);written=[]
    for name in ('page_links','category_xml','category_sql','category_graph'):
        path=directory/(name+'.parquet');write_adjacency(path,graph[name]);written.append(path)
    schemas={
        'pages':pa.schema([('page_id',pa.uint64()),('ns',pa.int32()),('title',pa.string()),('revision_id',pa.uint64()),('timestamp',pa.string()),('text_state',pa.string()),('parse_status',pa.string())]),
        'category_registry':pa.schema([('category_id',pa.uint64()),('title',pa.string())]),
        'category_union':pa.schema([('source_id',pa.uint64()),('target_id_list',pa.list_(pa.uint64())),('source_mask_list',pa.list_(pa.uint8()))]),
        'redirects':pa.schema([('source_id',pa.uint64()),('target_title',pa.string()),('target_namespace',pa.int32()),('target_id',pa.uint64())]),
        'unresolved':pa.schema([('source_id',pa.uint64()),('target_title',pa.string()),('target_namespace',pa.int32()),('reason',pa.string())])}
    for name,schema in schemas.items():
        path=directory/(name+'.parquet')
        if path.exists():raise FileExistsError(path)
        table=pa.Table.from_pylist(graph[name],schema=schema);pq.write_table(table,path,compression='zstd');assert pq.read_table(path).equals(table);written.append(path)
    return written
