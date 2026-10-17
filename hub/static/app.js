'use strict';

const state = { snapshot: null, page: 'overview', selectedRecord: null, recordHash: null, busy: false, timer: null, recordRequest: 0, recordController: null };
const liveState = { data: null, busy: false, timer: null, stale: false, stage: 'data' };
const pages = {
  overview: ['Overview', 'What is happening.', 'Current progress, missing proof, and the next recorded step.'],
  work: ['Current work', 'See work as it happens.', 'Live agent signals and actual project processes, with their observation times.'],
  loop: ['Whole loop', 'Follow the whole loop.', 'Data to research, evaluation, paper operation, and feedback. Every stage keeps its evidence separate.'],
  results: ['Results', 'What the checks establish.', 'Exact recorded results, with separate environments and original sources.'],
  map: ['Project map', 'See how the project connects.', 'Milestones, their requirements, and the full horizontal project map.'],
  records: ['Source records', 'Read the actual evidence.', 'Checkpoints, plans, and reports from this working folder.']
};

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = String(text);
  if (className) element.className = className;
  return element;
}
function time(value) {
  if (!value) return 'Time unavailable';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Time unavailable';
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit', timeZone: 'America/New_York', timeZoneName: 'short' }).format(date);
}
function showNumber(value) { return value === null || value === undefined ? 'Unavailable' : value.toLocaleString('en-US'); }
function button(text, action, className = 'text-button') {
  const element = node('button', text, className);
  element.type = 'button'; element.addEventListener('click', action); return element;
}
function sourceLink(path, label) { return button(label || path, () => openRecord(path)); }
function surface(title, label) {
  const element = node('article', null, 'surface');
  if (label) element.append(node('p', label, 'eyebrow'));
  if (title) element.append(node('h2', title));
  return element;
}
function keyRow(label, value) {
  const row = node('div', null, 'key-row'); row.append(node('span', label), node('strong', value)); return row;
}
function provenance(record, label = 'Source') {
  const element = node('div', null, 'provenance');
  element.append(document.createTextNode(`${label}: `), sourceLink(record.path), node('div', `File changed ${time(record.modified_at)}`));
  return element;
}
function changePage(page) {
  if (!pages[page]) page = 'overview';
  state.page = page;
  Object.keys(pages).forEach(key => { document.getElementById(`${key}-page`).hidden = key !== page; });
  document.querySelectorAll('nav [data-page]').forEach(item => {
    if (item.dataset.page === page) item.setAttribute('aria-current', 'page'); else item.removeAttribute('aria-current');
  });
  const [name, title, description] = pages[page];
  document.getElementById('page-name').textContent = name;
  document.getElementById('page-title').textContent = title;
  document.getElementById('page-description').textContent = description;
  history.replaceState(null, '', `#${page}`);
}

