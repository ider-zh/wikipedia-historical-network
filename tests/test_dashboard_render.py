"""Exercise the real renderer with a tiny DOM adapter; browser checks complement it."""
from test_dashboard_contract import node_json
import unittest

DOM = r"""
class E {
 constructor(tag='div') {this.tagName=tag;this.children=[];this.attrs={};this.listeners={};this.value='';this.hidden=false;this._text='';}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this._text='';this.children=nodes;}
 setAttribute(k,v){this.attrs[k]=String(v);}
 removeAttribute(k){delete this.attrs[k];}
 addEventListener(k,fn){this.listeners[k]=fn;}
 set textContent(v){this._text=String(v);this.children=[];}
 focus(){doc.activeElement=this;}
 get textContent(){return this._text+this.children.map(n=>typeof n==='string'?n:n.textContent).join('');}
}
const ids = new Map();
const doc={getElementById:id=>{if(!ids.has(id))ids.set(id,new E());return ids.get(id);},createElement:tag=>new E(tag)};
const get=id=>doc.getElementById(id);
const manifest={schema_version:1,generated_at:'2026-10-21T00:00:00Z',
project:{name:'<img src=x onerror=alert(1)>',phase:'planning',languages:['enwiki','zhwiki']},
inventory:{file_count:null,total_bytes:0,source_set_count:2,hosts:[]},
plans:[
 {snapshot_id:'enwiki-2026Q3',wiki:'enwiki',plan_version:'v1',status:'planned',target_time:'2026-09-30',
 xml_source:{id:'xml-1',date:'2026-10-01',offset_days:1,status:'unverified',coverage:'partial',file_count:0},sql_source:null,warnings:['<b>Review gap</b>']},
 {snapshot_id:'enwiki-2026Q3',wiki:'enwiki',plan_version:'v2',status:'blocked',target_time:'2026-09-30',xml_source:null,sql_source:null,warnings:[]},
 {snapshot_id:'zhwiki-2001Q1',wiki:'zhwiki',plan_version:'v1',status:'planned',target_time:'2001-03-31',xml_source:null,sql_source:null,warnings:[]}],
work_items:[{id:'parse',title:'Parser',status:'deferred'}],metrics:{graph_nodes:999}};
"""


class DashboardRenderTests(unittest.TestCase):
    def test_render_filter_inspect_versions_and_signed_source_offset(self):
        result = node_json(DOM + r"""
const ui=D.createDashboard(doc);
ui.setData(D.normalizeManifest(manifest),'JSON / HTTP');
const initial={title:get('project-name').textContent,files:get('file-count').textContent,
 total:get('result-count').textContent,index:get('index-status').textContent,
 source:get('source-detail').textContent,warnings:get('plan-warnings').textContent};
get('plan-search').value='2001';get('plan-search').listeners.input();
const search=get('plan-rows').textContent;
get('plan-search').value='';get('plan-search').listeners.input();
get('plan-version').value='1';get('plan-version').listeners.change();
const selected=get('selected-status').textContent;
get('source-select').value='sql_source';get('source-select').listeners.change();
const missing=get('source-detail').textContent;
ui.showError('missing manifest');
console.log(JSON.stringify({initial,search,selected,missing,error:get('load-state').textContent,
 cleared:get('plan-rows').textContent,disabled:get('plan-search').disabled}));
""")
        self.assertEqual(result["initial"]["title"], "<img src=x onerror=alert(1)>")
        self.assertEqual(result["initial"]["files"], "未知")
        self.assertIn("3", result["initial"]["total"])
        self.assertIn("未报告", result["initial"]["index"])
        self.assertIn("+1", result["initial"]["source"])
        self.assertIn("<b>Review gap</b>", result["initial"]["warnings"])
        self.assertIn("2001Q1", result["search"])
        self.assertNotIn("2026Q3", result["search"])
        self.assertIn("blocked", result["selected"])
        self.assertIn("未选择来源", result["missing"])
        self.assertIn("missing manifest", result["error"])
        self.assertNotIn("2001Q1", result["cleared"])
        self.assertTrue(result["disabled"])

    def test_selected_plan_retains_keyboard_focus_after_rerender(self):
        result = node_json(DOM + r"""
const ui=D.createDashboard(doc);ui.setData(D.normalizeManifest(manifest),'test');
const oldButton=get('plan-rows').children[1].children[0].children[0];
oldButton.focus();oldButton.listeners.click();
const button=get('plan-rows').children[1].children[0].children[0];
console.log(JSON.stringify({focused:doc.activeElement===button,selected:button.attrs['aria-pressed'],controls:button.attrs['aria-controls']}));
""")
        self.assertEqual(result, {"focused": True, "selected": "true", "controls": "detail-panel"})


if __name__ == "__main__":
    unittest.main()
