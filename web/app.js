'use strict';

const $ = id => document.getElementById(id);
const STORE_PROJECT = 'griddrawer.project';
const STORE_BUILT = 'griddrawer.built';
const RULER = 38; // px, width of the y ruler

let project = emptyProject();
let scale = 1;
// Signatures say what a build or arrangement depends on, so that reordering boxes
// (which changes neither) does not mark them out of date.
let buildSig = '';      // unique sizes + box parameters of the current project
let arrangeSig = '';    // the same plus how many of each size
let builtSig = null;    // buildSig the current STL build was made from
let arrangedSig = null; // arrangeSig the current arrangement was made from
let arrangement = null;
let tools = { openscad: { found: false }, prusaslicer: { found: false } };
let hasErrors = false;
let busy = null;        // 'build' | 'arrange' | 'slice' | null
let editingColumn = null;
let addingBoxesToColumn = null;

// ---------- helpers ----------

function emptyProject() {
  return {
    version: 1,
    drawer: { width: 580, depth: 580 },
    defaults: { height: 40, wall: 2, r: 4, cover_width: 32, cover_width_short: 28, short_depth_below: 45 },
    columns: [],
  };
}

const fmt = value => String(Math.round(value * 1000) / 1000);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const plural = (count, word) => `${count} ${word}${count === 1 ? '' : (word.endsWith('x') ? 'es' : 's')}`;
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));

function describeError(detail) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(item => item.msg || JSON.stringify(item)).join(' ');
  return 'Request failed.';
}

async function api(path, body, method = 'POST') {
  const options = body === undefined ? {} : {
    method, headers: { 'content-type': 'application/json' }, body: JSON.stringify(body),
  };
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(describeError(data.detail));
  return data;
}