function renderOverview(data) {
  const parent = document.getElementById('overview-page'); parent.replaceChildren();
  const columns = node('div', null, 'columns');
  const focus = surface(null); focus.classList.add('focus-card');
  const label = node('div', null, 'section-label'); label.append(node('p', 'LATEST RECORDED CHECKPOINT', 'eyebrow'), node('span', 'SAVED RECORD', 'pill'));
  focus.append(label, node('h2', data.checkpoint.summary));
  if (data.checkpoint.status !== 'available') focus.append(node('p', `The checkpoint is ${data.checkpoint.status.replaceAll('_', ' ')}. Current progress cannot be established.`, 'muted'));
  else focus.append(node('p', data.checkpoint.heading, 'muted small'));
  const next = node('div', null, 'next-step'); next.append(node('h3', 'Next recorded action'));
  if (data.next_steps.length) data.next_steps.forEach(text => next.append(node('p', text)));
  else next.append(node('p', 'No next action was found in the current section.', 'muted'));
  data.related_records.forEach(path => next.append(sourceLink(path)));
  focus.append(node('div', null, 'line-divider'), next, provenance(data.checkpoint));
  const status = surface('Where the project stands', 'ACCEPTANCE');
  const accepted = data.milestones.filter(item => item.status === 'Accepted').map(item => item.id);
  status.append(keyRow('Fully accepted', accepted.length ? accepted.join(', ') : 'Unavailable'));
  status.append(keyRow('Actual supervised sessions', data.sessions.completed === null ? 'Unavailable' : `${data.sessions.completed} of ${data.sessions.required}`));
  status.append(keyRow('Research runtime', data.runtime.status));
  status.append(node('p', data.runtime.note, 'muted small'));
  status.append(sourceLink('docs/BUILD_SPEC.md', 'Read the acceptance requirements'));
  columns.append(focus, status); parent.append(columns);
  const gap = surface('What still needs proof', 'OPEN REQUIREMENTS'); gap.classList.add('below');
  const list = node('ul', null, 'gap-list');
  if (data.gaps.length) data.gaps.forEach(text => list.append(node('li', text)));
  else list.append(node('li', 'No open requirements were extracted. Read the current checkpoint before drawing a conclusion.'));
  gap.append(list); parent.append(gap);
  const recent = surface(null); recent.classList.add('below');
  const heading = node('div', null, 'records-heading'); heading.append(node('h2', 'Recently changed records'), button('All source records →', () => changePage('records'))); recent.append(heading);
  const entries = [...data.catalogue.entries].filter(item => item.modified_at).sort((a, b) => b.modified_at.localeCompare(a.modified_at)).slice(0, 5);
  entries.forEach(item => {
    const row = node('div', null, 'record-row'); row.append(sourceLink(item.path), node('span', time(item.modified_at), 'record-meta')); recent.append(row);
  });
  recent.append(node('p', 'These are file modification times. They do not establish when a check passed.', 'muted small')); parent.append(recent);
}

function renderWork(data) {
  const parent = document.getElementById('work-page'); parent.replaceChildren();
  const columns = node('div', null, 'columns');
  const plan = surface('Next recorded actions', 'PLAN');
  data.next_steps.forEach(text => plan.append(node('p', text)));
  if (!data.next_steps.length) plan.append(node('p', 'No next action is recorded in the current section.', 'muted'));
  const links = node('div', null, 'record-links'); data.related_records.forEach(path => links.append(sourceLink(path))); plan.append(links, provenance(data.checkpoint));
  const runtime = surface('Operational runtime', 'STAGE REPORTING');
  runtime.append(node('h3', data.runtime.status), node('p', data.runtime.note, 'muted'), button('See whole-loop observations →', () => changePage('loop')));
  columns.append(plan, runtime); parent.append(columns);
  const files = surface('Changes in the working folder', 'READ-ONLY GIT OBSERVATION'); files.classList.add('below');
  files.append(node('p', data.work.note, 'muted small'));
  if (!data.work.available) files.append(node('p', 'Git observations are unavailable. The document view remains available.', 'empty'));
  else if (!data.work.changes.length) files.append(node('p', 'No visible source changes were reported.', 'empty'));
  else {
    const list = node('ul', null, 'file-list');
    data.work.changes.forEach(item => { const row = node('li'); row.append(node('code', item.path), node('span', item.status)); list.append(row); });
    files.append(list);
  }
  if (data.work.omitted) files.append(node('p', `${data.work.omitted} further changes are omitted by the display limit.`, 'muted small'));
  parent.append(files);
  const livePanel = node('div'); livePanel.id = 'work-live-panel'; parent.prepend(livePanel);
  if (liveState.data) renderLiveActivity(liveState.data);
}

