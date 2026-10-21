"""Planner tracer: a quarterly target cannot use a future-only current XML."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('planner',Path(__file__).resolve().parents[1]/'whn'/'planner.py')
assert spec is not None and spec.loader is not None and spec.origin is not None
planner=importlib.util.module_from_spec(spec)
if Path(spec.origin).exists():spec.loader.exec_module(planner)

class PlannerTests(unittest.TestCase):
    def test_quarter_end_and_history_selection(self):
        self.assertTrue(hasattr(planner,'plan_snapshot'),'snapshot planner missing')
        target='2004-12-31T23:59:59Z'
        sources=[dict(id='history-2020',wiki='enwiki',date='2020-01-01',kind='history_xml',eligible=True,file_count=1),
                 dict(id='current-2005',wiki='enwiki',date='2005-01-01',kind='current_xml',eligible=True,file_count=1)]
        plan=planner.plan_snapshot('enwiki',target,sources)
        self.assertEqual(plan['xml_source']['id'],'history-2020')
        self.assertEqual(plan['status'],'planned_unverified')
        self.assertIsNone(plan['sql_source'])
        self.assertIn('sql_unavailable',plan['warnings'])
        self.assertEqual(planner.quarter_targets('2001-01-01','2001-10-01'),['2001-03-31T23:59:59Z','2001-06-30T23:59:59Z','2001-09-30T23:59:59Z'])

    def test_sql_nearest_source_and_immutable_version(self):
        self.assertTrue(hasattr(planner,'version_plan'),'versioned plans missing')
        sources=[dict(id='h20',wiki='enwiki',date='2020-01-01',kind='history_xml',eligible=True,file_count=1),
                 dict(id='s07',wiki='enwiki',date='2007-01-01',kind='category_sql',eligible=True,file_count=3),
                 dict(id='s03',wiki='enwiki',date='2003-01-01',kind='category_sql',eligible=True,file_count=3)]
        target='2004-12-31T23:59:59Z'
        a=planner.version_plan(planner.plan_snapshot('enwiki',target,sources),None)
        self.assertEqual(a['sql_source']['id'],'s07')
        self.assertEqual(a['plan_version'],1)
        self.assertIn('sql_temporal_approximation',a['warnings'])
        self.assertIn('future_sql_observations',a['warnings'])
        sources.append(dict(id='s04',wiki='enwiki',date='2004-12-31',kind='category_sql',eligible=True,file_count=3))
        b=planner.version_plan(planner.plan_snapshot('enwiki',target,sources),a)
        self.assertEqual(b['plan_version'],2)
        self.assertEqual(b['sql_source']['id'],'s04')
        self.assertEqual(b['invalidated_components'],['category_observations_sql','category_union','category_graph','statistics'])
        self.assertEqual(planner.version_plan(planner.plan_snapshot('enwiki',target,list(reversed(sources))),b),b)

    def test_temporal_edges_unverified_and_ngd_deferred(self):
        sources=[dict(id='old',wiki='enwiki',date='2003-01-01',kind='history_xml',eligible=True,file_count=1),
                 dict(id='bad',wiki='enwiki',date='2005-01-01',kind='history_xml',eligible=False,file_count=1)]
        p=planner.plan_snapshot('enwiki','2004-12-31T23:59:59Z',sources)
        self.assertIsNone(p['xml_source'])
        self.assertEqual(p['status'],'blocked_no_temporally_eligible_xml')
        self.assertTrue(hasattr(planner,'source_observation'),'source offset projection missing')
        obs=planner.source_observation(dict(id='h',date='2020-01-01',kind='history_xml',file_count=3),'2004-12-31T23:59:59Z')
        self.assertGreater(obs['offset_days'],0)
        self.assertEqual(obs['status'],'metadata_only_not_payload_verified')
        self.assertNotIn('path',obs)
        dates=planner.quarter_targets('2001-01-01','2026-10-21T11:00:00Z')
        self.assertEqual(len(dates),103)
        self.assertEqual(dates[-1],'2026-09-30T23:59:59Z')

    def test_new_replica_does_not_invalidate_graph_recipe(self):
        source=dict(id='h20',wiki='enwiki',date='2020-01-01',kind='history_xml',eligible=True,file_count=1,replica_count=1)
        first=planner.version_plan(planner.plan_snapshot('enwiki','2004-12-31T23:59:59Z',[source]),None)
        source['replica_count']=2
        same=planner.version_plan(planner.plan_snapshot('enwiki','2004-12-31T23:59:59Z',[source]),first)
        self.assertEqual(same['plan_version'],1,'new physical placement must not rebuild logical recipe')

if __name__=='__main__':unittest.main()
