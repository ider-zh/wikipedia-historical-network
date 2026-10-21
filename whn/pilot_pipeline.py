"""Backpressured in-memory XML pipeline; only graph metadata reaches disk."""
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import zlib
from whn.pilot import decode_graph_record


def execute_pipeline(decoder_cmd,selector_cmd,graph_cmd,output_dir,expected_xml_bytes,expected_crc32,max_records=20000,deadline_seconds=1800,max_graph_bytes=256<<20):
    if type(max_records) is not int or max_records<1 or type(max_graph_bytes) is not int or max_graph_bytes<1:
        raise ValueError('invalid pipeline budget')
    if type(deadline_seconds) not in (int,float) or not 0<deadline_seconds<=86400:
        raise ValueError('invalid pipeline deadline')
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=False)
    logs=[];children=[];errors=[];stats=dict(xml_bytes=0,xml_crc32=0)
    started=time.monotonic()
    def log(name):
        f=(out/(name+'.stderr.log')).open('wb');logs.append(f);return f
    timer=None;worker=None
    try:
        decoder=subprocess.Popen(decoder_cmd,stdout=subprocess.PIPE,stderr=log('decoder'));children.append(decoder)
        selector=subprocess.Popen(selector_cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log('selector'));children.append(selector)
        assert decoder.stdout and selector.stdin and selector.stdout
        graph=subprocess.Popen(graph_cmd,stdin=selector.stdout,stdout=subprocess.PIPE,stderr=log('wikitext'));children.append(graph)
        assert graph.stdout
        selector.stdout.close()
        def pump():
            try:
                assert decoder.stdout and selector.stdin
                for block in iter(lambda:decoder.stdout.read(65536),b''):
                    stats['xml_bytes']+=len(block);stats['xml_crc32']=zlib.crc32(block,stats['xml_crc32'])
                    selector.stdin.write(block)
            except BaseException as exc:errors.append(type(exc).__name__)
            finally:
                for f in (decoder.stdout,selector.stdin):
                    if f and not f.closed:
                        try:f.close()
                        except OSError:pass
        worker=threading.Thread(target=pump,daemon=True);worker.start()
        def terminate():
            for child in children:
                if child.poll() is None:child.kill()
        timer=threading.Timer(deadline_seconds,terminate);timer.start()
        records=[];graph_bytes=0
        with (out/'graph-records.jsonl.partial').open('w',encoding='utf-8') as f:
            while True:
                line=graph.stdout.readline((32<<20)+1)
                if not line:break
                if len(line)>32<<20:raise ValueError('graph line limit exceeded')
                graph_bytes+=len(line)
                if graph_bytes>max_graph_bytes:raise ValueError('graph byte budget exceeded')
                row=decode_graph_record(json.loads(line))
                if len(records)>=max_records:raise ValueError('bounded pilot page limit exceeded')
                records.append(row);f.write(json.dumps(row,ensure_ascii=False)+'\n')
        graph.stdout.close();worker.join(timeout=max(1,deadline_seconds-(time.monotonic()-started)))
        codes=[p.wait(timeout=max(1,deadline_seconds-(time.monotonic()-started))) for p in children]
        if worker.is_alive() or errors or any(codes):raise RuntimeError('pipeline exits='+str(codes)+' pump_errors='+str(errors))
        crc='%08X'%(stats['xml_crc32']&0xffffffff)
        if stats['xml_bytes']!=expected_xml_bytes or crc!=expected_crc32.upper():raise ValueError('complete XML bytes/CRC mismatch')
        os.replace(out/'graph-records.jsonl.partial',out/'graph-records.jsonl')
        proof=dict(status='single_archive_pipeline_verified',records=len(records),xml_bytes=stats['xml_bytes'],xml_crc32=crc,
            complete_archive_decoded=True,exit_codes=codes,runtime_seconds=time.monotonic()-started,wikitext_persisted=False)
        (out/'pipeline-verification.json').write_text(json.dumps(proof,indent=2)+'\n')
        return records,proof
    finally:
        if timer:timer.cancel()
        for child in children:
            if child.poll() is None:child.kill()
        for child in children:child.wait()
        if worker:worker.join(timeout=5)
        for child in children:
            for name in ('stdin','stdout'):
                f=getattr(child,name,None)
                if f and not f.closed:
                    try:f.close()
                    except OSError:pass
        for f in logs:f.close()