function activityCards(data) {
  const parent = node('div');
  const grid = node('div', null, 'stats-pair');
  const agents = surface('Agents', 'LIVE ACTIVITY EVENTS');
  if (!data.agents.length) agents.append(node('p', data.coverage.agents === 'Unavailable' ? 'The agent event source is unavailable.' : 'No project agent was found within the bounded discovery window.', 'muted'));
  data.agents.filter(agent => agent.last_signal && agent.age_seconds < 86400).slice(0, 8).forEach(agent => {
    const row = node('div', null, 'activity-row');
    row.append(node('div', `Agent ${agent.id.slice(0, 8)}`, 'activity-name'), node('strong', agent.state), node('p', agent.activity, 'muted small'), node('small', `Last signal ${time(agent.last_signal)} · ${agent.pending_tools} pending tools`));
    if (agent.history_partial) row.append(node('small', 'Older events are outside the read window.'));
    agents.append(row);
  });
  agents.append(node('p', `Agent coverage: ${data.coverage.agents}. Signals older than ${data.stale_after_seconds} seconds cannot establish current work.`, 'muted small'));
  const processes = surface('Project processes', 'NATIVE WINDOWS OBSERVATION');
  if (!data.processes.length) processes.append(node('p', 'No accessible project work process is currently observed.', 'muted'));
  [...data.processes].sort((a,b) => Number(b.kind === 'test') - Number(a.kind === 'test') || b.started_at.localeCompare(a.started_at)).forEach(process => {
    const row = node('div', null, 'activity-row');
    row.append(node('div', process.label, 'activity-name'), node('strong', `Process ${process.pid} · ${process.program}`), node('p', `Started ${time(process.started_at)}`, 'muted small'));
    processes.append(row);
  });
  processes.append(node('p', `Coverage: ${data.coverage.processes}. Unreadable candidate processes: ${data.coverage.unreadable_processes}.`, 'muted small'));
  processes.append(node('p', 'A process disappearing does not prove that its work passed.', 'muted small'));
  grid.append(agents, processes); parent.append(grid);
  const jobs = surface('Reported jobs', 'EXPLICIT JOB RECEIPTS'); jobs.classList.add('below');
  if (!data.jobs.length) jobs.append(node('p', 'No explicit job receipt is connected. Unwrapped test processes are still observed above.', 'muted'));
  data.jobs.slice(0, 12).forEach(job => {
    const row = node('div', null, 'activity-row');
    row.append(node('div', `${job.stage.replaceAll('_', ' ')} · ${job.kind}`, 'activity-name'), node('strong', job.state), node('p', `Job ${job.run_id.slice(0, 8)} · process ${job.pid}${job.exit_code === null ? '' : ` · exit code ${job.exit_code}`}`, 'muted small'), node('small', `Started ${time(job.started_at)} · observed ${time(job.observed_at)}`));
    if (job.finished_at) row.append(node('small', `Finished ${time(job.finished_at)}`));
    jobs.append(row);
  });
  parent.append(jobs);
  const events = surface('Recent activity', 'OBSERVED EVENTS'); events.classList.add('below');
  if (!data.events.length) events.append(node('p', 'No current activity events have been observed.', 'muted'));
  data.events.slice(0, 18).forEach(event => {
    const row = node('div', null, 'event-row');
    const label = event.exit_code === undefined ? event.label : `${event.label} · exit code ${event.exit_code}`;
    row.append(node('span', label), node('small', `${event.agent_id ? `Agent ${event.agent_id.slice(0, 8)} · ` : ''}${time(event.at)}`));
    events.append(row);
  });
  events.append(node('p', 'Command exit codes are observations. They do not grant milestone or financial acceptance.', 'muted small'));
  parent.append(events); return parent;
}

