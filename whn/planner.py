"""Deterministic source choice, never a claim of completed graph recovery."""
import calendar
import datetime as dt
import hashlib
import json

POLICY_VERSION='quarterly-nearest-v1'

def instant(value):
    """Return the UTC instant; naive timestamps (including dates) mean UTC."""
    parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)

def quarter_targets(start,end):
    start,end=instant(start),instant(end)
    targets=[]
    for year in range(start.year,end.year+1):
        for month in (3,6,9,12):
            target=dt.datetime(year,month,calendar.monthrange(year,month)[1],23,59,59,tzinfo=dt.timezone.utc)
            if start<=target<=end:targets.append(target.isoformat().replace('+00:00','Z'))
    return targets

def plan_snapshot(wiki,target_time,sources):
    target=instant(target_time)
    available=[s for s in sources if s['wiki']==wiki and s.get('eligible')]
    xml=[s for s in available if s['kind']=='history_xml' and instant(s['date'])>=target]
    xml+= [s for s in available if s['kind']=='current_xml' and instant(s['date']).date()==target.date()]
    xml.sort(key=lambda s:(abs((instant(s['date'])-target).total_seconds()),s['id']))
    selected=xml[0] if xml else None
    sql=[s for s in available if s['kind']=='category_sql']
    sql.sort(key=lambda s:(abs((instant(s['date'])-target).total_seconds()),instant(s['date'])>target,s['id']))
    selected_sql=sql[0] if sql else None
    warnings=[] if selected_sql else ['sql_unavailable']
    if selected_sql and instant(selected_sql['date']).date()!=target.date():warnings.append('sql_temporal_approximation')
    if selected_sql and instant(selected_sql['date'])>target:warnings.append('future_sql_observations')
    if selected and selected['kind']=='history_xml':warnings.append('survivorship_and_historical_title_bias')
    return dict(snapshot_id=wiki+'-'+str(target.year)+'Q'+str((target.month-1)//3+1),wiki=wiki,
                target_time=target_time,policy_version=POLICY_VERSION,xml_source=selected,sql_source=selected_sql,
                warnings=warnings,status='planned_unverified' if selected else 'blocked_no_temporally_eligible_xml')

def source_observation(source,target_time):
    if source is None:return None
    return dict(id=source['id'],date=source['date'],kind=source['kind'],
                offset_days=(instant(source['date']).date()-instant(target_time).date()).days,
                file_count=source.get('file_count',0),coverage=source.get('coverage','filename/stat inventory; shard completeness unverified'),
                status='metadata_only_not_payload_verified')

def version_plan(plan,previous):
    def logical_source(source):
        if source is None:return None
        return {k:v for k,v in source.items() if k not in ('replica_count','locations','observed_at')}
    recipe={k:v for k,v in plan.items() if k not in ('plan_version','recipe_sha256','supersedes','invalidated_components')}
    for key in ('xml_source','sql_source'):recipe[key]=logical_source(recipe[key])
    digest=hashlib.sha256(json.dumps(recipe,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if previous and previous.get('recipe_sha256')==digest:return previous
    changed_context=not previous or previous.get('build_context')!=plan.get('build_context')
    changed_xml=changed_context or logical_source(previous['xml_source'])!=logical_source(plan['xml_source'])
    changed_sql=changed_context or logical_source(previous['sql_source'])!=logical_source(plan['sql_source'])
    invalidated=[]
    if changed_xml:invalidated+=['page_network','category_observations_xml']
    if changed_sql:invalidated+=['category_observations_sql']
    invalidated+=['category_union','category_graph','statistics']
    return dict(plan,recipe_sha256=digest,plan_version=(previous['plan_version']+1 if previous else 1),
                supersedes=previous['recipe_sha256'] if previous else None,invalidated_components=invalidated)
