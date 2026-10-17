'use strict';

const state = { snapshot: null, page: 'overview', selectedRecord: null, recordHash: null, busy: false, timer: null, recordRequest: 0, recordController: null };
const pages = {
  overview: ['Overview', 'What is happening.', 'Current progress, missing proof, and the next recorded step.'],
  work: ['Current work', 'The next steps are visible.', 'Recorded plans and observed file changes. Running work stays separate.'],
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
  const runtime = surface('Running work', 'OBSERVATION LIMIT');
  runtime.append(node('h3', data.runtime.status), node('p', data.runtime.note, 'muted'), node('p', 'A file change is not proof that an agent or test is running.', 'muted small'));
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
document.getElementById('refresh').addEventListener('click', refresh);
document.getElementById('record-search').addEventListener('input', renderRecordList);
document.addEventListener('visibilitychange', () => { clearTimeout(state.timer); if (!document.hidden) refresh(); });
changePage(location.hash.slice(1));
refresh();