function renderLiveActivity(data) {
  const target = document.getElementById('work-live-panel');
  if (target) target.replaceChildren(activityCards(data));
  const overview = document.getElementById('overview-page');
  let summary = document.getElementById('overview-live-summary');
  if (!summary) { summary = surface('Happening now', 'LIVE OBSERVATIONS'); summary.id = 'overview-live-summary'; overview.prepend(summary); }
  const active = data.agents.filter(agent => ['Working', 'Recent activity'].includes(agent.state));
  summary.replaceChildren(node('p', 'LIVE OBSERVATIONS', 'eyebrow'), node('h2', 'Happening now'), node('p', `${active.length} agents with current signals · ${data.processes.filter(row => row.kind === 'test').length} test processes · ${data.processes.length} observed project processes`), button('See current work →', () => changePage('work')));
  renderWholeLoop(data);
}

function renderWholeLoop(data) {
  const parent = document.getElementById('loop-page'); parent.replaceChildren();
  const status = surface('Current observation coverage');
  status.append(node('p', `Agent events: ${data.coverage.agents}. Project processes: ${data.coverage.processes}.`, 'muted'));
  status.append(node('p', 'Operational stages need their own job events. A stage without a current event stays Not observed.', 'muted small'));
  parent.append(status);
  const viewport = node('div', null, 'loop-viewport');
  const track = node('div', null, 'whole-loop-track');
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 1000 460'); svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('preserveAspectRatio', 'none');
  const byId = new Map(data.loop.stages.map(stage => [stage.id, stage]));
  const defs = document.createElementNS(svg.namespaceURI, 'defs');
  const marker = document.createElementNS(svg.namespaceURI, 'marker'); marker.id = 'loop-arrow';
  for (const [key,value] of Object.entries({viewBox:'0 0 10 10',refX:'9',refY:'5',markerWidth:'5',markerHeight:'5',orient:'auto-start-reverse'})) marker.setAttribute(key,value);
  const tip = document.createElementNS(svg.namespaceURI, 'path'); tip.setAttribute('d','M 0 0 L 10 5 L 0 10 z'); marker.append(tip); defs.append(marker); svg.append(defs);
  for (const edge of data.loop.connections) {
    const a = byId.get(edge.from), b = byId.get(edge.to); if (!a || !b) continue;
    const ax = 80 + a.column * 164, ay = 20 + a.row * 160, bx = 80 + b.column * 164, by = 20 + b.row * 160;
    let path;
    if (a.row === b.row && Math.abs(a.column - b.column) === 1) {
      const direction = b.column > a.column ? 1 : -1;
      path = `M ${ax + direction*72} ${ay+48} L ${bx-direction*72} ${by+48}`;
    } else if (a.row === b.row) {
      path = `M ${ax} ${ay+96} V ${ay+112} H ${bx} V ${by+96}`;
    } else {
      const down = b.row > a.row, fromY = ay+(down?96:0), toY = by+(down?0:96), mid = (fromY+toY)/2;
      path = `M ${ax} ${fromY} V ${mid} H ${bx} V ${toY}`;
    }
    const line = document.createElementNS(svg.namespaceURI, 'path'); line.setAttribute('d',path);
    line.setAttribute('marker-end','url(#loop-arrow)');
    if (edge.state === 'Connection unfinished') line.setAttribute('stroke-dasharray','5 4'); svg.append(line);
  }
  track.append(svg);
  const detail = surface(null); detail.classList.add('below');
  function choose(stage, control) {
    liveState.stage = stage.id;
    track.querySelectorAll('button').forEach(item => item.setAttribute('aria-pressed', String(item === control)));
    detail.replaceChildren(node('p', stage.state.toUpperCase(), 'eyebrow'), node('h2', stage.name), node('p', stage.description), keyRow('Reporting', stage.reporting), node('p', stage.source, 'muted small'), sourceLink('docs/BUILD_SPEC.md', 'Read the governing specification'));
    stage.activities.forEach(job => detail.append(keyRow(`Job ${job.run_id.slice(0, 8)}`, `${job.state}${job.exit_code === null ? '' : ` · exit code ${job.exit_code}`}`), node('p', `Observed ${time(job.observed_at)}${job.finished_at ? ` · finished ${time(job.finished_at)}` : ''}`, 'muted small')));
  }
  data.loop.stages.forEach((stage, index) => {
    const control = button('', () => choose(stage, control), 'loop-stage'); control.setAttribute('aria-pressed', 'false');
    control.dataset.stage = stage.id;
    control.style.left = `${(8+stage.column*164)/10}%`; control.style.top = `${20+stage.row*160}px`;
    control.append(node('small', String(index + 1).padStart(2, '0')), node('strong', stage.name), node('span', stage.state));
    track.append(control);
  });
  viewport.append(track); parent.append(viewport, node('p', 'Arrows show the required route. Dashed arrows mark unfinished connections. Select any stage for its exact observation.', 'map-direction'), detail);
  if (data.loop.stages.length) {
    const index = Math.max(0, data.loop.stages.findIndex(stage => stage.id === liveState.stage));
    choose(data.loop.stages[index], track.querySelectorAll('button')[index]);
  }
  const connections = surface('Return paths and unfinished connections'); connections.classList.add('below');
  data.loop.connections.filter(edge => ['feedback', 'reconciliation'].includes(edge.from) || edge.from === 'proposals').forEach(edge => connections.append(keyRow(`${edge.from.replaceAll('_', ' ')} → ${edge.to.replaceAll('_', ' ')}`, edge.state)));
  connections.append(node('p', data.loop.note, 'muted small')); parent.append(connections);
  const engineering = surface('Engineering activity beside the loop'); engineering.classList.add('below');
  engineering.append(node('p', 'Agent edits and tests remain separate from an operational research or paper session.', 'muted'));
  engineering.append(node('p', `${data.loop.engineering.length} current engineering processes.`, 'muted small'), button('View live agent and test activity →', () => changePage('work'))); parent.append(engineering);
}