function store(key, value) {
  try { localStorage.setItem(key, value); } catch { /* private mode or full: autosave is optional */ }
}
function stored(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

// One stable hue per unique box size, shared by the drawer and the bed views.
const hues = new Map();
function hueFor(key) {
  if (!hues.has(key)) hues.set(key, Math.round((210 + hues.size * 137.508) % 360));
  return hues.get(key);
}

const expandedBoxes = column => column.boxes.flatMap(row => Array(row.qty).fill(row.depth));
const usedDepth = column => column.boxes.reduce((sum, row) => sum + row.depth * row.qty, 0);
const usedWidth = () => project.columns.reduce((sum, column) => sum + column.width, 0);
function regroupBoxes(depths) {
  const rows = [];
  for (const depth of depths) {
    const last = rows[rows.length - 1];
    if (last && last.depth === depth) last.qty++;
    else rows.push({ depth, qty: 1 });
  }
  return rows;
}

// ---------- project changes ----------

function updateSignatures() {
  const counts = {};
  for (const column of project.columns) {
    for (const row of column.boxes) {
      const key = `${fmt(row.depth)}X${fmt(column.width)}`;
      counts[key] = (counts[key] || 0) + row.qty;
    }
  }
  const keys = Object.keys(counts).sort();
  const defaults = JSON.stringify(project.defaults);
  buildSig = `${defaults}|${keys.join(',')}`;
  arrangeSig = `${defaults}|${keys.map(key => `${key}*${counts[key]}`).join(',')}`;
}

function changed() {
  updateSignatures();
  store(STORE_PROJECT, JSON.stringify(project));
  render();
  scheduleValidate();
  for (const id of ['buildNote', 'arrangeNote', 'sliceNote']) $(id).classList.remove('error'); // old outcomes no longer apply
  updateSteps();
}

function setProject(next) {
  project = next;
  hues.clear();
  changed();
}

function removeBox(columnIndex, index) {
  const depths = expandedBoxes(project.columns[columnIndex]);
  depths.splice(index, 1);
  project.columns[columnIndex].boxes = regroupBoxes(depths);
  changed();
}

function moveBox(columnIndex, from, to) {
  const depths = expandedBoxes(project.columns[columnIndex]);
  if (from === to || to < 0 || to >= depths.length) return false;
  depths.splice(to, 0, depths.splice(from, 1)[0]);
  project.columns[columnIndex].boxes = regroupBoxes(depths);
  changed();
  return true;
}

function deleteColumn(index) {
  project.columns.splice(index, 1);
  project.columns.forEach((column, i) => { column.name = `Col ${i + 1}`; });
  changed();
}

// ---------- drawer preview ----------

function computeScale() {
  const d = project.drawer;
  const availableWidth = $('previewFrame').clientWidth - RULER - 8;
  const availableHeight = innerHeight - 230;
  return Math.min(1.6, Math.max(0.35, Math.min(availableWidth / d.width, availableHeight / d.depth)));
}

function make(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function render() {
  const d = project.drawer, defs = project.defaults;
  $('drawerWidth').value = d.width; $('drawerDepth').value = d.depth;
  $('height').value = defs.height; $('wall').value = defs.wall; $('radius').value = defs.r;

  scale = computeScale();
  const canvas = $('canvas'), heads = $('columnHeads');
  canvas.style.width = `${d.width * scale}px`;
  canvas.style.height = `${d.depth * scale}px`;
  heads.style.width = `${d.width * scale}px`;

  const body = document.createDocumentFragment(), head = document.createDocumentFragment();
  const sizes = new Set();
  let x = 0, total = 0;

  project.columns.forEach((column, ci) => {
    const left = `${x * scale}px`, width = `${column.width * scale}px`;
    const name = escapeHtml(column.name);

    const title = make('div', 'column-head');
    title.style.left = left; title.style.width = width;
    title.innerHTML =
      `<button class="column-title" type="button" data-action="edit-column" data-column="${ci}" title="Edit ${name}">` +
      `<b>${name}</b><small>${fmt(column.width)} mm</small></button>` +
      `<button class="icon" type="button" data-action="add-box" data-column="${ci}" title="Add boxes to ${name}" aria-label="Add boxes to ${name}">+</button>` +
      `<button class="icon danger" type="button" data-action="delete-column" data-column="${ci}" title="Delete ${name}" aria-label="Delete ${name}">×</button>`;
    head.append(title);

    const col = make('div', 'column');
    col.style.left = left; col.style.width = width;
    let y = 0, index = 0;
    for (const row of column.boxes) {
      const key = `${fmt(row.depth)}X${fmt(column.width)}`;
      const cover = row.depth < defs.short_depth_below ? defs.cover_width_short : defs.cover_width;
      const height = Math.max(12, row.depth * scale - 2);
      for (let q = 0; q < row.qty; q++, index++) {
        const box = make('div', 'box' + (y + row.depth > d.depth + 1e-9 ? ' overflow' : ''));
        box.draggable = true; box.tabIndex = 0;
        box.dataset.column = ci; box.dataset.index = index;
        box.style.cssText = `top:${(d.depth - y - row.depth) * scale}px;height:${height}px;--h:${hueFor(key)}`;
        box.title = `${fmt(row.depth)} × ${fmt(column.width)} mm`;
        box.setAttribute('aria-label', `Box ${fmt(row.depth)} by ${fmt(column.width)} mm. Alt+Up or Alt+Down to move.`);
        box.innerHTML =
          `<i class="cover" style="height:${Math.min(row.depth, cover) * scale}px"></i>` +
          (height >= 18 ? `<span>${fmt(row.depth)} × ${fmt(column.width)}</span>` : '') +
          `<button class="box-delete" type="button" data-action="delete-box" aria-label="Delete box">×</button>`;
        col.append(box);
        y += row.depth;
      }
      total += row.qty;
      sizes.add(key);
    }
    const freePx = (d.depth - y) * scale;
    if (freePx >= 18) {
      const ghost = make('button', 'ghost box-ghost', column.width * scale >= 70 ? '+ Add boxes' : '+');
      ghost.type = 'button'; ghost.dataset.action = 'add-box'; ghost.dataset.column = ci;
      ghost.setAttribute('aria-label', `Add boxes to ${column.name}`);
      const height = Math.min(34, freePx - 6);
      ghost.style.top = `${freePx - height - 3}px`; ghost.style.height = `${height}px`;
      col.append(ghost);
    }
    body.append(col);
    x += column.width;
  });

  const freeWidthPx = (d.width - x) * scale;
  if (freeWidthPx >= 18) {
    const label = !project.columns.length ? '+ Add a column to start' : freeWidthPx >= 90 ? '+ Add column' : '+';
    const ghost = make('button', 'ghost column-ghost', label);
    ghost.type = 'button'; ghost.dataset.action = 'add-column';
    ghost.setAttribute('aria-label', 'Add column');
    ghost.style.left = `${x * scale + 3}px`; ghost.style.width = `${freeWidthPx - 6}px`;
    body.append(ghost);
  }

  canvas.replaceChildren(body);
  heads.replaceChildren(head);
  renderRulers(d);

  const over = x > d.width + 1e-9;
  $('summary').innerHTML =
    `<span class="chip">${plural(total, 'box')}</span>` +
    `<span class="chip">${plural(sizes.size, 'unique size')}</span>` +
    `<span class="chip${over ? ' over' : ''}">${fmt(x)} / ${fmt(d.width)} mm wide</span>`;
}

function renderRulers(d) {
  const step = [10, 20, 50, 100, 200, 500].find(value => value * scale >= 36) || 1000;
  const ticks = (length, side) => {
    const fragment = document.createDocumentFragment();
    for (let value = 0; value <= length; value += step) {
      const tick = make('span', 'ruler-tick', value);
      tick.style[side] = `${value * scale}px`;
      fragment.append(tick);
    }
    return fragment;
  };
  $('xRuler').style.width = `${d.width * scale}px`;
  $('yRuler').style.height = `${d.depth * scale}px`;
  $('xRuler').replaceChildren(ticks(d.width, 'left'));
  $('yRuler').replaceChildren(ticks(d.depth, 'bottom'));
}

// Clicks, drags and keys are delegated: no per-box listeners to rebuild on every render.
$('preview').addEventListener('click', event => {
  const target = event.target.closest('[data-action]');
  if (!target) return;
  const column = Number(target.dataset.column);
  switch (target.dataset.action) {
    case 'add-column': openColumnDialog(); break;
    case 'edit-column': openColumnEditor(column); break;
    case 'delete-column': deleteColumn(column); break;
    case 'add-box': openBoxDialog(column); break;
    case 'delete-box': {
      const box = target.closest('.box');
      removeBox(Number(box.dataset.column), Number(box.dataset.index));
      break;
    }
  }
});

let drag = null, dropTarget = null;
const canvas = $('canvas');
function setDropTarget(box) {
  if (dropTarget === box) return;
  dropTarget?.classList.remove('drop-target');
  dropTarget = box;
  box?.classList.add('drop-target');
}
canvas.addEventListener('dragstart', event => {
  const box = event.target.closest?.('.box');
  if (!box) return;
  drag = { column: Number(box.dataset.column), index: Number(box.dataset.index) };
  event.dataTransfer.setData('text/plain', `${drag.column}:${drag.index}`);
  event.dataTransfer.effectAllowed = 'move';
  box.classList.add('dragging');
});
canvas.addEventListener('dragover', event => {
  const box = event.target.closest?.('.box');
  if (drag && box && Number(box.dataset.column) === drag.column) {
    event.preventDefault();
    setDropTarget(box);
  } else setDropTarget(null);
});
canvas.addEventListener('drop', event => {
  const box = event.target.closest?.('.box');
  setDropTarget(null);
  if (!drag || !box || Number(box.dataset.column) !== drag.column) return;
  event.preventDefault();
  const { column, index } = drag;
  drag = null;
  moveBox(column, index, Number(box.dataset.index));
});
canvas.addEventListener('dragend', event => {
  event.target.classList?.remove('dragging');
  setDropTarget(null);
  drag = null;
});
canvas.addEventListener('keydown', event => {
  const box = event.target.closest?.('.box');
  if (!box || !event.altKey || (event.key !== 'ArrowUp' && event.key !== 'ArrowDown')) return;
  event.preventDefault();
  const column = Number(box.dataset.column), index = Number(box.dataset.index);
  const to = index + (event.key === 'ArrowUp' ? 1 : -1); // the stack grows upward
  if (moveBox(column, index, to)) {
    canvas.querySelector(`.box[data-column="${column}"][data-index="${to}"]`)?.focus();
  }
});
canvas.addEventListener('mousemove', event => {
  const rect = canvas.getBoundingClientRect(), d = project.drawer;
  const x = Math.max(0, Math.min(d.width, (event.clientX - rect.left) / scale));
  const y = Math.max(0, Math.min(d.depth, (rect.bottom - event.clientY) / scale));
  $('cursorPosition').textContent = `x ${x.toFixed(1)} · y ${y.toFixed(1)} mm`;
});
canvas.addEventListener('mouseleave', () => { $('cursorPosition').textContent = ''; });

let resizeFrame = 0;
addEventListener('resize', () => {
  cancelAnimationFrame(resizeFrame);
  resizeFrame = requestAnimationFrame(() => { if (computeScale() !== scale) render(); });
});

// ---------- validation ----------

let validateTimer = 0, validateSeq = 0;
function scheduleValidate() {
  clearTimeout(validateTimer);
  validateTimer = setTimeout(validate, 150);
}

async function validate() {
  clearTimeout(validateTimer);
  const seq = ++validateSeq;
  let issues;
  try {
    issues = (await api('/api/validate', project)).issues;
  } catch (error) {
    issues = [{ level: 'error', msg: error.message }];
  }
  if (seq !== validateSeq) return issues; // a newer edit is already being validated
  hasErrors = issues.some(issue => issue.level === 'error');
  $('issues').innerHTML = issues.map(issue =>
    `<div class="issue ${escapeHtml(issue.level)}"><b>${escapeHtml(issue.level)}</b><span>${escapeHtml(issue.msg)}</span></div>`).join('');
  updateSteps();
  return issues;
}

// ---------- workflow state ----------

function setNote(id, text, isError = false) {
  $(id).textContent = text;
  $(id).classList.toggle('error', isError);
}
function setProgress(id, done, total) {
  $(id).hidden = false;
  $(id).firstElementChild.style.width = total ? `${(done / total) * 100}%` : '0%';
}

function updateSteps() {
  const boxes = project.columns.reduce((sum, column) => sum + column.boxes.reduce((s, row) => s + row.qty, 0), 0);
  const built = builtSig === buildSig, arranged = arrangedSig === arrangeSig && arrangement;
  const unplaced = arranged ? arrangement.failed.length : 0;

  $('build').disabled = Boolean(busy) || hasErrors || !boxes || !tools.openscad.found;
  $('arrange').disabled = Boolean(busy) || hasErrors || !boxes;
  $('slice').disabled = Boolean(busy) || !built || !arranged || unplaced > 0 || !tools.prusaslicer.found;

  $('buildStale').hidden = built || busy === 'build';
  $('buildPanel').classList.toggle('stale', !built && busy !== 'build');
  $('arrangeStale').hidden = Boolean(arranged);
  $('arrangementView').classList.toggle('stale', !arranged);
  $('build').closest('.step').classList.toggle('done', built);
  $('arrange').closest('.step').classList.toggle('done', Boolean(arranged) && !unplaced);

  if (busy !== 'build') {
    if (!tools.openscad.found) setNote('buildNote', 'OpenSCAD was not found.', true);
    else if (!boxes) setNote('buildNote', 'Add some boxes first.');
    else if (hasErrors) setNote('buildNote', 'Fix the errors above first.', true);
    else if (built) setNote('buildNote', 'STL files are up to date.');
    else if (!$('buildNote').classList.contains('error')) setNote('buildNote', 'One STL per unique box size.');
  }
  if (busy !== 'arrange' && !$('arrangeNote').classList.contains('error')) {
    setNote('arrangeNote', arranged
      ? `${arrangement.placed}/${arrangement.total} boxes on ${plural(arrangement.beds.length, 'bed')}`
      : 'Pack every box onto print beds.');
  }
  if (busy !== 'slice' && !$('sliceNote').classList.contains('error')) {
    setNote('sliceNote',
      !tools.prusaslicer.found ? 'PrusaSlicer was not found.'
        : !built ? 'Generate the STL files first.'
        : !arranged ? 'Arrange the print beds first.'
        : unplaced ? `${plural(unplaced, 'box')} do not fit the bed.`
        : 'Ready to slice with PrusaSlicer.');
  }
}

async function pollUntilDone(path, onUpdate, interval) {
  for (;;) {
    const data = await api(path);
    onUpdate(data);
    if (data.state !== 'running') return data;
    await sleep(interval);
  }
}

// ---------- step 1: STL build ----------

function renderBuild(data) {
  const items = [...(data.items || [])].sort((a, b) => a.filename.localeCompare(b.filename, undefined, { numeric: true }));
  $('buildPanel').hidden = !items.length && data.state !== 'running';
  $('results').innerHTML = items.map(item => {
    const name = escapeHtml(item.filename);
    if (item.status === 'failed') {
      return `<div class="file failed"><span class="name">${name}</span><span class="meta">failed</span>` +
        `<details><summary>Log</summary><pre>${escapeHtml(item.log)}</pre></details></div>`;
    }
    const meta = item.status === 'cached' ? 'cached' : `${item.seconds}s`;
    return `<div class="file ${item.status}"><span class="name">${name}</span><span class="meta">${meta}</span>` +
      `<a href="/api/build/files/${encodeURIComponent(item.filename)}">Download</a></div>`;
  }).join('');
  if (data.state === 'running') {
    setProgress('buildProgress', data.done, data.total);
    setNote('buildNote', `Compiling ${data.done} / ${data.total}…`);
  }
  const anyFile = items.some(item => item.status !== 'failed');
  $('zip').hidden = data.state === 'running' || !anyFile;
  $('zip').href = `/api/build/zip?include_scad=${$('includeScad').checked}`;
}

async function build() {
  if ((await validate()).some(issue => issue.level === 'error')) return;
  const signature = buildSig;
  busy = 'build';
  setNote('buildNote', 'Starting…');
  setProgress('buildProgress', 0, 1);
  updateSteps();
  try {
    await api('/api/build', {
      project,
      options: {
        workers: +$('workers').value || 4, fn: +$('quality').value,
        include_scad: $('includeScad').checked, force: $('force').checked,
      },
    });
    const data = await pollUntilDone('/api/build', renderBuild, 500);
    if (data.state === 'done') {
      store(STORE_BUILT, signature);
      builtSig = signature;
      setNote('buildNote', '');
    } else {
      const failed = (data.items || []).filter(item => item.status === 'failed').length;
      setNote('buildNote', data.error || `${plural(failed, 'file')} failed. See the log below.`, true);
    }
  } catch (error) {
    setNote('buildNote', error.message, true);
  } finally {
    busy = null;
    $('buildProgress').hidden = true;
    updateSteps();
  }
}

// ---------- step 2: bed arrangement ----------

function renderBeds(data) {
  $('arrangementView').hidden = false;
  $('arrangementSummary').textContent =
    `${data.placed}/${data.total} boxes placed · ${plural(data.beds.length, 'bed')}` +
    (data.failed.length ? ` · ${data.failed.length} could not fit` : '');
  const fragment = document.createDocumentFragment();
  for (const bed of data.beds) {
    const panel = make('article', 'bed-panel');
    panel.append(make('h4', '', `Bed ${bed.number} · ${plural(bed.placements.length, 'box')}`));
    const surface = make('div', 'bed-surface');
    surface.style.width = `${data.bed.width}px`;
    surface.style.height = `${data.bed.depth}px`;
    for (const item of bed.placements) {
      const name = item.filename.replace(/\.stl$/, '');
      const box = make('div', 'bed-box', item.width >= 56 && item.depth >= 14 ? name.replace('X', ' × ') : '');
      box.style.cssText = `left:${item.x}px;bottom:${item.y}px;width:${item.width}px;height:${item.depth}px;--h:${hueFor(name)}`;
      box.title = `${item.filename}${item.rotated ? ' (rotated)' : ''}`;
      surface.append(box);
    }
    panel.append(surface);
    fragment.append(panel);
  }
  if (data.failed.length) {
    const names = [...new Set(data.failed.map(item => item.filename))].join(', ');
    fragment.append(make('p', 'arrangement-failed', `Too large for the bed: ${names}`));
  }
  $('beds').replaceChildren(fragment);
}

async function arrangeBeds() {
  const signature = arrangeSig;
  busy = 'arrange';
  setNote('arrangeNote', 'Arranging…');
  updateSteps();
  try {
    const data = await api('/api/arrange', {
      project,
      options: {
        bed_width: +$('bedWidth').value, bed_depth: +$('bedDepth').value,
        margin: +$('bedMargin').value, gap: +$('bedGap').value,
        allow_rotation: $('allowRotation').checked,
      },
    });
    arrangement = data;
    arrangedSig = signature;
    setNote('arrangeNote', '');
    renderBeds(data);
  } catch (error) {
    setNote('arrangeNote', error.message, true);
  } finally {
    busy = null;
    updateSteps();
  }
}

// ---------- step 3: slicing ----------

// Slicing shows a modal loading screen: showModal() centres it and makes the rest of
// the page inert, so nothing can be clicked, typed into or changed until it closes.
const sliceDialog = $('sliceDialog');
sliceDialog.addEventListener('cancel', event => event.preventDefault()); // Esc must not dismiss it

function showSliceProgress(done, total) {
  $('sliceDialogText').textContent = total
    ? (done >= total ? 'Finishing…' : `${done} of ${plural(total, 'bed')} done`)
    : 'Starting…';
  $('sliceDialogBar').style.width = total ? `${(done / total) * 100}%` : '0%';
}

function renderSlice(data) {
  const items = [...(data.items || [])].sort((a, b) => a.bed - b.bed);
  $('slicePanel').hidden = !items.length && data.state !== 'running';
  $('sliceResults').innerHTML = items.map(item => {
    if (item.status === 'done') {
      return `<div class="file"><span class="name">${escapeHtml(item.filename)}</span><span class="meta">${item.seconds}s</span>` +
        `<a href="/api/slice/files/${encodeURIComponent(item.filename)}">Download</a></div>`;
    }
    const debug = `returncode: ${item.returncode ?? 'n/a'}\ncommand: ${(item.command || []).join(' ')}\n\n` +
      `stdout:\n${item.stdout || ''}\n\nstderr:\n${item.stderr || ''}\n\nerror:\n${item.log || ''}`;
    return `<div class="file failed"><span class="name">Bed ${item.bed}</span><span class="meta">failed</span>` +
      `<details><summary>Debug details</summary><pre>${escapeHtml(debug)}</pre></details></div>`;
  }).join('');
  $('sliceDebug').hidden = !items.length;
  if (data.state === 'running') showSliceProgress(items.length, data.total);
}

async function sliceBeds() {
  busy = 'slice';
  let note = '', isError = false;
  showSliceProgress(0, 0);
  sliceDialog.showModal();
  updateSteps();
  try {
    await api('/api/slice', {
      arrangement,
      options: {
        print_profile: $('printProfile').value.trim(), printer_profile: $('printerProfile').value.trim(),
        material_profile: $('materialProfile').value.trim(),
        supports: $('supports').checked, binary_gcode: $('binaryGcode').checked,
      },
    });
    const data = await pollUntilDone('/api/slice', renderSlice, 800);
    if (data.state === 'done') note = `${plural(data.total, 'bed')} sliced.`;
    else [note, isError] = [data.error || 'Slicing failed. See the details below.', true];
  } catch (error) {
    [note, isError] = [error.message, true];
  } finally {
    busy = null;
    sliceDialog.close();
    updateSteps();
    setNote('sliceNote', note, isError); // keep the outcome until the next change
    if (!$('slicePanel').hidden) $('slicePanel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

// ---------- dialogs ----------

function openColumnDialog() {
  editingColumn = null;
  $('columnError').textContent = '';
  $('columnDialogTitle').textContent = 'Add columns';
  $('columnCountLabel').hidden = false;
  $('columnDialogHint').textContent = `Columns are added from left to right. ${fmt(project.drawer.width - usedWidth())} mm is free.`;
  $('columnCount').value = 1;
  $('deleteColumn').hidden = true;
  $('saveColumn').textContent = 'Add columns';
  $('columnDialog').showModal();
  $('columnWidth').select();
}

function openColumnEditor(index) {
  editingColumn = index;
  $('columnError').textContent = '';
  $('columnDialogTitle').textContent = `Edit ${project.columns[index].name}`;
  $('columnWidth').value = project.columns[index].width;
  $('columnCountLabel').hidden = true;
  $('columnDialogHint').textContent = 'Changing the width changes the length of every box in this column.';
  $('deleteColumn').hidden = false;
  $('saveColumn').textContent = 'Save changes';
  $('columnDialog').showModal();
  $('columnWidth').select();
}

function openBoxDialog(columnIndex) {
  addingBoxesToColumn = columnIndex;
  const column = project.columns[columnIndex];
  $('boxError').textContent = '';
  $('boxDialogTitle').textContent = `Add boxes to ${column.name}`;
  $('boxDialogHint').textContent =
    `Boxes stack from the bottom of the column upward. ${fmt(project.drawer.depth - usedDepth(column))} mm is free.`;
  $('boxCount').value = 1;
  $('boxDialog').showModal();
  $('boxDepth').select();
}

$('columnForm').addEventListener('submit', event => {
  event.preventDefault();
  const width = +$('columnWidth').value;
  if (!(width > 0)) return;
  const editing = editingColumn !== null;
  const existing = usedWidth() - (editing ? project.columns[editingColumn].width : 0);
  const count = editing ? 1 : Math.max(1, Math.floor(+$('columnCount').value));
  if (existing + width * count > project.drawer.width + 1e-9) {
    $('columnError').textContent = `That would exceed the drawer width. ${fmt(project.drawer.width - existing)} mm remains.`;
    return;
  }
  if (editing) project.columns[editingColumn].width = width;
  else {
    const start = project.columns.length;
    for (let i = 0; i < count; i++) project.columns.push({ name: `Col ${start + i + 1}`, width, boxes: [] });
  }
  $('columnDialog').close();
  changed();
});

$('boxForm').addEventListener('submit', event => {
  event.preventDefault();
  const depth = +$('boxDepth').value, count = Math.floor(+$('boxCount').value);
  if (!(depth > 0 && count > 0)) return;
  const column = project.columns[addingBoxesToColumn];
  const used = usedDepth(column);
  if (used + depth * count > project.drawer.depth + 1e-9) {
    $('boxError').textContent = `That would exceed the drawer depth. ${fmt(project.drawer.depth - used)} mm remains.`;
    return;
  }
  const last = column.boxes[column.boxes.length - 1];
  if (last && last.depth === depth) last.qty += count;
  else column.boxes.push({ depth, qty: count });
  $('boxDialog').close();
  changed();
});

$('cancelColumn').onclick = () => $('columnDialog').close();
$('cancelBox').onclick = () => $('boxDialog').close();
$('deleteColumn').onclick = () => { $('columnDialog').close(); deleteColumn(editingColumn); };

// ---------- sidebar ----------

for (const id of ['drawerWidth', 'drawerDepth', 'height', 'wall', 'radius']) {
  $(id).addEventListener('change', () => {
    project.drawer.width = +$('drawerWidth').value;
    project.drawer.depth = +$('drawerDepth').value;
    project.defaults.height = +$('height').value;
    project.defaults.wall = +$('wall').value;
    project.defaults.r = +$('radius').value;
    changed();
  });
}

$('addColumn').onclick = openColumnDialog;
$('build').onclick = build;
$('arrange').onclick = arrangeBeds;
$('slice').onclick = sliceBeds;

$('load').onclick = async () => {
  if (project.columns.length && !confirm('Replace the current drawer with the example?')) return;
  setProject(await api('/api/example'));
};
$('clear').onclick = () => {
  if (project.columns.length && !confirm('Remove every column and box?')) return;
  setProject(emptyProject());
};
$('save').onclick = () => {
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([JSON.stringify(project, null, 2)], { type: 'application/json' }));
  link.download = 'griddrawer-project.json';
  link.click();
  URL.revokeObjectURL(link.href);
};
$('open').onclick = () => $('openFile').click();
$('openFile').onchange = async event => {
  const file = event.target.files[0];
  event.target.value = '';
  if (!file) return;
  try {
    const next = JSON.parse(await file.text());
    await api('/api/validate', next); // rejects files that are not a project
    setProject({ ...emptyProject(), ...next });
  } catch (error) {
    alert(`Could not open that project file.\n${error.message}`);
  }
};

function renderTools() {
  const pill = (tool, label, key) => tool.found
    ? `<span class="pill" title="${escapeHtml(tool.path)}">${label} ${escapeHtml((tool.version || '').match(/\d[\d.]*/)?.[0] || '')}</span>`
    : `<button class="pill missing" type="button" data-tool="${key}" title="Click to set the executable path">${label} not found — set path</button>`;
  $('status').innerHTML = pill(tools.openscad, 'OpenSCAD', 'openscad') + pill(tools.prusaslicer, 'PrusaSlicer', 'prusaslicer');
}
$('status').addEventListener('click', async event => {
  const key = event.target.dataset.tool;
  if (!key) return;
  const path = prompt(`Full path to the ${key === 'openscad' ? 'OpenSCAD' : 'PrusaSlicer console'} executable:`);
  if (!path) return;
  tools = await api(`/api/${key}-path`, { path: path.trim().replace(/^"|"$/g, '') }, 'PUT');
  renderTools();
  updateSteps();
});

// ---------- start ----------

(async () => {
  try {
    const saved = JSON.parse(stored(STORE_PROJECT));
    if (saved && saved.drawer && Array.isArray(saved.columns)) project = { ...emptyProject(), ...saved };
  } catch { /* corrupt autosave: start empty */ }
  updateSignatures();
  render();
  updateSteps();
  const [status, lastBuild] = await Promise.all([api('/api/status'), api('/api/build'), validate()]);
  tools = status;
  renderTools();
  if (lastBuild.state === 'done' && stored(STORE_BUILT) === buildSig) {
    builtSig = buildSig;
    renderBuild(lastBuild);
  }
  updateSteps();
})();
