"""Conservative filename-derived source sets, separate from private file placement."""
import collections
import datetime as dt
import hashlib
import json
import re
from pathlib import PurePosixPath


def source_sets(rows, include_private=False):
    groups=collections.defaultdict(list)
    for row in rows:
        if row.get('type')!='file' or not row.get('source_eligible_candidate') or row.get('truncated') or row.get('size_bytes',0)<=0:continue
        if set(PurePosixPath(row['path']).parts)&{'testdata','fixtures','.git'}:continue
        wikis=row.get('inferred_wikis',[])
        dates=row.get('inferred_dates',[])
        if len(wikis)!=1 or len(dates)!=1:continue
        try:date=dt.datetime.strptime(dates[0],'%Y%m%d').date().isoformat()
        except ValueError:continue
        name=PurePosixPath(row['path']).name.lower()
        rep=row['representation']
        if any(t in name for t in ('stub','abstract','index')):continue
        kind='history_xml' if rep=='xml_history' else 'current_xml' if rep=='xml' and any(t in name for t in ('pages-articles','pages-meta-current')) else 'category_sql' if rep=='sql' else None
        if not kind:continue
        if kind=='history_xml' and not re.fullmatch(re.escape(wikis[0])+r'-'+dates[0]+r'-pages-meta-history\d*\.xml(?:-p\d+p\d+)?(?:\.(?:7z|bz2|gz|xz|zst))?',name):continue
        if kind=='current_xml' and not re.fullmatch(re.escape(wikis[0])+r'-'+dates[0]+r'-pages-(?:articles(?:-multistream)?|meta-current)\d*\.xml(?:-p\d+p\d+)?(?:\.(?:7z|bz2|gz|xz|zst))?',name):continue
        if kind=='category_sql' and (not re.search(r'\.sql(?:\.(?:gz|bz2|xz|zst))?$',name) or 'schema' in name or 'structure' in name):continue
        encoding=re.sub(r'^\.xml(?:-p\d+p\d+)?','.xml',name[name.find('.xml'):]) if kind in ('history_xml','current_xml') else 'sql_tables'
        key=(row['host'],str(PurePosixPath(row['path']).parent),wikis[0],date,kind,encoding)
        groups[key].append(row)
    output=[]
    for (host,parent,wiki,date,kind,encoding),files in sorted(groups.items()):
        signature=[dict(name=PurePosixPath(r['path']).name,size_bytes=r['size_bytes'],mtime_ns=r['mtime_ns']) for r in sorted(files,key=lambda r:r['path'])]
        signature_hash=hashlib.sha256(json.dumps(signature,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        tables=sorted({t for f in files for t in f.get('tables',[])})
        missing=[]
        if kind=='history_xml':
            shard_numbers=sorted({int(m.group(1)) for f in files if (m:=re.search(r'pages-meta-history(\d+)\.xml',PurePosixPath(f['path']).name))})
            if shard_numbers and shard_numbers!=list(range(1,max(shard_numbers)+1)):missing.append('observed_history_shard_gap')
        if kind=='category_sql' and not {'page','categorylinks'}<=set(tables):missing.append('same_source_page_and_categorylinks_sql')
        provenance='original_dump_candidate'
        if kind=='category_sql' and ('mysql_dump' in PurePosixPath(parent).parts or not all(re.match(re.escape(wiki)+r'-\d{8}-',PurePosixPath(f['path']).name.lower()) for f in files)):
            missing.append('source_provenance_unverified');provenance='local_logical_export_provenance_unverified'
        eligible=not missing
        source_id=wiki+'-'+date.replace('-','')+'-'+kind+'-'+signature_hash[:12]
        # Paths remain only in private inventory, public ID binds an inferred set.
        output.append(dict(id=source_id,wiki=wiki,date=date,kind=kind,file_count=len(files),
            total_bytes=sum(f['size_bytes'] for f in files),tables=tables,eligible=eligible,payload_verified=False,
            fingerprint_sha256=signature_hash,
            coverage='filename/stat index only; payload and shard completeness unverified',
            missing_requirements=missing,provenance_class=provenance))
        if include_private:output[-1]['locations']=[dict(host=host,paths=sorted(f['path'] for f in files))]
    # Same IDs can occur on multiple physical replicas. Never sum or double-build them.
    unique={}
    for source in output:
        if source['id'] in unique:
            unique[source['id']]['replica_count']+=1
            if include_private:unique[source['id']]['locations'].extend(source['locations'])
        else:unique[source['id']]=dict(source,replica_count=1)
    return sorted(unique.values(),key=lambda s:(s['wiki'],s['date'],s['kind'],s['id']))


def private_bindings(rows):
    return {source['id']:source['locations'] for source in source_sets(rows,include_private=True)}