async function refreshLive() {
  if (liveState.busy || document.hidden) return;
  liveState.busy = true;
  const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const data = await readJSON('/api/live', controller.signal); liveState.data = data; liveState.stale = false;
    renderLiveActivity(data);
    document.getElementById('live-state').textContent = 'Live activity connected · refreshes every 2 seconds';
    document.getElementById('live-time').textContent = `Observed ${time(data.observed_at)}`;
    document.getElementById('live-error').hidden = true;
  } catch (error) {
    liveState.stale = true;
    document.getElementById('live-state').textContent = 'Live activity connection lost · retained observations are stale';
    const notice = document.getElementById('live-error'); notice.hidden = false;
    notice.textContent = 'Current agent and process activity cannot be confirmed. Retained observations below are stale.';
  } finally {
    clearTimeout(timeout); liveState.busy = false; clearTimeout(liveState.timer);
    if (!document.hidden) liveState.timer = setTimeout(refreshLive, 2000);
  }
}

function renderResults(data) {
  const parent = document.getElementById('results-page'); parent.replaceChildren();
  const pair = node('div', null, 'stats-pair');
  for (const [key, title] of [['source', 'Source checks'], ['installed', 'Installed-package checks']]) {
    const result = data.results[key], card = surface(title, 'CURRENT CHECKPOINT');
    card.append(node('div', showNumber(result.passed), 'big-number'), node('div', result.passed === null ? 'Passing count is unavailable' : 'distinct cases passed', 'result-label'));
    const counts = node('div', null, 'counts');
    for (const [field, label] of [['failed', 'failed'], ['errors', 'errors'], ['skipped', 'skipped']]) {
      const value = node('span'); value.append(node('b', showNumber(result[field])), document.createTextNode(` ${label}`)); counts.append(value);
    }
    card.append(counts); pair.append(card);
  }
  parent.append(pair, node('p', data.results.note, 'muted small'));
  const scope = surface('What these results cover', 'EVIDENCE SCOPE'); scope.classList.add('below');
  scope.append(keyRow('In-process cases per environment', showNumber(data.results.in_process)), keyRow('Native Windows stages per environment', showNumber(data.results.native_per_environment)));
  scope.append(node('p', 'Native Windows checks test actual Windows behavior. In-process checks run within a single program. Read the report for simulated inputs and remaining limits.', 'muted small'));
  scope.append(node('p', 'The Hub does not add overlapping counts or use these results to approve a milestone.', 'muted small'));
  const details = node('details'); details.append(node('summary', 'Read the current checkpoint excerpt'), node('pre', data.checkpoint.text)); scope.append(details, provenance(data.checkpoint));
  parent.append(scope);
}

