#!/usr/bin/env python3
"""Exercise actual static dashboard via HTTP and file mode; no public deployment."""
import argparse
import functools
import http.server
import json
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--evidence-dir',required=True,type=Path,help='Private screenshots and verification output directory')
parser.add_argument('--browser',required=True,type=Path,help='Installed Chromium executable')
args=parser.parse_args()
evidence=args.evidence_dir
evidence.mkdir(parents=True,exist_ok=True)
manifest=json.loads((root/'dashboard/data/project.json').read_text())
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
handler=functools.partial(Quiet,directory=str(root/'dashboard'))
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=str(args.browser),headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport=dict(width=1440,height=1000))
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:'+str(server.server_port)+'/')
        page.wait_for_function("document.querySelector('#plan-search').disabled === false")
        page.wait_for_timeout(200)
        assert page.locator('#plan-rows tr').count()==len(manifest['plans'])
        assert str(manifest['inventory']['file_count']) in page.locator('#file-count').inner_text().replace(',','')
        page.screenshot(path=str(evidence/'desktop.png'),full_page=True)
        page.select_option('#language-filter','zhwiki')
        assert page.locator('#plan-rows tr').count()==103
        page.fill('#plan-search','2026Q3')
        assert page.locator('#plan-rows tr').count()==1
        page.locator('#plan-rows button').first.click()
        assert 'zhwiki-2026Q3' in page.locator('#selected-id').inner_text()
        page.select_option('#source-select','sql_source')
        assert '2026-10-01' in page.locator('#source-detail').inner_text()
        page.screenshot(path=str(evidence/'blocked-quarter.png'),full_page=True)
        page.set_viewport_size(dict(width=390,height=844))
        page.screenshot(path=str(evidence/'mobile.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'mobile overflow'
        page.goto((root/'dashboard/index.html').as_uri())
        page.wait_for_function("document.querySelector('#plan-search').disabled === false")
        assert page.locator('#plan-rows tr').count()==206
        assert not errors,errors
        report=dict(status='passed',actual_plan_rows=len(manifest['plans']),language_filter_rows=103,
            blocked_quarter_inspected='zhwiki-2026Q3',http=True,file_mode=True,mobile_overflow=False,console_errors=errors,
            screenshots=['desktop.png','blocked-quarter.png','mobile.png'])
        (evidence/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(report,ensure_ascii=False,indent=2))
        browser.close()
finally:
    server.shutdown();server.server_close()
