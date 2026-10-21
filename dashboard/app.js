/* Static, dependency-free dashboard. No source data is embedded here. */
(function (root) {
  'use strict';
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const text = value => typeof value === 'string' ? value : '';
  const count = value => Number.isSafeInteger(value) && value >= 0 ? value : null;
  const strings = value => Array.isArray(value) ? value.filter(item => typeof item === 'string') : [];

  function normalizeSource(source) {
    if (!object(source)) return null;
    return {
      id: text(source.id), date: text(source.date), kind: text(source.kind),
      offset_days: typeof source.offset_days === 'number' && Number.isFinite(source.offset_days) ? source.offset_days : null,
      file_count: count(source.file_count), coverage: text(source.coverage), status: text(source.status)
    };
  }

  function quarterLabel(plan) {
    const match = text(plan.snapshot_id).match(/\d{4}Q[1-4]/i);
    if (match) return match[0].toUpperCase();
    const date = new Date(plan.target_time);
    if (!Number.isFinite(date.getTime())) return '未提供';
    return date.getUTCFullYear() + 'Q' + (Math.floor(date.getUTCMonth() / 3) + 1);
  }

  function filterPlans(plans, filters = {}) {
    const terms = text(filters.query).trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    return plans.filter(plan => {
      const searchable = [plan.snapshot_id, plan.wiki, plan.plan_version, plan.status, plan.target_time, quarterLabel(plan)].join(' ').toLocaleLowerCase();
      return (!filters.wiki || plan.wiki === filters.wiki) && (!filters.status || plan.status === filters.status) && terms.every(term => searchable.includes(term));
    });
  }

  function workSummary(items) {
    return {complete: items.filter(item => ['complete', 'completed', 'verified', 'done'].includes(item.status)).length, total: items.length};
  }

  function normalizeManifest(input) {
    if (!object(input) || input.schema_version !== 1) throw new Error('不支持的 manifest schema_version（需要 1）');
    if (!object(input.project) || !object(input.inventory) || !Array.isArray(input.plans) || !Array.isArray(input.work_items)) {
      throw new Error('Manifest 缺少 project、inventory、plans 或 work_items');
    }
    return {
      schema_version: 1,
      generated_at: text(input.generated_at),
      project: {
        name: text(input.project.name), phase: text(input.project.phase), languages: strings(input.project.languages),
        storage_format: text(input.project.storage_format), processing_location_label: text(input.project.processing_location_label)
      },
      inventory: {
        file_count: count(input.inventory.file_count), total_bytes: count(input.inventory.total_bytes),
        source_set_count: count(input.inventory.source_set_count),
        hosts: Array.isArray(input.inventory.hosts) ? input.inventory.hosts.filter(object).map(host => ({
          label: text(host.label), status: text(host.status), file_count: count(host.file_count), errors: strings(host.errors)
        })) : []
      },
      plans: input.plans.filter(object).map(plan => ({
        snapshot_id: text(plan.snapshot_id), wiki: text(plan.wiki), target_time: text(plan.target_time),
        plan_version: text(plan.plan_version), status: text(plan.status),
        xml_source: normalizeSource(plan.xml_source), sql_source: normalizeSource(plan.sql_source), warnings: strings(plan.warnings)
      })),
      work_items: input.work_items.filter(object).map(item => ({id: text(item.id), title: text(item.title), status: text(item.status)})),
      metrics: object(input.metrics) ? Object.fromEntries([
        ['index_status', text(input.metrics.index_status)], ['index_verified_at', text(input.metrics.index_verified_at)],
        ['index_record_count', count(input.metrics.index_record_count)], ['index_total_count', count(input.metrics.index_total_count)]
      ].filter(([, value]) => value !== '' && value !== null)) : {}
    };
  }

  async function loadManifest({protocol, fetcher, scriptLoader}) {
    let input;
    let transport;
    if (protocol === 'file:') {
      input = await scriptLoader();
      transport = 'JS / file';
    } else {
      let response;
      try {
        response = await fetcher('data/project.json', {cache: 'no-store'});
      } catch (_) {
        response = null;
      }
      if (response && response.ok) {
        input = await response.json();
        transport = 'JSON / HTTP';
      } else {
        input = await scriptLoader();
        transport = 'JS / HTTP fallback';
      }
    }
    if (!input) throw new Error('尚未提供项目 manifest；未加载任何计划或结果。');
    return {data: normalizeManifest(input), transport};
  }

  function createDashboard(doc) {
    const get = id => doc.getElementById(id);
    const make = (tag, content, className) => {
      const element = doc.createElement(tag);
      if (content !== undefined) element.textContent = String(content);
      if (className) element.className = className;
      return element;
    };
    const put = (id, value) => {get(id).textContent = value;};
    const number = value => value === null || value === undefined ? '未知' : value.toLocaleString('en-US');
    const shown = value => value || '未提供';
    const statuses = {planned:'待执行',planning:'规划中',blocked:'受阻',unverified:'未验证',missing:'缺失',running:'声明运行中',complete:'声明完成',completed:'声明完成',verified:'已验证',ready:'就绪',deferred:'延后',failed:'失败',partial:'部分',unavailable:'不可用',indexed:'已索引',pending:'待处理',done:'声明完成'};
    const statusLabel = value => value ? (statuses[value] ? statuses[value] + ' / ' + value : value) : '未报告';
    const badge = value => {
      const span = make('span', statusLabel(value), 'badge');
      span.setAttribute('data-tone', ['complete','completed','verified','done'].includes(value) ? 'good' : ['blocked','failed','missing','unavailable'].includes(value) ? 'error' : ['unverified','partial','deferred'].includes(value) ? 'warning' : 'neutral');
      return span;
    };
    const controls = ['plan-search','language-filter','status-filter','clear-filters','plan-version','source-select'];
    let data = null, selected = -1, visible = [];
    get('source-select').value = 'xml_source';
    function disableControls(disabled) {controls.forEach(id => {get(id).disabled = disabled;});}
    function options(id, values, allLabel) {
      const select = get(id);select.replaceChildren();
      if (allLabel) {const option = make('option', allLabel);option.value = '';select.append(option);}
      values.forEach(value => {const option = make('option', value);option.value = value;select.append(option);});
      select.value = '';
    }
    function detailList(container, entries) {
      const dl = make('dl');
      entries.forEach(([label,value]) => {const row = make('div');row.append(make('dt',label),make('dd',value));dl.append(row);});
      container.replaceChildren(dl);
    }
    function emptyRow(message) {
      const row = make('tr'), cell = make('td',message,'empty-state');cell.setAttribute('colspan','4');row.append(cell);get('plan-rows').replaceChildren(row);
    }
    function renderSource() {
      const plan = data && data.plans[selected];
      const key = get('source-select').value === 'sql_source' ? 'sql_source' : 'xml_source';
      const source = plan && plan[key];
      if (!source) {put('source-detail','未选择来源。此来源尚未提供，不能据此构建快照。');return;}
      detailList(get('source-detail'),[
        ['Source ID',shown(source.id)],['来源日期',shown(source.date)],['Kind',shown(source.kind)],
        ['Offset / days',source.offset_days === null ? '未知' : (source.offset_days > 0 ? '+' : '') + source.offset_days + ' 天'],
        ['文件数',number(source.file_count)],['Coverage',shown(source.coverage)],['来源状态',statusLabel(source.status)]
      ]);
      get('source-detail').append(make('p',source.offset_days > 0 ? '注意：来源晚于目标时间。请审查时间泄漏风险；这不等于目标时点的精确还原。' : '偏移由 manifest 提供；文件数量不代表覆盖已验证。'));
    }
    function renderDetails() {
      const plan = data && data.plans[selected];
      if (!plan) {
        put('detail-heading','选择一个季度');put('selected-status','未选择');put('selected-id','尚无选中计划');put('selected-target','未提供');put('selected-wiki','未提供');
        options('plan-version',[],'未选择');get('plan-version').disabled = true;get('source-select').disabled = true;
        get('plan-warnings').replaceChildren(make('li','来源完整性尚未验证。'));renderSource();return;
      }
      put('detail-heading',quarterLabel(plan));put('selected-id',shown(plan.snapshot_id));
      get('selected-status').replaceChildren(badge(plan.status));get('selected-status').className = '';
      put('selected-target',shown(plan.target_time));put('selected-wiki',shown(plan.wiki));
      const versions = get('plan-version');versions.replaceChildren();
      data.plans.forEach((candidate,index) => {
        if (candidate.snapshot_id === plan.snapshot_id && candidate.wiki === plan.wiki) {
          const option = make('option',shown(candidate.plan_version) + ' · ' + statusLabel(candidate.status));option.value = String(index);versions.append(option);
        }
      });
      versions.value = String(selected);versions.disabled = false;get('source-select').disabled = false;
      put('selection-note',visible.includes(plan) ? '只读检查 · 不修改来源、不启动计算。' : '此版本不在当前筛选结果中 · 只读检查，不启动计算。');
      const warnings = plan.warnings.length ? plan.warnings : ['未报告额外警告；不代表来源完整或已经验证。'];
      get('plan-warnings').replaceChildren(...warnings.map(warning => make('li',warning)));renderSource();
    }
    function renderPlans(keepSelection = false, focusIndex = null) {
      if (!data) return;
      visible = filterPlans(data.plans,{query:get('plan-search').value,wiki:get('language-filter').value,status:get('status-filter').value});
      if (!keepSelection && !visible.includes(data.plans[selected])) selected = visible.length ? data.plans.indexOf(visible[0]) : -1;
      put('result-count',number(visible.length) + ' / ' + number(data.plans.length) + ' 条计划版本');get('plan-rows').replaceChildren();
      if (!visible.length) emptyRow(data.plans.length ? '没有匹配的季度计划。试试清除筛选。' : 'Manifest 尚无季度计划。没有执行结果可供推断。');
      visible.forEach(plan => {
        const index = data.plans.indexOf(plan), row = make('tr'), cell = make('td');row.setAttribute('data-selected',index === selected ? 'true' : 'false');
        const button = make('button',quarterLabel(plan),'plan-button');button.type = 'button';button.setAttribute('aria-pressed',index === selected ? 'true' : 'false');button.setAttribute('aria-controls','detail-panel');
        button.setAttribute('aria-label',[quarterLabel(plan),plan.wiki,plan.plan_version,'查看计划详情'].join(' '));button.append(make('span',shown(plan.snapshot_id),'plan-subtitle'));
        button.addEventListener('click',() => {selected = index;renderPlans(true,index);});cell.append(button);
        const stateCell = make('td');stateCell.append(badge(plan.status));row.append(cell,make('td',shown(plan.wiki),'mono'),make('td',shown(plan.plan_version),'mono'),stateCell);get('plan-rows').append(row);
        if (index === focusIndex) button.focus({preventScroll:true});
      });renderDetails();
    }
    function renderOverview() {
      put('project-name',data.project.name || '项目名称未提供');put('project-phase','阶段 / ' + statusLabel(data.project.phase));put('generated-at',data.generated_at || '未提供');put('file-count',number(data.inventory.file_count));
      const bytes = data.inventory.total_bytes;let size = '未知';
      if (bytes !== null) {const unit = bytes === 0 ? 0 : Math.min(Math.floor(Math.log(bytes) / Math.log(1024)),5);size = (bytes / Math.pow(1024,unit)).toLocaleString('en-US',{maximumFractionDigits:2}) + ' ' + ['B','KiB','MiB','GiB','TiB','PiB'][unit];}
      put('total-bytes',size);put('source-set-count','来源集 / ' + number(data.inventory.source_set_count));
      put('index-status',data.metrics.index_status ? statusLabel(data.metrics.index_status) : '未报告 / 未验证');
      put('index-count',data.metrics.index_record_count !== undefined ? '索引记录 / ' + number(data.metrics.index_record_count) + (data.metrics.index_total_count !== undefined ? ' / ' + number(data.metrics.index_total_count) : '') : '索引记录数量未提供');
      put('index-verified','索引验证时间 / ' + (data.metrics.index_verified_at || '未提供（不能视为已验证）'));
      put('storage-info','存储格式 / ' + shown(data.project.storage_format) + ' · 处理位置 / ' + shown(data.project.processing_location_label));
      put('host-count',data.inventory.hosts.length ? number(data.inventory.hosts.length) + ' 个来源标签' : '未报告来源');
      const hosts = data.inventory.hosts.map(host => {
        const item = make('li');item.append(make('span',shown(host.label),'mono'),badge(host.status),make('span','文件 / ' + number(host.file_count),'muted'));
        host.errors.forEach(error => item.append(make('span',error,'host-error')));return item;
      });get('host-list').replaceChildren(...(hosts.length ? hosts : [make('li','未报告来源状态；不代表所有来源可访问。')]));
      const summary = workSummary(data.work_items);
      put('work-count',summary.total ? summary.complete + ' / ' + summary.total : '未报告');put('work-summary',summary.total ? '已完成 ' + summary.complete + ' / ' + summary.total + ' 项声明工作' : '尚未报告工作项。');
      const progress = get('work-progress');progress.hidden = !summary.total;progress.max = summary.total || 1;progress.value = summary.complete;
      const items = data.work_items.map((item,index) => {
        const row = make('li'), title = make('span',shown(item.title),'work-title');title.append(make('small',shown(item.id)));row.append(make('span',String(index + 1).padStart(2,'0'),'work-step'),title,badge(item.status));return row;
      });get('work-items').replaceChildren(...(items.length ? items : [make('li','尚未提供工作计划。')]));
    }
    function setData(manifest,transport) {
      data = manifest;selected = data.plans.length ? 0 : -1;get('plan-search').value = '';
      options('language-filter',[...new Set([...data.project.languages,...data.plans.map(plan => plan.wiki)])].filter(Boolean).sort(),'全部语言');
      options('status-filter',[...new Set(data.plans.map(plan => plan.status))].filter(Boolean).sort(),'全部状态');disableControls(false);get('source-select').value = 'xml_source';
      put('load-transport',transport || '未提供读取方式');put('load-state','已加载项目清单 · ' + number(data.plans.length) + ' 条计划版本 · 非图谱构建完成声明');get('load-state').setAttribute('data-state','ready');renderOverview();renderPlans();
    }
    function reset() {
      data = null;selected = -1;visible = [];disableControls(true);get('plan-search').value = '';options('language-filter',[],'全部语言');options('status-filter',[],'全部状态');
      const defaults = {'project-name':'Wikipedia Historical Network','project-phase':'阶段未报告','generated-at':'未提供','file-count':'未知','total-bytes':'未知','source-set-count':'来源集数量未提供','index-status':'未报告 / 未验证','index-count':'索引记录数量未提供','index-verified':'索引验证时间未提供。','work-count':'未报告','work-summary':'尚未报告工作项。','host-count':'未报告来源','storage-info':'存储格式与处理位置未提供。','result-count':'计划尚未加载','load-transport':'未加载','selection-note':'此处只读检查，不修改来源、不启动计算。'};
      Object.entries(defaults).forEach(([id,value]) => put(id,value));get('work-progress').hidden = true;get('work-items').replaceChildren(make('li','等待工作计划。'));get('host-list').replaceChildren(make('li','未报告来源状态。'));emptyRow('尚未加载项目 manifest。不会使用演示数据填充。');renderDetails();
    }
    function showError(message) {reset();put('load-state','数据未加载 / ' + message + ' 请检查 data/project.json 或可信的 data/project.js。');get('load-state').setAttribute('data-state','error');}
    function showLoading() {reset();put('load-state','正在读取项目 manifest…');get('load-state').setAttribute('data-state','loading');}
    get('plan-search').addEventListener('input',() => renderPlans());['language-filter','status-filter'].forEach(id => get(id).addEventListener('change',() => renderPlans()));
    get('clear-filters').addEventListener('click',() => {['plan-search','language-filter','status-filter'].forEach(id => {get(id).value = '';});renderPlans();});
    get('plan-version').addEventListener('change',() => {const index = Number(get('plan-version').value);if (data && Number.isInteger(index) && data.plans[index]) {selected = index;renderPlans(true);}});
    get('source-select').addEventListener('change',renderSource);return {setData,showError,showLoading};
  }

  function loadLocalScript() {
    return new Promise((resolve,reject) => {
      if (root.WHN_DATA !== undefined) delete root.WHN_DATA;
      const script = document.createElement('script');script.src = 'data/project.js';
      script.onload = () => {const data = root.WHN_DATA;script.remove();resolve(data);};script.onerror = () => {script.remove();reject(new Error('项目数据文件不可用。'));};document.head.append(script);
    });
  }
  function boot() {
    const ui = createDashboard(document), reload = document.getElementById('reload-data');
    const refresh = async () => {
      reload.disabled = true;ui.showLoading();
      try {const result = await loadManifest({protocol:root.location.protocol,fetcher:root.fetch && root.fetch.bind(root),scriptLoader:loadLocalScript});ui.setData(result.data,result.transport);}
      catch (error) {ui.showError(error instanceof SyntaxError ? 'JSON 格式无效；未采用备用数据掩盖错误。' : (error.message || '读取失败。'));}
      finally {reload.disabled = false;}
    };reload.addEventListener('click',refresh);refresh();
  }

  const api = {normalizeManifest,normalizeSource,quarterLabel,filterPlans,workSummary,loadManifest,createDashboard};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.WHN_Dashboard = api;
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',boot,{once:true});
    else boot();
  }
})(typeof window !== 'undefined' ? window : globalThis);