function renderMap(data) {
  const parent = document.getElementById('map-page'); parent.replaceChildren();
  parent.append(node('p', 'Read left to right. Select a milestone to see its original requirements.', 'map-direction'));
  const track = node('div', null, 'map-track'); track.setAttribute('aria-label', 'Milestones from foundations to supervised operation');
  const detail = surface(null);
  function choose(item, selected) {
    track.querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', String(button === selected)));
    detail.replaceChildren(node('p', item.status.toUpperCase(), 'eyebrow'), node('h2', `${item.id}: ${item.name}`), node('h3', 'Required evidence'), node('p', item.requirements), node('h3', 'Required failure checks'), node('p', item.failure_checks), sourceLink(item.source, 'Read the full build specification'));
  }
  data.milestones.forEach(item => {
    const control = button('', () => choose(item, control), 'map-node');
    control.setAttribute('aria-pressed', 'false');
    control.append(node('strong', item.id), node('span', item.name, 'map-name'), node('span', item.status, 'map-state')); track.append(control);
  });
  parent.append(track, detail);
  const selected = data.milestones.find(item => item.id === 'M5') || data.milestones[0];
  if (selected) choose(selected, track.children[data.milestones.indexOf(selected)]);
  else detail.append(node('p', 'The build specification is unavailable.', 'empty'));
  const pdf = surface('Full horizontal project map', 'ARCHITECTURE'); pdf.classList.add('below');
  pdf.append(node('p', 'Open the saved PDF for the whole system, research loop, data, evaluation, paper operations, safety, and recovery.', 'muted'));
  if (data.map.available) {
    const link = node('a', 'Open project-map PDF ↗', 'button secondary'); link.href = data.map.url; link.target = '_blank'; link.rel = 'noopener'; pdf.append(link, node('p', `Map file changed ${time(data.map.modified_at)}`, 'muted small'));
  } else pdf.append(node('p', 'The saved PDF is unavailable at its recorded location.', 'empty'));
  pdf.append(sourceLink('docs/PROJECT_MAP_REFRESH.md', 'Read the map source and refresh instructions')); parent.append(pdf);
}

function renderRecordList() {
  if (!state.snapshot) return;
  const parent = document.getElementById('record-list'); parent.replaceChildren();
  const search = document.getElementById('record-search').value.trim().toLowerCase();
  const entries = state.snapshot.catalogue.entries.filter(item => item.path.toLowerCase().includes(search)).sort((a, b) => (b.modified_at || '').localeCompare(a.modified_at || '') || a.path.localeCompare(b.path));
  document.getElementById('catalogue-note').textContent = `${entries.length} matching records. ${state.snapshot.catalogue.omitted ? `${state.snapshot.catalogue.omitted} records omitted by the read limit.` : ''} ${state.snapshot.catalogue.git_available ? '' : 'Git catalogue unavailable; showing named core records.'}`;
  if (!entries.length) parent.append(node('p', 'No matching project records.', 'empty'));
  entries.forEach(item => {
    const choice = button('', () => openRecord(item.path), 'record-choice'); choice.setAttribute('aria-pressed', String(item.path === state.selectedRecord));
    choice.append(document.createTextNode(item.path), node('small', `${item.kind} · ${item.status === 'available' ? time(item.modified_at) : item.status}`)); parent.append(choice);
  });
}

