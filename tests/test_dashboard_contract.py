"""Dependency-free dashboard tests; synthetic records never ship as project data."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "dashboard" / "app.js"


def node_json(body):
    if not shutil.which("node"):
        raise unittest.SkipTest("Node is required for dashboard behavior tests")
    script = "const D = require(" + json.dumps(str(APP)) + ");\n" + body
    result = subprocess.run(["node", "-e", script], text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class DashboardContractTests(unittest.TestCase):
    def test_manifest_rejects_unknown_schema_and_preserves_unknown_inventory(self):
        self.assertTrue(APP.exists(), "dashboard app missing: contract has no implementation")
        result = node_json("""
const base = {schema_version:1, generated_at:null, project:{name:'test', languages:[]},
  inventory:{file_count:null, hosts:[]}, plans:[], work_items:[]};
const data = D.normalizeManifest(base);
let invalid = false;
try { D.normalizeManifest({...base, schema_version:2}); } catch (e) { invalid = true; }
console.log(JSON.stringify({invalid, count:data.inventory.file_count,
  plans:data.plans.length, metrics:data.metrics}));
""")
        self.assertEqual(result, {"invalid": True, "count": None, "plans": 0, "metrics": {}})

    def test_plan_filtering_versions_sources_and_metric_allowlist(self):
        result = node_json("""
const source = {id:'source-1', date:'2026-10-01', kind:'xml', offset_days:1,
 file_count:0, coverage:'partial', status:'unverified', private_path:'DO_NOT_EXPOSE'};
const base = {schema_version:1, project:{languages:['enwiki','zhwiki']}, inventory:{},
 plans:[{snapshot_id:'enwiki-2026Q3',wiki:'enwiki',target_time:'2026-09-30T23:59:59Z',
 plan_version:'v2',status:'planned',xml_source:source,sql_source:null,warnings:['gap']},
 {snapshot_id:'zhwiki-2001Q1',wiki:'zhwiki',target_time:'2001-03-31T23:59:59Z',
 plan_version:'v1',status:'blocked',xml_source:null,sql_source:null,warnings:[]}],
 work_items:[{id:'one',title:'Index',status:'verified'}],
 metrics:{index_status:'partial',index_record_count:7,index_total_count:10,graph_nodes:99}};
const data = D.normalizeManifest(base);
console.log(JSON.stringify({source:data.plans[0].xml_source,
 quarter:D.quarterLabel(data.plans[0]),
 found:D.filterPlans(data.plans,{query:'2026q3 v2',wiki:'enwiki',status:'planned'}).length,
 noResult:D.filterPlans(data.plans,{query:'2001',wiki:'enwiki',status:''}).length,
 metrics:data.metrics, summary:D.workSummary(data.work_items)}));
""")
        self.assertEqual(result["source"], {"id": "source-1", "date": "2026-10-01", "kind": "xml",
            "offset_days": 1, "file_count": 0, "coverage": "partial", "status": "unverified"})
        self.assertEqual(result["quarter"], "2026Q3")
        self.assertEqual(result["found"], 1)
        self.assertEqual(result["noResult"], 0)
        self.assertEqual(result["metrics"], {"index_status": "partial", "index_record_count": 7, "index_total_count": 10})
        self.assertEqual(result["summary"], {"complete": 1, "total": 1})

    def test_http_file_loading_and_no_fabricated_fallback(self):
        result = node_json("""
(async () => {
 const data = {schema_version:1,project:{},inventory:{},plans:[],work_items:[]};
 let fetchCalls=0, scriptCalls=0;
 const fetcher=async (url,opts) => {fetchCalls++; if(url!=='data/project.json' || opts.cache!=='no-store') throw Error('wrong fetch'); return {ok:true,json:async()=>data};};
 const scriptLoader=async()=>{scriptCalls++;return data;};
 const http=await D.loadManifest({protocol:'http:',fetcher,scriptLoader});
 const file=await D.loadManifest({protocol:'file:',fetcher,scriptLoader});
 const fallback=await D.loadManifest({protocol:'http:',fetcher:async()=>{throw Error('missing');},scriptLoader});
 let missing=false, invalid=false;
 try {await D.loadManifest({protocol:'file:',scriptLoader:async()=>undefined});} catch(e){missing=true;}
 try {await D.loadManifest({protocol:'http:',fetcher:async()=>({ok:true,json:async()=>({schema_version:2})}),scriptLoader});} catch(e){invalid=true;}
 console.log(JSON.stringify({fetchCalls,scriptCalls,http:http.transport,file:file.transport,fallback:fallback.transport,missing,invalid}));
})().catch(e=>{console.error(e);process.exit(1);});
""")
        self.assertEqual(result, {"fetchCalls": 1, "scriptCalls": 2, "http": "JSON / HTTP",
            "file": "JS / file", "fallback": "JS / HTTP fallback", "missing": True, "invalid": True})


if __name__ == "__main__":

    unittest.main()