async function readJSON(path, signal) {
  const reply = await fetch(path, { cache: 'no-store', signal });
  if (!reply.ok) throw new Error(`Read failed (${reply.status}).`);
  return reply.json();
}

async function openRecord(path, background = false) {
  const request = ++state.recordRequest;
  if (state.recordController) state.recordController.abort();
  const controller = new AbortController(); state.recordController = controller;
  const timeout = setTimeout(() => controller.abort(), 8000);
  state.selectedRecord = path;
  if (!background) changePage('records');
  renderRecordList();
  const heading = document.getElementById('record-heading'), content = document.getElementById('record-text');
  if (!background) { heading.replaceChildren(node('h2', path), node('p', 'Reading the source record…', 'muted')); content.textContent = ''; }
  try {
    const record = await readJSON(`/api/record?path=${encodeURIComponent(path)}`, controller.signal);
    if (request !== state.recordRequest) return;
    heading.replaceChildren(node('h2', record.path));
    if (record.status !== 'available') {
      heading.append(node('p', `This record is ${record.status.replaceAll('_', ' ')}. No source text is available.`, 'muted')); content.textContent = ''; state.recordHash = null;
    } else {
      heading.append(node('p', `File changed ${time(record.modified_at)} · ${record.bytes.toLocaleString('en-US')} bytes`, 'muted small'), node('p', `SHA-256 content fingerprint: ${record.sha256}`, 'fingerprint'));
      if (state.recordHash !== record.sha256 || !background) content.textContent = record.text;
      state.recordHash = record.sha256;
    }
  } catch (error) {
    if (request !== state.recordRequest) return;
    heading.replaceChildren(node('h2', path), node('p', 'The source could not be refreshed. Any retained text below is stale. Retry when the Hub is available.', 'muted'));
  } finally { clearTimeout(timeout); }
}

async function refresh() {
  if (state.busy) return;
  state.busy = true; document.getElementById('refresh').disabled = true;
  const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const data = await readJSON('/api/snapshot', controller.signal);
    state.snapshot = data;
    renderOverview(data); renderWork(data); renderResults(data); renderMap(data); renderRecordList();
    if (liveState.data) renderLiveActivity(liveState.data);
    const status = document.getElementById('connection-state'); status.textContent = 'Connected to saved project records'; status.dataset.state = 'connected';
    document.getElementById('last-read').textContent = `Records checked ${time(data.read_at)}`;
    document.getElementById('connection-error').hidden = true;
    if (state.selectedRecord && state.page === 'records') await openRecord(state.selectedRecord, true);
  } catch (error) {
    const status = document.getElementById('connection-state'); status.textContent = state.snapshot ? 'Connection lost · displayed records are stale' : 'Project records unavailable'; status.dataset.state = 'stale';
    const notice = document.getElementById('connection-error'); notice.hidden = false; notice.textContent = 'The Hub could not read the project records. Check that its terminal is still open, then refresh.';
    if (!state.snapshot) Object.keys(pages).filter(key => key !== 'records').forEach(key => { document.getElementById(`${key}-page`).replaceChildren(node('p', 'No current project records are available.', 'empty')); });
  } finally {
    clearTimeout(timeout); state.busy = false; document.getElementById('refresh').disabled = false;
    clearTimeout(state.timer);
    if (!document.hidden) state.timer = setTimeout(refresh, 10000);
  }
}

document.querySelectorAll('nav [data-page]').forEach(item => item.addEventListener('click', () => changePage(item.dataset.page)));
document.getElementById('refresh').addEventListener('click', () => { refresh(); refreshLive(); });
document.getElementById('record-search').addEventListener('input', renderRecordList);
document.addEventListener('visibilitychange', () => { clearTimeout(state.timer); clearTimeout(liveState.timer); if (!document.hidden) { refresh(); refreshLive(); } });
changePage(location.hash.slice(1));
refresh();
refreshLive();
