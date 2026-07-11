/**
 * RTL CPU Simulator — D3.js layout-engine renderer + cycle scrubber.
 *
 * Supports multiple ISAs (RISC-V, ARM, x86) and execution models
 * (single-cycle, pipeline, out-of-order, superscalar).
 *
 * Uses fixed layout templates for textbook-quality diagrams when available,
 * falling back to auto-positioned topology for unknown models.
 */

const API = window.CPU_API_URL || '';

// ── State ────────────────────────────────────────────────────────
let topology = null;
let cycleData = [];
let currentCycle = 0;
let playing = false;
let playTimer = null;
let layoutEngine = null;
let currentLayout = null;

// ISA / model state
let currentRegNames = [];
let currentISA = localStorage.getItem('cpu_sim_isa') || 'riscv';
let currentModel = localStorage.getItem('cpu_sim_model') || 'single_cycle';
let currentProgramFormat = 'words';
let currentInputMode = 'asm';  // 'asm' or 'hex'
let numLanes = parseInt(localStorage.getItem('cpu_sim_lanes'), 10) || 2;

// Program listing state
let instructionListing = [];   // [{addr, text, bytes?}]
let listingVisible = false;

// Memory viewer state
let memCenterAddr = 0;         // word address to center on
let memVisibleCount = 21;      // how many addresses to show (odd, so center is exact)
let memViewMode = 'dmem';      // 'dmem' or 'imem'
let memFollow = true;          // auto-center on the address written this cycle
let memLastWriteByte = null;   // byte address of the most recent write (for the inspector)

// Detail panel state
let detailPanelOpen = false;
let detailCompId = null;
let detailCompLabel = null;

// ── DOM refs ─────────────────────────────────────────────────────
const isaSel       = document.getElementById('isa-select');
const modelSel     = document.getElementById('model-select');
const btnRun       = document.getElementById('btn-run');
const btnPrev      = document.getElementById('btn-prev');
const btnNext      = document.getElementById('btn-next');
const btnPlay      = document.getElementById('btn-play');
const slider       = document.getElementById('cycle-slider');
const cycleLabel   = document.getElementById('cycle-label');
const progInput    = document.getElementById('program-input');
const numCyclesIn  = document.getElementById('num-cycles');
const autoCyclesChk = document.getElementById('auto-cycles');

// "auto" cycles: run to completion server-side; the number input becomes a
// read-only report of how many cycles the last run actually took.
if (autoCyclesChk && numCyclesIn) {
    autoCyclesChk.addEventListener('change', () => {
        numCyclesIn.disabled = autoCyclesChk.checked;
    });
    numCyclesIn.disabled = autoCyclesChk.checked;
}
const regPanel     = document.getElementById('register-panel');
const svg          = d3.select('#cpu-svg');
const pipePanel    = document.getElementById('pipeline-panel');
const oooPanel     = document.getElementById('ooo-panel');
const lanesControl = document.getElementById('lanes-control');
const lanesSlider  = document.getElementById('lanes-slider');
const lanesValue   = document.getElementById('lanes-value');
const btnModeAsm   = document.getElementById('btn-mode-asm');
const btnModeHex   = document.getElementById('btn-mode-hex');
const memGrid      = document.getElementById('memory-grid');
const memPanel     = document.getElementById('memory-panel');
const btnMemToggle = document.getElementById('btn-mem-toggle');
const memSearch     = document.getElementById('mem-search');
const btnMemGo      = document.getElementById('btn-mem-go');
const btnMemFollow  = document.getElementById('btn-mem-follow');
const memInspector  = document.getElementById('mem-inspector');
const memVisSlider  = document.getElementById('mem-visible-slider');
const memVisCount   = document.getElementById('mem-visible-count');
const btnCheatsheet= document.getElementById('btn-cheatsheet');
const cheatPanel   = document.getElementById('cheatsheet-panel');
const cheatOverlay = document.getElementById('cheatsheet-overlay');
const cheatContent = document.getElementById('cheatsheet-content');
const cheatTitle   = document.getElementById('cheatsheet-title');
const btnCloseCS   = document.getElementById('btn-close-cheatsheet');
const resizeHandle = document.getElementById('sidebar-resize-handle');
const sidebar      = document.querySelector('.cpu-sim__sidebar');
const btnExpand    = document.getElementById('btn-expand-editor');
const fsOverlay    = document.getElementById('fs-editor-overlay');
const fsTextarea   = document.getElementById('fs-editor-textarea');
const fsLineNums   = document.getElementById('fs-line-numbers');
const btnFsSave    = document.getElementById('btn-fs-save');
const btnFsCancel  = document.getElementById('btn-fs-cancel');
const bpSel        = document.getElementById('bp-select');
const bpStageCtrl  = document.getElementById('bp-stage-control');
const bpStageBtns  = bpStageCtrl.querySelectorAll('[data-bp-stage]');
let   bpStage      = localStorage.getItem('cpu_sim_bp_stage') || 'id';  // current prediction stage
// Wire-layer control (OoO renderer declutter) — null-guarded: the control group
// may be absent in older markup, so every access checks for existence.
const wireLayerControl = document.getElementById('wire-layer-control');
// Configurable model: cycle-budget knobs + readout, single-cycle explainer.
const cfgPanel     = document.getElementById('configurable-panel');
const scNote       = document.getElementById('single-cycle-note');
const cfgRanges    = document.querySelectorAll('.cfg-range');
const cfgPresets   = document.querySelectorAll('.cfg-preset');
const cfgCyclesOut = document.getElementById('cfg-cycles');
const cfgPeriodOut = document.getElementById('cfg-period');
const cfgTimeOut   = document.getElementById('cfg-time');
const wireLayerChips   = wireLayerControl
    ? wireLayerControl.querySelectorAll('input[data-layer]')
    : [];
const _WIRE_LAYERS     = ['data', 'control', 'cdb', 'commit'];
const btnModeC     = document.getElementById('btn-mode-c');
const progListing  = document.getElementById('program-listing');
const btnMemDmem   = document.getElementById('btn-mem-dmem');
const btnMemImem   = document.getElementById('btn-mem-imem');
const detailPanel  = document.getElementById('comp-detail-panel');
const detailOverlay= document.getElementById('detail-overlay');
const detailTitle  = document.getElementById('detail-panel-title');
const detailContent= document.getElementById('detail-panel-content');
const btnCloseDetail= document.getElementById('btn-close-detail');
const btnLoadExample  = document.getElementById('btn-load-example');
const exampleOverlay  = document.getElementById('example-overlay');
const exampleContent  = document.getElementById('example-modal-content');
const btnCloseExamples = document.getElementById('btn-close-examples');

// ── Examples state ───────────────────────────────────────────────
let examplesCatalog = null;  // cached catalog (all ISAs)

// ── Layout constants for fallback auto-layout ────────────────────
const NODE_W = 150;
const NODE_H = 60;
const H_GAP  = 50;
const V_GAP  = 40;
const PAD    = 40;

const CATEGORY_ROW = {
    fetch: 0, decode: 0, execute: 0, memory: 0, writeback: 0,
    control: 1, pipeline: 2, ooo: 2,
};

// ── Input mode toggle ────────────────────────────────────────────
btnModeAsm.addEventListener('click', () => switchInputMode('asm'));
btnModeHex.addEventListener('click', () => switchInputMode('hex'));
if (btnModeC) btnModeC.addEventListener('click', () => switchInputMode('c'));

function switchInputMode(mode) {
    const prevMode = currentInputMode;
    currentInputMode = mode;
    // Leaving Source (C): swap the C buffer out of the shared textarea for
    // the compiled assembly, so Run never feeds C source to the assembler.
    if (prevMode === 'c' && mode !== 'c' &&
            typeof CompilerTab !== 'undefined' && CompilerTab.onLeaveMode) {
        CompilerTab.onLeaveMode();
    }
    btnModeAsm.classList.toggle('toggle-btn--active', mode === 'asm');
    btnModeHex.classList.toggle('toggle-btn--active', mode === 'hex');
    if (btnModeC) btnModeC.classList.toggle('toggle-btn--active', mode === 'c');
    // Compiler-mode UI (null-guarded — the elements may be absent in old markup)
    const cc = document.getElementById('compiler-controls');
    const cs = document.getElementById('compiler-stages');
    const isC = mode === 'c';
    if (cc) cc.style.display = isC ? 'flex' : 'none';
    if (cs && !isC) cs.style.display = 'none';
    if (isC) {
        // Editing C source: always show the raw textarea, never the asm listing.
        hideProgramListing();
        if (typeof CompilerTab !== 'undefined' && CompilerTab.onEnterMode) {
            CompilerTab.onEnterMode();
        }
    }
}

// ── Examples modal ───────────────────────────────────────────────
const _EXAMPLE_CATEGORY_ORDER = ['instructions', 'hazards', 'branch_prediction', 'algorithms'];

function openExamplesModal() { exampleOverlay.classList.add('active'); }
function closeExamplesModal() { exampleOverlay.classList.remove('active'); }

btnLoadExample.addEventListener('click', async () => {
    if (!examplesCatalog) {
        try {
            const res = await fetch(`${API}/examples`);
            examplesCatalog = await res.json();
        } catch (err) {
            console.error('Failed to load examples:', err);
            return;
        }
    }
    renderExampleModal();
    openExamplesModal();
});

btnCloseExamples.addEventListener('click', closeExamplesModal);
exampleOverlay.addEventListener('click', (e) => {
    if (e.target === exampleOverlay) closeExamplesModal();
});

// ── Cycles-to-completion comparison modal ────────────────────────
const btnCompare      = document.getElementById('btn-compare');
const compareOverlay  = document.getElementById('compare-overlay');
const compareContent  = document.getElementById('compare-modal-content');
const btnCloseCompare = document.getElementById('btn-close-compare');
const _MODEL_LABELS = {single_cycle: 'Single Cycle', multicycle: 'Multicycle',
                       configurable: 'Configurable',
                       pipeline: 'Pipeline', ooo: 'Out-of-Order',
                       superscalar: 'Superscalar'};
const _ISA_LABELS = {riscv: 'RISC-V', arm: 'ARM', x86: 'x86'};

if (btnCloseCompare) btnCloseCompare.addEventListener('click',
    () => compareOverlay.classList.remove('active'));
if (compareOverlay) compareOverlay.addEventListener('click', (e) => {
    if (e.target === compareOverlay) compareOverlay.classList.remove('active');
});

async function runComparison() {
    // Core-C compares across all ISAs; asm/hex only across models of the
    // current ISA (assembly is inherently ISA-specific).
    const body = {};
    if (currentInputMode === 'c') {
        body.source = progInput.value;
    } else if (currentInputMode === 'asm') {
        body.asm_text = progInput.value;
        body.isa = currentISA;
    } else {
        alert('Compare works from Assembly or Source (C) mode.');
        return;
    }
    if (!((body.source || body.asm_text) || '').trim()) {
        alert('Nothing to compare — the editor is empty.');
        return;
    }
    body.num_lanes = numLanes;

    compareContent.innerHTML =
        '<div class="compare-note">Running every target to completion…</div>';
    compareOverlay.classList.add('active');
    try {
        const res = await fetch(`${API}/compare`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        });
        const data = await res.json();
        if (data.error) {
            compareContent.innerHTML =
                `<div class="compare-note">${data.error}</div>`;
            return;
        }
        renderComparison(data);
    } catch (e) {
        compareContent.innerHTML =
            `<div class="compare-note">Comparison failed: ${e.message}</div>`;
    }
}

function renderComparison(data) {
    const byCell = {};
    for (const r of data.results) byCell[`${r.isa}/${r.model}`] = r;
    const models = data.models;
    let html = '<table class="compare-table"><thead><tr><th></th>';
    for (const m of models) html += `<th>${_MODEL_LABELS[m] || m}</th>`;
    html += '<th class="compare-table__len">Instrs</th></tr></thead><tbody>';
    for (const isa of data.isas) {
        html += `<tr><th>${_ISA_LABELS[isa] || isa}</th>`;
        let programLen = null;
        for (const m of models) {
            const r = byCell[`${isa}/${m}`] || {};
            if (r.cycles != null && r.completed) {
                html += `<td class="compare-cell--ok">${r.cycles.toLocaleString()}</td>`;
                if (r.program_len != null) programLen = r.program_len;
            } else if (r.cycles != null) {
                html += `<td class="compare-cell--warn" title="did not settle ` +
                        `within ${data.cap.toLocaleString()} cycles">&gt;${data.cap.toLocaleString()}</td>`;
            } else {
                const why = (r.error || 'unavailable').replace(/"/g, '&quot;');
                html += `<td class="compare-cell--na" title="${why}">—</td>`;
            }
        }
        html += `<td class="compare-table__len">${programLen != null ? programLen.toLocaleString() : ''}</td></tr>`;
    }
    html += '</tbody></table>';
    html += '<div class="compare-note">Cycles to completion (settle point of ' +
            'registers + data memory). Hover a — cell for why that target is ' +
            'unavailable; every shown count is parity-checked against ' +
            'single-cycle, so all numbers compute the same result. ' +
            '"Instrs" = program length (words; bytes on x86).</div>';
    compareContent.innerHTML = html;
}

if (btnCompare) btnCompare.addEventListener('click', runComparison);

function renderExampleModal() {
    exampleContent.innerHTML = '';
    const isaCat = examplesCatalog[currentISA];
    if (!isaCat) {
        exampleContent.innerHTML = '<div style="padding:18px;color:var(--text-muted);font-size:0.82rem;text-align:center;">No examples available for this ISA</div>';
        return;
    }
    for (const catKey of _EXAMPLE_CATEGORY_ORDER) {
        const cat = isaCat[catKey];
        if (!cat) continue;
        const header = document.createElement('div');
        header.className = 'example-modal__category';
        header.textContent = cat.label;
        exampleContent.appendChild(header);
        for (const item of cat.items) {
            const btn = document.createElement('button');
            btn.className = 'example-modal__item';
            btn.textContent = item.label;
            btn.addEventListener('click', () => loadExample(item.file));
            exampleContent.appendChild(btn);
        }
    }
}

async function loadExample(filepath) {
    closeExamplesModal();
    try {
        const res = await fetch(`${API}/examples/${filepath}`);
        const data = await res.json();
        if (data.error) {
            console.error('Example load error:', data.error);
            return;
        }
        // Switch mode FIRST: leaving C mode swaps buffers via onLeaveMode,
        // which would otherwise clobber the freshly loaded example.
        switchInputMode('asm');
        progInput.value = data.content;
        hideProgramListing();
    } catch (err) {
        console.error('Failed to load example:', err);
    }
}

// ── Resizable sidebar ────────────────────────────────────────────
(function initResize() {
    let startX, startW;
    resizeHandle.addEventListener('mousedown', (e) => {
        e.preventDefault();
        startX = e.clientX;
        startW = sidebar.offsetWidth;
        resizeHandle.classList.add('active');
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    });
    function onMouseMove(e) {
        const newW = Math.min(600, Math.max(200, startW + (e.clientX - startX)));
        sidebar.style.width = newW + 'px';
    }
    function onMouseUp() {
        resizeHandle.classList.remove('active');
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
    }
})();

// ── Full-screen editor ───────────────────────────────────────────
btnExpand.addEventListener('click', () => openFullscreenEditor());
btnFsSave.addEventListener('click', () => closeFullscreenEditor(true));
btnFsCancel.addEventListener('click', () => closeFullscreenEditor(false));

function openFullscreenEditor() {
    fsTextarea.value = progInput.value;
    fsOverlay.classList.add('active');
    updateFsLineNumbers();
    fsTextarea.focus();
}

function closeFullscreenEditor(save) {
    if (save) {
        progInput.value = fsTextarea.value;
    }
    fsOverlay.classList.remove('active');
}

function updateFsLineNumbers() {
    const count = fsTextarea.value.split('\n').length;
    let html = '';
    for (let i = 1; i <= count; i++) html += i + '\n';
    fsLineNums.textContent = html;
}

fsTextarea.addEventListener('input', updateFsLineNumbers);
fsTextarea.addEventListener('scroll', () => {
    fsLineNums.scrollTop = fsTextarea.scrollTop;
});

// ── Memory panel collapse (declutter; collapsed by default, persisted) ──
function setMemCollapsed(collapsed) {
    memPanel.classList.toggle('collapsed', collapsed);
    btnMemToggle.setAttribute('aria-expanded', String(!collapsed));
    localStorage.setItem('cpu_sim_mem_collapsed', collapsed ? '1' : '0');
}
btnMemToggle.addEventListener('click', () =>
    setMemCollapsed(!memPanel.classList.contains('collapsed')));
// Restore prior choice; default collapsed when unset.
setMemCollapsed(localStorage.getItem('cpu_sim_mem_collapsed') !== '0');

// ── Cheat sheet ──────────────────────────────────────────────────
btnCheatsheet.addEventListener('click', () => toggleCheatsheet(true));
btnCloseCS.addEventListener('click', () => toggleCheatsheet(false));
cheatOverlay.addEventListener('click', () => toggleCheatsheet(false));

function toggleCheatsheet(show) {
    cheatPanel.classList.toggle('active', show);
    cheatOverlay.classList.toggle('active', show);
}

async function loadCheatsheet() {
    try {
        const res = await fetch(`${API}/cheatsheet/${currentISA}`);
        const data = await res.json();
        if (data.error) return;
        renderCheatsheet(data.instructions);
        cheatTitle.textContent = `${currentISA.toUpperCase()} Instructions`;
    } catch (e) {
        console.error('Cheatsheet load failed:', e);
    }
}

function renderCheatsheet(instructions) {
    const grouped = {};
    instructions.forEach(instr => {
        if (!grouped[instr.category]) grouped[instr.category] = [];
        grouped[instr.category].push(instr);
    });

    let html = '';
    for (const [cat, instrs] of Object.entries(grouped)) {
        html += `<div class="cheatsheet-category"><h3>${cat}</h3>`;
        for (const i of instrs) {
            html += `<div class="cheatsheet-entry">
                <span class="cheatsheet-mnemonic">${i.mnemonic}</span>
                <span class="cheatsheet-syntax">${i.syntax}</span>
                <div class="cheatsheet-desc">${i.description}</div>
            </div>`;
        }
        html += '</div>';
    }
    cheatContent.innerHTML = html;
}

// ── Lanes control ────────────────────────────────────────────────
lanesSlider.addEventListener('input', () => {
    numLanes = parseInt(lanesSlider.value);
    lanesValue.textContent = numLanes;
    localStorage.setItem('cpu_sim_lanes', numLanes);
    loadTopology();
});

// ── ISA / Model change handlers ─────────────────────────────────
isaSel.value = currentISA;
modelSel.value = currentModel;
lanesSlider.value = numLanes;
lanesValue.textContent = numLanes;

isaSel.addEventListener('change', async () => {
    currentISA = isaSel.value;
    localStorage.setItem('cpu_sim_isa', currentISA);
    try {
        const res = await fetch(`${API}/isa/${currentISA}`);
        const info = await res.json();
        currentRegNames = info.reg_names;
        currentProgramFormat = info.program_format;
        if (currentInputMode === 'c') {
            // In Source (C) mode the editor holds C source, not a demo program —
            // leave it as-is; just refresh which toolchains apply to the new ISA.
            if (typeof CompilerTab !== 'undefined' && CompilerTab.onEnterMode) {
                CompilerTab.onEnterMode();
            }
        } else if (currentInputMode === 'asm' && info.demo_program_asm) {
            progInput.value = info.demo_program_asm;
        } else {
            progInput.value = info.demo_program_text;
        }
    } catch (e) {
        console.error('Failed to load ISA info:', e);
    }
    cycleData = [];
    currentCycle = 0;
    hideProgramListing();
    updatePanelVisibility();
    if (exampleOverlay.classList.contains('active')) renderExampleModal();
    await loadTopology();
    loadCheatsheet();
});

modelSel.addEventListener('change', async () => {
    currentModel = modelSel.value;
    localStorage.setItem('cpu_sim_model', currentModel);
    cycleData = [];
    currentCycle = 0;
    hideProgramListing();
    updatePanelVisibility();
    await loadTopology();
});

function updatePanelVisibility() {
    pipePanel.style.display = (currentModel === 'pipeline') ? 'block' : 'none';
    oooPanel.style.display = currentModel === 'ooo' ? 'block' : 'none';
    lanesControl.style.display = currentModel === 'superscalar' ? 'flex' : 'none';
    if (wireLayerControl) {
        wireLayerControl.style.display = currentModel === 'ooo' ? 'flex' : 'none';
    }
    if (cfgPanel) cfgPanel.style.display = (currentModel === 'configurable') ? 'block' : 'none';
    if (scNote) scNote.style.display = (currentModel === 'single_cycle') ? 'block' : 'none';
    // The cycle-budget readout needs the settled cycle count, so the
    // Configurable model runs to completion by default.
    if (currentModel === 'configurable' && autoCyclesChk && !autoCyclesChk.checked) {
        autoCyclesChk.checked = true;
    }
    if (typeof updateBpStageVisibility === 'function') updateBpStageVisibility();
}

// ── Configurable model: cycle-budget knobs ───────────────────────
const CFG_PRESETS = {
    single:    { alu: 1, load: 1, store: 1, branch: 1 },
    fetdecexe: { alu: 3, load: 4, store: 4, branch: 3 },
};
function cfgCosts() {
    const c = {};
    cfgRanges.forEach(r => { c[r.dataset.class] = parseInt(r.value, 10) || 1; });
    return c;
}
function cfgSyncLabels() {
    cfgRanges.forEach(r => {
        const v = document.querySelector(`.cfg-knob__val[data-val="${r.dataset.class}"]`);
        if (v) v.textContent = r.value;
    });
    const cur = cfgCosts();
    cfgPresets.forEach(btn => {
        const p = CFG_PRESETS[btn.dataset.preset] || {};
        const match = Object.keys(p).every(k => p[k] === cur[k]);
        btn.classList.toggle('cfg-preset--active', match);
    });
}
function updateCfgReadout(tm) {
    if (!tm) return;
    if (cfgCyclesOut) cfgCyclesOut.textContent = (tm.cycles != null) ? tm.cycles : '—';
    if (cfgPeriodOut) cfgPeriodOut.textContent = (tm.clock_period != null) ? tm.clock_period.toFixed(2) : '—';
    if (cfgTimeOut)   cfgTimeOut.textContent = (tm.total_time != null) ? Math.round(tm.total_time) : '—';
}
cfgRanges.forEach(r => {
    r.addEventListener('input', cfgSyncLabels);   // live label + preset highlight
    r.addEventListener('change', () => {          // re-run on release
        if (currentModel === 'configurable' && cycleData.length) runSimulation();
    });
});
cfgPresets.forEach(btn => {
    btn.addEventListener('click', () => {
        const p = CFG_PRESETS[btn.dataset.preset];
        if (!p) return;
        cfgRanges.forEach(r => { r.value = p[r.dataset.class]; });
        cfgSyncLabels();
        if (currentModel === 'configurable' && cycleData.length) runSimulation();
    });
});
cfgSyncLabels();

// ── Wire-layer toggles (OoO renderer declutter) ──────────────────
// Each chip persists to localStorage key cpu_sim_ooo_layer_<name>; visible by
// default when unset. applyWireLayers() re-reads + re-applies the saved state
// after every OoO (re)render, since renderLayout rebuilds the wire DOM.
function _layerStorageKey(name) { return `cpu_sim_ooo_layer_${name}`; }

function _layerVisibleSaved(name) {
    const v = localStorage.getItem(_layerStorageKey(name));
    return v === null ? true : (v === '1' || v === 'true');
}

function applyWireLayers() {
    if (!layoutEngine || typeof layoutEngine.setLayerVisible !== 'function') return;
    for (const name of _WIRE_LAYERS) {
        const visible = _layerVisibleSaved(name);
        wireLayerChips.forEach(cb => {
            if (cb.dataset.layer === name) cb.checked = visible;
        });
        layoutEngine.setLayerVisible(name, visible);
    }
}

wireLayerChips.forEach(cb => {
    cb.addEventListener('change', () => {
        const name = cb.dataset.layer;
        const on = cb.checked;
        localStorage.setItem(_layerStorageKey(name), on ? '1' : '0');
        if (layoutEngine && typeof layoutEngine.setLayerVisible === 'function') {
            layoutEngine.setLayerVisible(name, on);
        }
    });
});

function getPresetName() {
    return `${isaSel.value}/${modelSel.value}`;
}

// ── Layout selection ─────────────────────────────────────────────
function getLayoutForModel(model) {
    try {
        if (model === 'single_cycle' && window.getSingleCycleLayout) {
            return window.getSingleCycleLayout();
        }
        if (model === 'pipeline' && window.getPipelineLayout) {
            return window.getPipelineLayout();
        }
        if (model === 'superscalar' && window.getSuperscalarLayout) {
            return window.getSuperscalarLayout(numLanes);
        }
        if (model === 'ooo' && window.getOoOLayout) {
            return window.getOoOLayout();
        }
        if (model === 'multicycle' && window.getMulticycleLayout) {
            return window.getMulticycleLayout();
        }
    } catch (e) {
        console.warn('Layout template error, falling back to auto:', e);
    }
    return null;
}

// ── Topology rendering (fallback auto-layout) ────────────────────
function layoutNodes(nodes) {
    const rows = {};
    nodes.forEach(n => {
        const row = CATEGORY_ROW[n.category] !== undefined ? CATEGORY_ROW[n.category] : 2;
        if (!rows[row]) rows[row] = [];
        rows[row].push(n);
    });
    const sortedRows = Object.keys(rows).sort((a, b) => a - b);
    sortedRows.forEach((rowIdx, ri) => {
        rows[rowIdx].forEach((n, ci) => {
            n.x = PAD + ci * (NODE_W + H_GAP);
            n.y = PAD + ri * (NODE_H + V_GAP + 60);
        });
    });
    return nodes;
}

function renderTopologyFallback(topo) {
    topology = topo;
    svg.selectAll('*').remove();

    const width = svg.node().parentElement.clientWidth;
    const height = svg.node().parentElement.clientHeight;
    svg.attr('viewBox', `0 0 ${width} ${height}`);

    const defs = svg.append('defs');
    defs.append('marker')
        .attr('id', 'arrowhead')
        .attr('viewBox', '0 0 10 7')
        .attr('refX', 10).attr('refY', 3.5)
        .attr('markerWidth', 8).attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path').attr('d', 'M0,0 L10,3.5 L0,7 Z');

    const nodes = layoutNodes(topo.nodes);
    const nodeMap = {};
    nodes.forEach(n => nodeMap[n.id] = n);

    const g = svg.append('g').attr('class', 'canvas');
    svg.call(d3.zoom().scaleExtent([0.3, 3]).on('zoom', e => {
        g.attr('transform', e.transform);
    }));

    const edgeG = g.selectAll('.edge').data(topo.edges).enter()
        .append('g').attr('class', 'edge');
    edgeG.each(function(d) {
        const src = nodeMap[d.from.split('.')[0]];
        const dst = nodeMap[d.to.split('.')[0]];
        if (!src || !dst) return;
        const x1 = src.x + NODE_W, y1 = src.y + NODE_H / 2;
        const x2 = dst.x, y2 = dst.y + NODE_H / 2;
        if (x1 <= x2) {
            d3.select(this).append('line')
                .attr('x1', x1).attr('y1', y1)
                .attr('x2', x2).attr('y2', y2)
                .attr('marker-end', 'url(#arrowhead)');
        } else {
            const midY = Math.max(y1, y2) + NODE_H + 20;
            d3.select(this).append('path')
                .attr('d', `M${x1},${y1} L${x1+20},${y1} L${x1+20},${midY} L${x2-20},${midY} L${x2-20},${y2} L${x2},${y2}`)
                .attr('marker-end', 'url(#arrowhead)');
        }
    });

    const nodeG = g.selectAll('.node').data(nodes).enter()
        .append('g')
        .attr('class', d => `node node--${d.category}`)
        .attr('data-id', d => d.id)
        .attr('transform', d => `translate(${d.x},${d.y})`);
    nodeG.append('rect').attr('width', NODE_W).attr('height', NODE_H);
    nodeG.append('text').attr('class', 'node-label')
        .attr('x', NODE_W / 2).attr('y', 22).text(d => d.label);
    nodeG.append('text').attr('class', 'node-detail')
        .attr('x', NODE_W / 2).attr('y', 42).text('');

    const tooltip = d3.select('body').selectAll('.cpu-tooltip').data([0]).join('div')
        .attr('class', 'cpu-tooltip').style('display', 'none');
    nodeG.on('mouseenter', function(event, d) {
        if (!cycleData.length) return;
        const state = cycleData[currentCycle]?.[d.id];
        if (!state) return;
        let html = '<dl>';
        for (const [k, v] of Object.entries(state)) {
            if (k === 'registers' || k === 'memory' || k === 'memory_hi' || k === 'window') continue;
            html += `<dt>${k}</dt><dd>${typeof v === 'number' ? '0x' + (v >>> 0).toString(16) : v}</dd>`;
        }
        html += '</dl>';
        tooltip.html(html).style('display', 'block');
    })
    .on('mousemove', function(event) {
        tooltip.style('left', (event.pageX + 12) + 'px').style('top', (event.pageY - 10) + 'px');
    })
    .on('mouseleave', function() { tooltip.style('display', 'none'); });
}

// ── Render with layout engine or fallback ────────────────────────
function renderTopology(topo) {
    topology = topo;
    const layout = getLayoutForModel(topo.model || currentModel);
    // Tag the SVG so OoO-only CSS (active-path dim, bus styling) applies without
    // affecting the other 14 configs. LayoutEngine doesn't set a per-model class.
    if (svg && svg.node()) svg.classed('le-diagram--ooo', currentModel === 'ooo');

    if (layout && window.LayoutEngine) {
        try {
            if (!layoutEngine) {
                layoutEngine = new window.LayoutEngine(svg);
            }
            currentLayout = layout;
            layoutEngine.renderLayout(layout, null);
            // Re-apply saved wire-layer toggles once the OoO wire DOM is (re)built.
            if (currentModel === 'ooo') applyWireLayers();
            return;
        } catch (e) {
            console.warn('Layout engine error, falling back:', e);
        }
    }

    // Fallback to auto-layout
    currentLayout = null;
    renderTopologyFallback(topo);
}

// ── Cycle state display ──────────────────────────────────────────
function displayCycle(idx) {
    if (!cycleData.length) return;
    currentCycle = Math.max(0, Math.min(idx, cycleData.length - 1));
    slider.value = currentCycle;
    cycleLabel.textContent = `Cycle ${currentCycle}`;

    const state = cycleData[currentCycle];

    // Update via layout engine or fallback
    if (layoutEngine && currentLayout) {
        const instrMap = buildInstrMap(state);
        layoutEngine.updateState(state, instrMap);
    } else {
        // Fallback: update node detail text
        svg.selectAll('.node').each(function(d) {
            const compState = state[d.id];
            if (!compState) return;
            d3.select(this).select('.node-detail').text(summarize(d.id, compState));
        });
        svg.selectAll('.node').classed('node--active', d => !!state[d.id]);
    }

    updateRegisters(state);
    updateMemoryView(state);

    if (currentModel === 'pipeline') {
        updatePipelineView(state);
    } else if (currentModel === 'ooo') {
        updateOoOView(state);
    }

    // Update program listing badges
    if (listingVisible) {
        renderProgramListing(state);
    }

    // Update detail panel if open
    if (detailPanelOpen && detailCompId) {
        renderDetailContent(detailCompId, state);
    }
}

function summarize(compId, state) {
    if (compId === 'fetch')   return state.pc !== undefined ? `PC=${state.pc}` : '';
    if (compId === 'imem')    return state.data !== undefined ? `${state.data}` : '';
    if (compId === 'decode')  return `rd=${state.rd ?? '?'} ${state.alu_op || ''}`;
    if (compId === 'alu')     return state.result !== undefined ? `${state.result}` : '';
    if (compId === 'branch')  return state.branch_taken ? 'TAKEN' : '';
    if (compId === 'dmem')    return state.wen ? 'WRITE' : '';
    if (compId === 'wb')      return `${state.sel || ''}`;
    if (compId === 'bpred')   return String(state.prediction || '');
    if (compId === 'if_id')   return state.instr !== undefined ? `I=${state.instr}` : '';
    if (compId === 'id_ex')   return state.alu_op !== undefined ? `op=${state.alu_op}` : '';
    if (compId === 'ex_mem')  return state.alu_result !== undefined ? `R=${state.alu_result}` : '';
    if (compId === 'mem_wb')  return state.rd !== undefined ? `rd=${state.rd}` : '';
    if (compId === 'hazard_det') return state.stall === 'STALL' ? 'STALL' : '';
    if (compId === 'flags_reg')  return state.zero_out ? 'Z' : '';
    if (compId === 'rob')  return state.count !== undefined ? `entries=${state.count}` : '';
    if (compId === 'rs')   return state.exec_valid ? 'EXEC' : '';
    // Handle decode_0, decode_1 etc. for superscalar
    if (compId.startsWith('decode_')) return `rd=${state.rd ?? '?'}`;
    if (compId.startsWith('alu_'))   return state.result !== undefined ? `${state.result}` : '';
    return '';
}

// Registers of the cycle immediately BEFORE the one being displayed. Diffing
// against this (rather than the last-displayed view) keeps the change-highlight
// correct when the slider is scrubbed non-sequentially. Mirrors the memory view.
function prevCycleRegs() {
    if (currentCycle > 0 && cycleData[currentCycle - 1]) {
        const pr = cycleData[currentCycle - 1].regfile;
        if (pr && pr.registers) return pr.registers;
    }
    return null;
}

function updateRegisters(state) {
    const regState = state.regfile;
    if (!regState || !regState.registers) return;
    const regs = regState.registers;
    const prev = prevCycleRegs();

    let html = '';
    for (let i = 0; i < regs.length; i++) {
        const name = (currentRegNames.length > i) ? currentRegNames[i] : `r${i}`;
        const val = regs[i];
        const changed = prev && prev[i] !== val;
        html += `<div class="reg ${changed ? 'reg--changed' : ''}">`;
        html += `<span class="reg__name">${name}</span>`;
        html += `<span class="reg__val">${val}</span>`;
        html += '</div>';
    }
    regPanel.innerHTML = html;
}

// ── Pipeline view ────────────────────────────────────────────────
function updatePipelineView(state) {
    const stages = [
        { id: 'stage-if',  label: 'IF',  comp: 'fetch',  pipeReg: 'if_id' },
        { id: 'stage-id',  label: 'ID',  comp: 'decode', pipeReg: 'id_ex' },
        { id: 'stage-ex',  label: 'EX',  comp: 'alu',    pipeReg: 'ex_mem' },
        { id: 'stage-mem', label: 'MEM', comp: 'dmem',   pipeReg: 'mem_wb' },
        { id: 'stage-wb',  label: 'WB',  comp: 'wb',     pipeReg: null },
    ];
    stages.forEach(s => {
        const el = document.getElementById(s.id);
        if (!el) return;
        el.className = 'pipeline-stage';

        let info = '';
        const hazard = state['hazard_det'];
        if (hazard && (hazard.stall === 'STALL' || hazard.stall === 1) && (s.id === 'stage-if' || s.id === 'stage-id')) {
            el.classList.add('pipeline-stage--stall');
            info = 'STALL';
        } else {
            const branch = state['branch'];
            if (branch && branch.mispredict && (s.id === 'stage-if' || s.id === 'stage-id' || s.id === 'stage-ex')) {
                el.classList.add('pipeline-stage--flush');
                info = 'FLUSH';
            } else {
                const pipeState = s.pipeReg ? state[s.pipeReg] : null;
                if (pipeState && pipeState.valid === 'BUBBLE') {
                    el.classList.add('pipeline-stage--bubble');
                    info = 'BUBBLE';
                } else if (state[s.comp]) {
                    el.classList.add('pipeline-stage--valid');
                    // Extract instruction summary from pipeline register state.
                    // instr / alu_result are already hex strings; rd / alu_op ints.
                    if (pipeState) {
                        if (s.pipeReg === 'if_id' && pipeState.instr !== undefined) {
                            info = pipeState.instr;
                        } else if (s.pipeReg === 'id_ex') {
                            const parts = [];
                            if (pipeState.alu_op) parts.push(`op=${pipeState.alu_op}`);
                            if (pipeState.rd !== undefined) parts.push(`rd=${pipeState.rd}`);
                            info = parts.join(' ');
                        } else if (s.pipeReg === 'ex_mem' && pipeState.alu_result !== undefined) {
                            info = `R=${pipeState.alu_result}`;
                        } else if (s.pipeReg === 'mem_wb' && pipeState.rd !== undefined) {
                            info = `rd=${pipeState.rd}`;
                        }
                    }
                    // WB stage: show writeback source
                    if (!s.pipeReg && state[s.comp]) {
                        info = state[s.comp].sel || '';
                    }
                }
            }
        }

        el.innerHTML = `${s.label}<span class="stage-info">${info}</span>`;
    });
}

// ── OoO view ─────────────────────────────────────────────────────
function updateOoOView(state) {
    const robDiv = document.getElementById('rob-table');
    const rsDiv = document.getElementById('rs-table');

    const robState = state['rob'];
    if (robState && robState.entries) {
        let html = '';
        robState.entries.forEach((entry, i) => {
            const ready = entry.ready ? 'rob-entry--ready' : '';
            html += `<div class="rob-entry ${ready}">`;
            html += `#${i}: ${entry.op || '?'}`;
            if (entry.dest !== undefined) html += ` rd=${entry.dest}`;
            if (entry.value !== undefined) html += ` =${entry.value}`;
            html += '</div>';
        });
        robDiv.innerHTML = html;
    } else {
        robDiv.innerHTML = '<div class="rob-entry">No ROB data</div>';
    }

    const rsState = state['rs'];
    if (rsState && rsState.entries) {
        let html = '';
        rsState.entries.forEach((entry, i) => {
            const ready = entry.ready ? 'rs-entry--ready' : '';
            html += `<div class="rs-entry ${ready}">`;
            html += `#${i}: ${entry.op || '?'}`;
            if (entry.src1 !== undefined) html += ` s1=${entry.src1}`;
            if (entry.src2 !== undefined) html += ` s2=${entry.src2}`;
            html += '</div>';
        });
        rsDiv.innerHTML = html;
    } else {
        rsDiv.innerHTML = '<div class="rs-entry">No RS data</div>';
    }
}

// ── Memory viewer ────────────────────────────────────────────────
btnMemDmem.addEventListener('click', () => switchMemView('dmem'));
btnMemImem.addEventListener('click', () => switchMemView('imem'));

function switchMemView(mode) {
    memViewMode = mode;
    btnMemDmem.classList.toggle('mem-tab--active', mode === 'dmem');
    btnMemImem.classList.toggle('mem-tab--active', mode === 'imem');
    if (cycleData.length) updateMemoryView(cycleData[currentCycle]);
}

memVisSlider.addEventListener('input', () => {
    memVisibleCount = parseInt(memVisSlider.value);
    // Force odd so center address is exact middle
    if (memVisibleCount % 2 === 0) memVisibleCount++;
    memVisCount.textContent = memVisibleCount;
    if (cycleData.length) updateMemoryView(cycleData[currentCycle]);
});

btnMemGo.addEventListener('click', () => memoryGoToSearch());
memSearch.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') memoryGoToSearch();
});

function memoryGoToSearch() {
    const raw = memSearch.value.trim();
    if (!raw) return;
    try {
        let addr;
        if (raw.toLowerCase().startsWith('0x')) {
            addr = parseInt(raw, 16);
        } else {
            addr = parseInt(raw, 10);
        }
        if (isNaN(addr) || addr < 0) return;
        // Convert byte address to word address
        memCenterAddr = addr >> 2;
        memFollow = false;  // manual Go pins the view; toggle Follow to resume tracking
        setMemFollowUI();
        if (cycleData.length) updateMemoryView(cycleData[currentCycle]);
    } catch (_) { /* ignore bad input */ }
}

// ── Memory inspector: Follow toggle + last-write readout ─────────
function setMemFollowUI() {
    if (!btnMemFollow) return;
    btnMemFollow.classList.toggle('mem-follow--on', memFollow);
    btnMemFollow.setAttribute('aria-pressed', String(memFollow));
    btnMemFollow.title = memFollow
        ? 'Following writes — auto-centering on the changed address (click to pin)'
        : 'Pinned to a fixed address (click to follow writes again)';
}

if (btnMemFollow) {
    btnMemFollow.addEventListener('click', () => {
        memFollow = !memFollow;
        if (memFollow && memLastWriteByte !== null) memCenterAddr = memLastWriteByte >> 2;
        setMemFollowUI();
        if (cycleData.length) updateMemoryView(cycleData[currentCycle]);
    });
    setMemFollowUI();
}

function _memAscii(v) {
    let s = '';
    for (let i = 0; i < 4; i++) {                 // little-endian bytes
        const c = (v >>> (i * 8)) & 0xFF;
        s += (c >= 0x20 && c < 0x7F) ? String.fromCharCode(c) : '·';
    }
    return s;
}

// Live readout of the most-recently-changed data-memory word (old -> new).
function updateMemInspectorReadout() {
    if (!memInspector) return;
    const cur = cycleData[currentCycle] && cycleData[currentCycle].dmem;
    if (memViewMode !== 'dmem' || memLastWriteByte === null || !cur || !cur.memory) {
        memInspector.hidden = true;
        return;
    }
    const word = memLastWriteByte >> 2;
    const nv = dmemWordAt(cur, word);
    let ov = 0;
    const prev = currentCycle > 0 && cycleData[currentCycle - 1] && cycleData[currentCycle - 1].dmem;
    if (prev && prev.memory) ov = dmemWordAt(prev, word);
    const hex = (v) => '0x' + v.toString(16).padStart(8, '0').toUpperCase();

    memInspector.hidden = false;
    memInspector.innerHTML =
        '<span class="mi-label">last write</span>' +
        `<span class="mi-addr">[0x${(memLastWriteByte >>> 0).toString(16).padStart(4, '0').toUpperCase()}]</span>` +
        `<span class="mi-old">${hex(ov)}</span><span class="mi-arrow">&rarr;</span>` +
        `<span class="mi-new">${hex(nv)}</span>` +
        `<span class="mi-dec">${nv}</span>` +
        `<span class="mi-ascii">&lsquo;${_memAscii(nv)}&rsquo;</span>`;

    // Re-trigger the flash animation when this word actually changed this cycle.
    if (ov !== nv) {
        memInspector.classList.remove('mem-inspector--flash');
        void memInspector.offsetWidth;
        memInspector.classList.add('mem-inspector--flash');
    }
}

function updateMemoryView(state) {
    if (memViewMode === 'imem') {
        if (memInspector) memInspector.hidden = true;  // inspector tracks data memory only
        updateImemView(state);
    } else {
        updateDmemView(state);
    }
}

function updateImemView(state) {
    // Try word-addressed IMEM first, then byte-addressed (x86)
    const imemState = state['imem'];
    if (!imemState) {
        memGrid.innerHTML = '<span style="color:var(--text-muted);font-size:0.75rem;padding:8px;">No instruction memory data</span>';
        return;
    }

    // Get current fetch PC for highlighting
    const fetchState = state['fetch'];
    let fetchPC = -1;
    if (fetchState && fetchState.pc !== undefined) {
        fetchPC = typeof fetchState.pc === 'string' ? parseInt(fetchState.pc, 16) : fetchState.pc;
    }

    if (imemState.program) {
        // Word-addressed (RISC-V, ARM)
        const prog = imemState.program;
        const half = Math.floor(memVisibleCount / 2);
        const startAddr = Math.max(0, memCenterAddr - half);
        const endAddr = Math.min(prog.length, startAddr + memVisibleCount);

        if (startAddr >= prog.length) {
            memGrid.innerHTML = `<div class="mem-oob-msg">Address out of bounds. Program size: ${prog.length} words.</div>`;
            return;
        }

        let html = '';
        for (let waddr = startAddr; waddr < endAddr; waddr++) {
            const val = prog[waddr] || 0;
            const byteAddr = waddr * 4;

            let cls = 'mem-cell';
            if (waddr === memCenterAddr) cls += ' mem-cell--center';
            if (val !== 0) cls += ' mem-cell--nonzero';
            if (byteAddr === fetchPC) cls += ' mem-cell--fetch';

            const hexVal = '0x' + ((val >>> 0) & 0xFFFFFFFF).toString(16).padStart(8, '0').toUpperCase();

            html += `<div class="${cls}">`;
            html += `<span class="mem-addr">0x${byteAddr.toString(16).padStart(4, '0')}</span>`;
            html += `<span class="mem-val">${hexVal}</span>`;
            html += '</div>';
        }
        memGrid.innerHTML = html;
    } else if (imemState.program_bytes) {
        // Byte-addressed (x86)
        const prog = imemState.program_bytes;
        // Show 4 bytes per cell for consistency
        const numWords = Math.ceil(prog.length / 4);
        const half = Math.floor(memVisibleCount / 2);
        const startAddr = Math.max(0, memCenterAddr - half);
        const endAddr = Math.min(numWords, startAddr + memVisibleCount);

        if (startAddr >= numWords) {
            memGrid.innerHTML = `<div class="mem-oob-msg">Address out of bounds. Program size: ${prog.length} bytes.</div>`;
            return;
        }

        let html = '';
        for (let waddr = startAddr; waddr < endAddr; waddr++) {
            const byteAddr = waddr * 4;
            // Pack 4 bytes LE into a word
            let val = 0;
            for (let b = 0; b < 4; b++) {
                const idx = byteAddr + b;
                if (idx < prog.length) val |= (prog[idx] & 0xFF) << (b * 8);
            }

            let cls = 'mem-cell';
            if (waddr === memCenterAddr) cls += ' mem-cell--center';
            if (val !== 0) cls += ' mem-cell--nonzero';
            if (byteAddr === fetchPC) cls += ' mem-cell--fetch';

            // Show individual bytes
            let bytesStr = '';
            for (let b = 0; b < 4; b++) {
                const idx = byteAddr + b;
                bytesStr += idx < prog.length ? ((prog[idx] & 0xFF).toString(16).padStart(2, '0')).toUpperCase() : '90';
                if (b < 3) bytesStr += ' ';
            }

            html += `<div class="${cls}">`;
            html += `<span class="mem-addr">0x${byteAddr.toString(16).padStart(4, '0')}</span>`;
            html += `<span class="mem-val">${bytesStr}</span>`;
            html += '</div>';
        }
        memGrid.innerHTML = html;
    } else {
        memGrid.innerHTML = '<span style="color:var(--text-muted);font-size:0.75rem;padding:8px;">No program data available</span>';
    }
}

// Read one data-memory word from a cycle's dmem snapshot. The snapshot is a
// dense low window (`memory`) plus a sparse high map (`memory_hi`, keyed by word
// index) so the 64 KB memory doesn't bloat every cycle — the software stack
// lives in the high map. Any consumer must go through this to see high words.
function dmemWordAt(dmemState, word) {
    const mem = dmemState.memory || [];
    if (word < mem.length) return (mem[word] >>> 0);
    const hi = dmemState.memory_hi;
    const v = hi ? hi[word] : undefined;
    return ((v === undefined || v === null) ? 0 : v) >>> 0;
}

function updateDmemView(state) {
    const dmemState = state['dmem'];
    if (!dmemState || !dmemState.memory) {
        memGrid.innerHTML = '<span style="color:var(--text-muted);font-size:0.75rem;padding:8px;">No memory data</span>';
        return;
    }

    const mem = dmemState.memory;
    const memSize = dmemState.size || mem.length;
    const half = Math.floor(memVisibleCount / 2);

    // Determine if a real memory operation is happening this cycle
    // Check decoder state for mem_read / mem_write signals
    let isMemRead = false;
    let isMemWrite = false;
    for (const key of Object.keys(state)) {
        const comp = state[key];
        if (comp && typeof comp === 'object') {
            if (comp.mem_read === 1 || comp.mem_read === true) isMemRead = true;
            if (comp.mem_write === 1 || comp.mem_write === true) isMemWrite = true;
        }
    }

    // Active address — only meaningful when a load or store is happening
    let activeWordAddr = -1;
    if ((isMemRead || isMemWrite) && dmemState.addr) {
        const addrVal = typeof dmemState.addr === 'string' ? parseInt(dmemState.addr, 16) : dmemState.addr;
        activeWordAddr = addrVal >> 2;
    }

    // Compare against previous cycle's memory to find changed cells
    let prevDmem = null;
    if (currentCycle > 0 && cycleData[currentCycle - 1]) {
        const pd = cycleData[currentCycle - 1]['dmem'];
        if (pd && pd.memory) prevDmem = pd;
    }

    // Track the word written this cycle (memory only changes via a store, so a
    // diff against the previous cycle pinpoints the written address). Auto-follow
    // recenters the view on it — "as if you ran Addr -> Go" on the live write.
    // Scan the dense window first, then the sparse high map (where the compiled
    // software stack lives) so a store high in memory still triggers auto-follow.
    let changedWord = -1;
    if (prevDmem) {
        for (let w = 0; w < mem.length; w++) {
            if (dmemWordAt(dmemState, w) !== dmemWordAt(prevDmem, w)) { changedWord = w; break; }
        }
        if (changedWord < 0) {
            const keys = new Set();
            for (const k in (dmemState.memory_hi || {})) keys.add(+k);
            for (const k in (prevDmem.memory_hi || {})) keys.add(+k);
            for (const w of keys) {
                if (dmemWordAt(dmemState, w) !== dmemWordAt(prevDmem, w)) { changedWord = w; break; }
            }
        }
    }
    if (changedWord >= 0) {
        memLastWriteByte = changedWord * 4;
        if (memFollow) memCenterAddr = changedWord;
    }
    updateMemInspectorReadout();

    // Clamp center so we don't go below 0
    const startAddr = Math.max(0, memCenterAddr - half);
    const endAddr = Math.min(memSize, startAddr + memVisibleCount);

    // Out-of-bounds check
    if (startAddr >= memSize) {
        const maxByte = (memSize - 1) * 4;
        memGrid.innerHTML = `<div class="mem-oob-msg">Address 0x${(memCenterAddr * 4).toString(16).padStart(8, '0').toUpperCase()} is out of bounds. Valid range: 0x00000000 &ndash; 0x${maxByte.toString(16).padStart(8, '0').toUpperCase()}</div>`;
        return;
    }

    let html = '';
    for (let waddr = startAddr; waddr < endAddr; waddr++) {
        const val = dmemWordAt(dmemState, waddr);
        const byteAddr = waddr * 4;

        let cls = 'mem-cell';
        if (waddr === memCenterAddr) cls += ' mem-cell--center';
        if (val !== 0) cls += ' mem-cell--nonzero';

        // Highlight writes (rose) and reads (amber) only for real memory ops
        if (waddr === activeWordAddr) {
            if (isMemWrite) cls += ' mem-cell--write';
            else if (isMemRead) cls += ' mem-cell--active';
        }

        // Highlight cells that changed from previous cycle (teal)
        if (prevDmem && dmemWordAt(prevDmem, waddr) !== val) {
            cls += ' mem-cell--changed';
        }

        const hexVal = '0x' + ((val >>> 0) & 0xFFFFFFFF).toString(16).padStart(8, '0').toUpperCase();
        const decVal = val === 0 ? '0' : (val >>> 0).toString(10);

        html += `<div class="${cls}">`;
        html += `<span class="mem-addr">0x${byteAddr.toString(16).padStart(4, '0')}</span>`;
        html += `<span class="mem-val">${hexVal}</span>`;
        html += `<span class="mem-dec">${decVal}</span>`;
        html += '</div>';
    }

    memGrid.innerHTML = html;

    // Scroll to keep the center cell visible
    const centerIdx = memCenterAddr - startAddr;
    if (centerIdx >= 0 && centerIdx < memVisibleCount) {
        const cells = memGrid.children;
        if (cells[centerIdx]) {
            cells[centerIdx].scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
        }
    }
}

// ── Component detail panel ────────────────────────────────────────
btnCloseDetail.addEventListener('click', () => closeDetailPanel());
detailOverlay.addEventListener('click', () => closeDetailPanel());

// Listen for custom event from layout engine
document.addEventListener('comp-detail-click', (e) => {
    openDetailPanel(e.detail.compId, e.detail.label);
});

function openDetailPanel(compId, label) {
    detailCompId = compId;
    detailCompLabel = label;
    detailTitle.textContent = label || compId;
    detailPanelOpen = true;
    detailPanel.classList.add('active');
    detailOverlay.classList.add('active');
    if (cycleData.length) {
        renderDetailContent(compId, cycleData[currentCycle]);
    }
}

function closeDetailPanel() {
    detailPanelOpen = false;
    detailPanel.classList.remove('active');
    detailOverlay.classList.remove('active');
    if (layoutEngine) layoutEngine.clearSelection();
}

function renderDetailContent(compId, state) {
    const compState = state[compId];
    if (!compState) {
        detailContent.innerHTML = '<p style="color:var(--text-muted)">No state data for this component.</p>';
        return;
    }

    let html = '';

    // Check for register array
    if (compState.registers && Array.isArray(compState.registers)) {
        html += renderDetailRegisters(compState.registers);
    }

    // Check for memory array
    if (compState.memory && Array.isArray(compState.memory)) {
        html += renderDetailMemory(compState);
    }

    // Check for program array (IMEM)
    if (compState.program && Array.isArray(compState.program)) {
        html += renderDetailProgram(compState.program, state);
    }
    if (compState.program_bytes && Array.isArray(compState.program_bytes)) {
        html += renderDetailProgramBytes(compState.program_bytes, state);
    }

    // Check for entries array (ROB, RS)
    if (compState.entries && Array.isArray(compState.entries)) {
        html += renderDetailEntries(compState.entries);
    }

    // Check for lane_N objects (superscalar pipeline registers)
    const laneKeys = Object.keys(compState).filter(k => k.startsWith('lane_')).sort();
    if (laneKeys.length > 0) {
        html += '<div class="detail-section"><div class="detail-section__title">Lanes</div>';
        for (const lk of laneKeys) {
            const lane = compState[lk];
            html += `<div style="margin-bottom:8px"><strong style="color:var(--accent);font-size:0.72rem;">${lk.toUpperCase()}</strong>`;
            html += '<div>';
            for (const [k, v] of Object.entries(lane)) {
                html += `<div class="detail-kv"><span class="detail-kv__key">${k}</span><span class="detail-kv__val">${formatDetailValue(v)}</span></div>`;
            }
            html += '</div></div>';
        }
        html += '</div>';
    }

    // Check for hazard conflicting registers
    if (compState.conflicting_regs && Array.isArray(compState.conflicting_regs)) {
        html += '<div class="detail-section"><div class="detail-section__title" style="color:var(--rose)">Hazard Detail</div>';
        html += `<div class="detail-kv"><span class="detail-kv__key">Type</span><span class="detail-kv__val" style="color:var(--rose)">${compState.hazard_type || 'RAW'}</span></div>`;
        const rdIdx = compState.stall_rd;
        const rdName = (currentRegNames.length > rdIdx) ? currentRegNames[rdIdx] : `r${rdIdx}`;
        html += `<div class="detail-kv"><span class="detail-kv__key">Load Dest</span><span class="detail-kv__val" style="color:var(--rose)">${rdName} (r${rdIdx})</span></div>`;
        html += `<div class="detail-kv"><span class="detail-kv__key">Waiting On</span><span class="detail-kv__val" style="color:var(--rose)">`;
        html += compState.conflicting_regs.map(r => {
            const name = (currentRegNames.length > r) ? currentRegNames[r] : `r${r}`;
            return `${name} (r${r})`;
        }).join(', ');
        html += '</span></div></div>';
    }

    // Scalar fields
    const skipKeys = new Set(['registers', 'memory', 'memory_hi', 'window', 'program', 'program_bytes', 'entries', 'size',
                              'conflicting_regs', 'hazard_type', 'stall_rd', ...laneKeys]);
    const scalarKeys = Object.keys(compState).filter(k => !skipKeys.has(k));
    if (scalarKeys.length > 0) {
        html += '<div class="detail-section"><div class="detail-section__title">Properties</div>';
        for (const k of scalarKeys) {
            html += `<div class="detail-kv"><span class="detail-kv__key">${k}</span><span class="detail-kv__val">${formatDetailValue(compState[k])}</span></div>`;
        }
        html += '</div>';
    }

    detailContent.innerHTML = html;
}

function formatDetailValue(v) {
    if (typeof v === 'number') {
        return `0x${(v >>> 0).toString(16).toUpperCase().padStart(8, '0')}  (${v})`;
    }
    return String(v);
}

function renderDetailRegisters(regs) {
    let html = '<div class="detail-section"><div class="detail-section__title">Registers</div>';
    html += '<table class="detail-table"><thead><tr><th>#</th><th>Name</th><th>Hex</th><th>Dec</th></tr></thead><tbody>';
    const prev = prevCycleRegs();
    for (let i = 0; i < regs.length; i++) {
        const name = (currentRegNames.length > i) ? currentRegNames[i] : `r${i}`;
        const val = regs[i];
        const rawVal = typeof val === 'string' ? parseInt(val, 16) : val;
        const isNonZero = rawVal !== 0;
        const changed = prev && prev[i] !== val;
        let cls = '';
        if (changed) cls = 'detail-row--changed';
        else if (isNonZero) cls = 'detail-row--nonzero';
        const hexStr = typeof val === 'string' ? val : `0x${(val >>> 0).toString(16).padStart(8, '0').toUpperCase()}`;
        const decStr = typeof val === 'string' ? parseInt(val, 16) : val;
        html += `<tr class="${cls}"><td>${i}</td><td>${name}</td><td>${hexStr}</td><td>${decStr}</td></tr>`;
    }
    html += '</tbody></table></div>';
    return html;
}

function renderDetailMemory(dmemState) {
    const mem = dmemState.memory || [];
    const hi = dmemState.memory_hi || {};
    // Show only non-zero entries, dense window + sparse high map, in order.
    const nonZero = [];
    for (let i = 0; i < mem.length; i++) {
        if (mem[i] !== 0) nonZero.push({ addr: i, val: mem[i] });
    }
    for (const k in hi) {
        if (hi[k] !== 0) nonZero.push({ addr: +k, val: hi[k] });
    }
    nonZero.sort((a, b) => a.addr - b.addr);

    let html = '<div class="detail-section"><div class="detail-section__title">Memory</div>';
    if (nonZero.length === 0) {
        html += '<p style="color:var(--text-muted);font-size:0.75rem;">All zeros</p>';
    } else {
        html += '<table class="detail-table"><thead><tr><th>Addr</th><th>Hex</th><th>Dec</th></tr></thead><tbody>';
        for (const entry of nonZero) {
            const byteAddr = entry.addr * 4;
            const hexStr = `0x${(entry.val >>> 0).toString(16).padStart(8, '0').toUpperCase()}`;
            html += `<tr class="detail-row--nonzero"><td>0x${byteAddr.toString(16).padStart(4, '0')}</td><td>${hexStr}</td><td>${entry.val}</td></tr>`;
        }
        html += '</tbody></table>';
    }
    const total = dmemState.size || mem.length;
    html += `<p style="color:var(--text-dim);font-size:0.65rem;margin-top:4px;">${total} words total</p></div>`;
    return html;
}

function renderDetailProgram(prog, state) {
    const fetchState = state['fetch'];
    let fetchPC = -1;
    if (fetchState && fetchState.pc !== undefined) {
        fetchPC = typeof fetchState.pc === 'string' ? parseInt(fetchState.pc, 16) : fetchState.pc;
    }

    let html = '<div class="detail-section"><div class="detail-section__title">Program</div>';
    html += '<table class="detail-table"><thead><tr><th>Addr</th><th>Instruction</th></tr></thead><tbody>';
    for (let i = 0; i < prog.length; i++) {
        const byteAddr = i * 4;
        const hexStr = `0x${(prog[i] >>> 0).toString(16).padStart(8, '0').toUpperCase()}`;
        const cls = byteAddr === fetchPC ? 'detail-row--changed' : 'detail-row--nonzero';
        html += `<tr class="${cls}"><td>0x${byteAddr.toString(16).padStart(4, '0')}</td><td>${hexStr}</td></tr>`;
    }
    html += '</tbody></table></div>';
    return html;
}

function renderDetailProgramBytes(prog, state) {
    const fetchState = state['fetch'];
    let fetchPC = -1;
    if (fetchState && fetchState.pc !== undefined) {
        fetchPC = typeof fetchState.pc === 'string' ? parseInt(fetchState.pc, 16) : fetchState.pc;
    }

    let html = '<div class="detail-section"><div class="detail-section__title">Program Bytes</div>';
    html += '<table class="detail-table"><thead><tr><th>Addr</th><th>Bytes</th></tr></thead><tbody>';
    // Group by 4 bytes
    for (let i = 0; i < prog.length; i += 4) {
        let bytesStr = '';
        for (let b = 0; b < 4 && (i + b) < prog.length; b++) {
            bytesStr += ((prog[i + b] & 0xFF).toString(16).padStart(2, '0')).toUpperCase() + ' ';
        }
        const cls = i === fetchPC ? 'detail-row--changed' : 'detail-row--nonzero';
        html += `<tr class="${cls}"><td>0x${i.toString(16).padStart(4, '0')}</td><td>${bytesStr.trim()}</td></tr>`;
    }
    html += '</tbody></table></div>';
    return html;
}

function renderDetailEntries(entries) {
    if (!entries.length) return '<div class="detail-section"><div class="detail-section__title">Entries</div><p style="color:var(--text-muted);font-size:0.75rem;">Empty</p></div>';

    // Collect all keys across entries
    const allKeys = new Set();
    entries.forEach(e => Object.keys(e).forEach(k => allKeys.add(k)));
    const keys = [...allKeys];

    let html = '<div class="detail-section"><div class="detail-section__title">Entries</div>';
    html += '<table class="detail-table"><thead><tr><th>#</th>';
    for (const k of keys) html += `<th>${k}</th>`;
    html += '</tr></thead><tbody>';
    entries.forEach((entry, i) => {
        const ready = entry.ready ? 'detail-row--nonzero' : '';
        html += `<tr class="${ready}"><td>${i}</td>`;
        for (const k of keys) {
            html += `<td>${entry[k] !== undefined ? formatDetailValue(entry[k]) : '-'}</td>`;
        }
        html += '</tr>';
    });
    html += '</tbody></table></div>';
    return html;
}

// ── Branch predictor loader ──────────────────────────────────────
async function loadPredictors() {
    try {
        const res = await fetch(`${API}/predictors`);
        const data = await res.json();
        // Clear all except the "None" option
        while (bpSel.options.length > 1) bpSel.remove(1);
        for (const p of data.predictors) {
            const opt = document.createElement('option');
            opt.value = p.name;
            opt.textContent = p.label;
            bpSel.appendChild(opt);
        }
        // Restore saved predictor, or default to always_taken
        const savedBp = localStorage.getItem('cpu_sim_bp');
        bpSel.value = savedBp || 'always_taken';
        if (!bpSel.value || bpSel.selectedIndex < 0) bpSel.selectedIndex = 0;
        // Sync stage toggle UI to restored bpStage
        bpStageBtns.forEach(b => {
            b.classList.toggle('toggle-btn--active', b.dataset.bpStage === bpStage);
        });
        updateBpStageVisibility();
    } catch (e) {
        console.error('Failed to load predictors:', e);
    }
}

// ── Prediction-stage toggle ──────────────────────────────────────
function updateBpStageVisibility() {
    const show = bpSel.value && (currentModel === 'pipeline' || currentModel === 'superscalar');
    bpStageCtrl.style.display = show ? '' : 'none';
}

bpStageBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        bpStageBtns.forEach(b => b.classList.remove('toggle-btn--active'));
        btn.classList.add('toggle-btn--active');
        bpStage = btn.dataset.bpStage;
        localStorage.setItem('cpu_sim_bp_stage', bpStage);
    });
});

bpSel.addEventListener('change', () => {
    localStorage.setItem('cpu_sim_bp', bpSel.value);
    updateBpStageVisibility();
});

// ── Instruction listing ──────────────────────────────────────────
const BADGE_COLORS = {
    IF:  '#60a5fa', // accent blue
    ID:  '#2dd4bf', // teal
    EX:  '#a78bfa', // purple
    MEM: '#fbbf24', // amber
    WB:  '#4ade80', // green
    ROB: '#fb923c', // orange
    ACT: '#60a5fa', // single-cycle active
};

/**
 * Estimate x86 instruction byte size from assembly text.
 * Must match the x86 assembler's actual encoding sizes.
 */
function _estimateX86Size(line) {
    const code = line.replace(/;.*$/, '').trim().replace(/^\w+:\s*/, '');
    if (!code) return 1;
    const parts = code.split(/[,\s]+/).filter(Boolean);
    const mnem = parts[0].toUpperCase();

    // NOP = 1 byte
    if (mnem === 'NOP') return 1;
    // RET = 1 byte
    if (mnem === 'RET') return 1;
    // PUSH/POP reg = 1 byte
    if (mnem === 'PUSH' || mnem === 'POP') return 1;

    // JMP/Jcc rel8 = 2 bytes
    if (/^J/.test(mnem) && mnem !== 'JALR') return 2;

    // CALL rel32 = 5 bytes
    if (mnem === 'CALL') return 5;

    if (parts.length < 2) return 2;
    const dst = parts[1];
    const src = parts.length > 2 ? parts[2] : null;

    // MOV reg, imm32 = 5 bytes (B8+rd imm32)
    if (mnem === 'MOV' && src && /^\d|^-|^0x/.test(src) && !/^\[/.test(dst)) return 5;
    // MOV reg, reg = 2 bytes
    if (mnem === 'MOV' && src && /^E[A-Z]{2}$/i.test(src) && /^E[A-Z]{2}$/i.test(dst)) return 2;
    // MOV reg, [reg+off] or MOV [reg+off], reg = 2-3 bytes
    if (mnem === 'MOV' && src && (/\[/.test(src) || /\[/.test(dst))) {
        const memOp = /\[/.test(src) ? src : dst;
        return /\+/.test(memOp) ? 3 : 2;
    }

    // ALU reg, imm8 (ADD/SUB/CMP/AND/OR/XOR reg, imm) = 3 bytes (83 modrm imm8)
    if (src && /^\d|^-|^0x/.test(src)) return 3;
    // ALU reg, reg = 2 bytes
    if (src && /^E[A-Z]{2}$/i.test(src)) return 2;

    return 2; // fallback
}

function buildInstructionListing() {
    instructionListing = [];
    const text = progInput.value;
    const lines = text.split('\n');

    if (currentInputMode === 'asm') {
        // Assembly mode: skip labels, blanks, comment-only lines
        let addr = 0;
        const isX86 = currentISA === 'x86';
        for (const raw of lines) {
            const code = raw.replace(/;.*$/, '').replace(/#.*$/, '').trim();
            if (!code) continue;
            // Labels end with ':'
            if (/^\w+:\s*$/.test(code)) continue;
            // Keep the full line (with comments), just strip any leading label
            let display = raw.trim().replace(/^\w+:\s*/, '');
            instructionListing.push({ addr, text: display });
            addr += isX86 ? _estimateX86Size(raw) : 4;
        }
    } else {
        // Hex mode
        if (currentProgramFormat === 'bytes') {
            // x86 byte format: count bytes per line
            let addr = 0;
            for (const raw of lines) {
                const stripped = raw.split('#')[0].split(';')[0].trim();
                if (!stripped) continue;
                const tokens = stripped.split(/\s+/).filter(t => t);
                const byteCount = tokens.length;
                const hexStr = tokens.join(' ');
                const comment = raw.includes('#') ? raw.split('#')[1].trim() : '';
                instructionListing.push({
                    addr,
                    text: comment || hexStr,
                    bytes: byteCount,
                });
                addr += byteCount;
            }
        } else {
            // Word format (RISC-V, ARM): 4 bytes each
            let addr = 0;
            for (const raw of lines) {
                const stripped = raw.split('#')[0].trim();
                if (!stripped) continue;
                const comment = raw.includes('#') ? raw.split('#')[1].trim() : '';
                instructionListing.push({
                    addr,
                    text: comment || stripped,
                });
                addr += 4;
            }
        }
    }
}

function _pcToNum(pcVal) {
    if (typeof pcVal === 'string') return parseInt(pcVal, 16);
    return pcVal >>> 0;
}

function computePipelineBadges(state) {
    // Returns Map<addr_number, [{label, color}]>
    const badges = new Map();
    function addBadge(pc, label, color) {
        const addr = _pcToNum(pc);
        if (!badges.has(addr)) badges.set(addr, []);
        badges.get(addr).push({ label, color });
    }

    if (currentModel === 'single_cycle') {
        const fetch = state['fetch'];
        if (fetch && fetch.pc !== undefined) {
            addBadge(fetch.pc, 'Active', BADGE_COLORS.ACT);
        }
    } else if (currentModel === 'multicycle') {
        const ctrl = state['mc_ctrl'];
        const pcLatch = state['pc_latch'];
        if (ctrl && pcLatch && pcLatch.pc) {
            const phaseLabels = ['FET', 'DEC', 'EXE', 'MEM'];
            const phaseColors = [BADGE_COLORS.IF, BADGE_COLORS.ID, BADGE_COLORS.EX, BADGE_COLORS.MEM];
            const phase = ctrl.phase;
            addBadge(pcLatch.pc, phaseLabels[phase], phaseColors[phase]);
        }
    } else if (currentModel === 'pipeline') {
        // Fetch stage
        const fetch = state['fetch'];
        if (fetch && fetch.pc !== undefined) addBadge(fetch.pc, 'IF', BADGE_COLORS.IF);
        // IF/ID
        const ifid = state['if_id'];
        if (ifid && ifid.pc && ifid.valid !== 'BUBBLE') addBadge(ifid.pc, 'ID', BADGE_COLORS.ID);
        // ID/EX
        const idex = state['id_ex'];
        if (idex && idex.pc && idex.valid !== 'BUBBLE') addBadge(idex.pc, 'EX', BADGE_COLORS.EX);
        // EX/MEM
        const exmem = state['ex_mem'];
        if (exmem && exmem.pc && exmem.valid !== 'BUBBLE') addBadge(exmem.pc, 'MEM', BADGE_COLORS.MEM);
        // MEM/WB
        const memwb = state['mem_wb'];
        if (memwb && memwb.pc && memwb.valid !== 'BUBBLE') addBadge(memwb.pc, 'WB', BADGE_COLORS.WB);
    } else if (currentModel === 'ooo') {
        const fetch = state['fetch'];
        if (fetch && fetch.pc !== undefined) addBadge(fetch.pc, 'IF', BADGE_COLORS.IF);
        // ROB entries
        const rob = state['rob'];
        if (rob && rob.entries) {
            rob.entries.forEach((entry, i) => {
                if (entry.valid && entry.pc !== undefined) {
                    const label = entry.ready ? `ROB #${i} (ready)` : `ROB #${i}`;
                    addBadge(entry.pc, label, BADGE_COLORS.ROB);
                }
            });
        }
    } else if (currentModel === 'superscalar') {
        // Fetch — add badge for each lane's PC
        const fetch = state['fetch'];
        if (fetch) {
            for (let i = 0; i < numLanes; i++) {
                const lanePC = fetch[`pc_lane_${i}`];
                if (lanePC !== undefined) {
                    addBadge(lanePC, `IF L${i}`, BADGE_COLORS.IF);
                }
            }
        }
        // Wide pipeline registers: if_id, id_ex, ex_mem, mem_wb each have lane_N
        const stageMap = [
            { comp: 'if_id',   stage: 'ID',  color: BADGE_COLORS.ID },
            { comp: 'id_ex',   stage: 'EX',  color: BADGE_COLORS.EX },
            { comp: 'ex_mem',  stage: 'MEM', color: BADGE_COLORS.MEM },
            { comp: 'mem_wb',  stage: 'WB',  color: BADGE_COLORS.WB },
        ];
        for (const { comp, stage, color } of stageMap) {
            const cs = state[comp];
            if (!cs) continue;
            for (let i = 0; i < numLanes; i++) {
                const lane = cs[`lane_${i}`];
                if (lane && lane.pc && lane.valid !== 'BUBBLE') {
                    addBadge(lane.pc, `${stage} L${i}`, color);
                }
            }
        }
    }

    return badges;
}

function buildInstrMap(state) {
    if (!instructionListing.length) return {};

    // PC → instruction text lookup
    const pcToInstr = {};
    for (const entry of instructionListing) {
        pcToInstr[entry.addr] = entry.text;
    }

    function lookup(pcField, validField) {
        if (validField === 'BUBBLE') return '';
        if (!pcField && pcField !== 0) return '';
        const addr = _pcToNum(pcField);
        return pcToInstr[addr] || '';
    }

    const map = {};

    if (currentModel === 'single_cycle') {
        const instr = lookup(state.fetch?.pc);
        for (const id of Object.keys(state)) {
            if (id !== '_cycle') map[id] = instr;
        }
    } else if (currentModel === 'multicycle') {
        const pcLatch = state['pc_latch'];
        const instr = pcLatch ? lookup(pcLatch.pc) : '';
        for (const id of Object.keys(state)) {
            if (id !== '_cycle') map[id] = instr;
        }
    } else if (currentModel === 'pipeline') {
        const ifInstr  = lookup(state.fetch?.pc);
        const idInstr  = lookup(state.if_id?.pc,  state.if_id?.valid);
        const exInstr  = lookup(state.id_ex?.pc,   state.id_ex?.valid);
        const memInstr = lookup(state.ex_mem?.pc,  state.ex_mem?.valid);
        const wbInstr  = lookup(state.mem_wb?.pc,  state.mem_wb?.valid);

        map['fetch'] = ifInstr;  map['imem'] = ifInstr;
        map['if_id'] = idInstr;  map['decode'] = idInstr; map['regfile'] = idInstr;
        map['id_ex'] = exInstr;  map['forwarding'] = exInstr;
        map['alu_mux'] = exInstr; map['alu'] = exInstr;
        map['ex_mem'] = memInstr; map['branch'] = memInstr; map['dmem'] = memInstr;
        map['mem_wb'] = wbInstr;  map['wb'] = wbInstr;
    } else if (currentModel === 'superscalar') {
        const ifInstr = lookup(state.fetch?.pc);
        map['fetch'] = ifInstr; map['imem'] = ifInstr;

        // Wide pipeline registers: show all valid lane instructions joined
        const wideRegs = ['if_id', 'id_ex', 'ex_mem', 'mem_wb'];
        for (const reg of wideRegs) {
            const cs = state[reg];
            if (!cs) continue;
            const parts = [];
            for (let i = 0; i < numLanes; i++) {
                const lane = cs[`lane_${i}`];
                if (lane && lane.valid !== 'BUBBLE') {
                    parts.push(`L${i}:` + lookup(lane.pc));
                }
            }
            map[reg] = parts.filter(p => !p.endsWith(':')).join(' | ');
        }

        // Per-lane decode/alu/wb components
        for (let i = 0; i < numLanes; i++) {
            const ifidLane = state.if_id?.[`lane_${i}`];
            const idInstr = ifidLane && ifidLane.valid !== 'BUBBLE' ? lookup(ifidLane.pc) : '';
            map[`decode_${i}`] = idInstr;

            const idexLane = state.id_ex?.[`lane_${i}`];
            const exInstr = idexLane && idexLane.valid !== 'BUBBLE' ? lookup(idexLane.pc) : '';
            map[`alu_mux_${i}`] = exInstr;
            map[`alu_${i}`] = exInstr;

            const memwbLane = state.mem_wb?.[`lane_${i}`];
            const wbInstr = memwbLane && memwbLane.valid !== 'BUBBLE' ? lookup(memwbLane.pc) : '';
            map[`wb_${i}`] = wbInstr;
        }
    } else if (currentModel === 'ooo') {
        const ifInstr = lookup(state.fetch?.pc);
        map['fetch'] = ifInstr; map['imem'] = ifInstr;
        map['decode'] = ifInstr;
        // ROB/RS/RAT are shared, don't assign a single instruction
    }

    return map;
}

function renderProgramListing(state) {
    if (!instructionListing.length) return;
    const badges = computePipelineBadges(state);

    // Build set of all active fetch PCs (single PC for most models, N for superscalar)
    const fetchPCs = new Set();
    const fetch = state['fetch'];
    if (fetch) {
        if (currentModel === 'superscalar') {
            for (let i = 0; i < numLanes; i++) {
                const lpc = fetch[`pc_lane_${i}`];
                if (lpc !== undefined) fetchPCs.add(_pcToNum(lpc));
            }
        } else if (fetch.pc !== undefined) {
            fetchPCs.add(_pcToNum(fetch.pc));
        }
    }

    // Detect hazard registers for highlighting
    const hazard = state['hazard_det'];
    const hazardRegs = new Set();
    let stalledPC = -1;
    if (hazard && hazard.stall === 'STALL' && hazard.conflicting_regs) {
        for (const r of hazard.conflicting_regs) {
            hazardRegs.add(r);
        }
        // The stalled instruction is in IF/ID
        const ifid = state['if_id'];
        if (ifid && ifid.valid !== 'BUBBLE') {
            stalledPC = _pcToNum(ifid.pc);
        }
    }

    // Build register name set for highlighting
    const hazardRegNames = new Set();
    for (const r of hazardRegs) {
        // Add all forms: x1/X1/r1/R1 for RISC-V, X1 for ARM, eax/EAX for x86
        if (currentRegNames.length > r) {
            hazardRegNames.add(currentRegNames[r].toLowerCase());
        }
        hazardRegNames.add(`x${r}`);
        hazardRegNames.add(`r${r}`);
    }

    let html = '';
    for (const entry of instructionListing) {
        const isFetch = fetchPCs.has(entry.addr);
        const isStalled = entry.addr === stalledPC;
        let rowCls = 'plist-row';
        if (isStalled) rowCls += ' plist-row--stall';
        else if (isFetch) rowCls += ' plist-row--fetch';
        const addrHex = entry.addr.toString(16).padStart(4, '0');

        let badgeHtml = '';
        const entryBadges = badges.get(entry.addr);
        if (entryBadges) {
            for (const b of entryBadges) {
                badgeHtml += `<span class="plist-badge" style="--badge-color:${b.color}">${b.label}</span>`;
            }
        }
        if (isStalled) {
            badgeHtml += `<span class="plist-badge" style="--badge-color:var(--rose)">STALL</span>`;
        }

        // Highlight conflicting registers in the instruction text
        let instrHtml = escapeHtml(entry.text);
        if (isStalled && hazardRegNames.size > 0) {
            instrHtml = highlightHazardRegs(instrHtml, hazardRegNames);
        }

        html += `<div class="${rowCls}">`;
        html += `<span class="plist-addr">${addrHex}</span>`;
        html += `<span class="plist-instr">${instrHtml}</span>`;
        html += `<span class="plist-badges">${badgeHtml}</span>`;
        html += '</div>';
    }
    progListing.innerHTML = html;
}

function highlightHazardRegs(html, hazardRegNames) {
    // Match register operands (word boundaries) and wrap matches in highlight span
    return html.replace(/\b([A-Za-z]+\d+)\b/g, (match) => {
        if (hazardRegNames.has(match.toLowerCase())) {
            return `<span class="plist-hazard-reg">${match}</span>`;
        }
        return match;
    });
}

function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function showProgramListing() {
    if (!listingVisible && instructionListing.length) {
        progInput.style.display = 'none';
        progListing.style.display = 'block';
        listingVisible = true;
    }
}

function hideProgramListing() {
    progInput.style.display = '';
    progListing.style.display = 'none';
    listingVisible = false;
}

// Click listing to go back to edit mode
progListing.addEventListener('click', () => hideProgramListing());

// ── Program parsing ──────────────────────────────────────────────
function parseProgram() {
    const lines = progInput.value.split('\n');
    const program = [];

    if (currentProgramFormat === 'bytes') {
        for (const line of lines) {
            const trimmed = line.split('#')[0].split(';')[0].trim();
            if (!trimmed) continue;
            const tokens = trimmed.split(/\s+/);
            for (const token of tokens) {
                if (token) program.push(parseInt(token, 16));
            }
        }
    } else {
        for (const line of lines) {
            const trimmed = line.split('#')[0].trim();
            if (trimmed) program.push(trimmed);
        }
    }
    return program;
}

// ── API calls ────────────────────────────────────────────────────
async function loadTopology() {
    const preset = getPresetName();
    try {
        let url = `${API}/topology/${preset}`;
        const params = new URLSearchParams();
        if (currentModel === 'superscalar') params.set('num_lanes', numLanes);
        if (bpSel.value) {
            params.set('branch_predictor', bpSel.value);
            params.set('prediction_stage', bpStage);
        }
        if (params.toString()) url += `?${params}`;
        const res = await fetch(url);
        if (!res.ok) {
            const err = await res.json();
            console.warn('Topology load failed:', err.error || res.statusText);
            svg.selectAll('*').remove();
            return;
        }
        const topo = await res.json();
        renderTopology(topo);
    } catch (e) {
        console.error('Failed to load topology:', e);
    }
}

async function runSimulation() {
    // Source (C) mode: Run means compile-and-run — the editor holds C source,
    // which must never reach the assembler or the hex parser. compileAndRun
    // switches to Assembly mode itself before re-invoking us (no recursion).
    if (currentInputMode === 'c' &&
            typeof CompilerTab !== 'undefined' && CompilerTab.compileAndRun) {
        await CompilerTab.compileAndRun();
        return;
    }
    const preset = getPresetName();
    const autoCycles = !!(autoCyclesChk && autoCyclesChk.checked);
    const cycles = Math.max(1, Math.min(parseInt(numCyclesIn.value) || 20, 2000));

    const body = { preset, cycles, num_lanes: numLanes };
    if (autoCycles) body.run_to_completion = true;
    if (currentModel === 'configurable') body.cycle_costs = cfgCosts();

    const bpValue = bpSel.value;
    if (bpValue) {
        body.branch_predictor = bpValue;
        body.prediction_stage = bpStage;
    }

    if (currentInputMode === 'asm') {
        body.input_mode = 'asm';
        body.asm_text = progInput.value;
    } else {
        body.program = parseProgram();
    }

    try {
        btnRun.disabled = true;
        btnRun.textContent = 'Running...';
        const res = await fetch(`${API}/simulate`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        });
        const data = await res.json();
        if (data.error) {
            alert(data.error);
            return;
        }

        if (data.reg_names) currentRegNames = data.reg_names;

        cycleData = data.cycles;
        if (data.time_model) updateCfgReadout(data.time_model);
        // Auto mode: report how many cycles the run actually took (and warn
        // if the program never settled within the server's 10k-cycle cap).
        if (autoCycles && numCyclesIn) {
            numCyclesIn.value = Math.max(0, cycleData.length - 1);
            if (data.completed === false) {
                console.warn('Run did not settle within the 10,000-cycle cap;' +
                             ' showing the first 10,000 cycles.');
            }
        }
        currentCycle = 0;
        slider.max = cycleData.length - 1;
        slider.disabled = false;
        btnPrev.disabled = false;
        btnNext.disabled = false;
        btnPlay.disabled = false;

        // Build instruction listing and show it
        buildInstructionListing();
        showProgramListing();

        displayCycle(0);
    } catch (e) {
        console.error('Simulation failed:', e);
        alert('Simulation failed: ' + e.message);
    } finally {
        btnRun.disabled = false;
        btnRun.textContent = 'Run';
    }
}

// ── Event handlers ───────────────────────────────────────────────
btnRun.addEventListener('click', async () => {
    if (!topology) await loadTopology();
    await runSimulation();
});

slider.addEventListener('input', () => displayCycle(parseInt(slider.value)));
btnPrev.addEventListener('click', () => displayCycle(currentCycle - 1));
btnNext.addEventListener('click', () => displayCycle(currentCycle + 1));
btnPlay.addEventListener('click', () => {
    if (playing) {
        playing = false;
        clearInterval(playTimer);
        btnPlay.innerHTML = '&#9654; Play';
    } else {
        playing = true;
        btnPlay.innerHTML = '&#9646;&#9646; Pause';
        playTimer = setInterval(() => {
            if (currentCycle >= cycleData.length - 1) {
                playing = false;
                clearInterval(playTimer);
                btnPlay.innerHTML = '&#9654; Play';
                return;
            }
            displayCycle(currentCycle + 1);
        }, 400);
    }
});

// Keyboard shortcuts
document.addEventListener('keydown', e => {
    // Close full-screen editor on Escape (even from within textarea)
    if (e.key === 'Escape' && fsOverlay.classList.contains('active')) {
        closeFullscreenEditor(false);
        return;
    }
    if (e.key === 'Escape' && exampleOverlay.classList.contains('active')) {
        closeExamplesModal();
        return;
    }
    if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;
    if (e.key === 'ArrowLeft')  displayCycle(currentCycle - 1);
    if (e.key === 'ArrowRight') displayCycle(currentCycle + 1);
    if (e.key === ' ') { e.preventDefault(); btnPlay.click(); }
    if (e.key === 'Escape') {
        if (detailPanelOpen) closeDetailPanel();
        else toggleCheatsheet(false);
    }
});

// ── Copy-to-clipboard buttons ────────────────────────────────────
function flashCopied(btn) {
    btn.classList.add('copied');
    btn.textContent = 'Copied!';
    setTimeout(() => {
        btn.classList.remove('copied');
        btn.textContent = 'Copy';
    }, 1200);
}

document.getElementById('btn-copy-code').addEventListener('click', () => {
    const text = progInput.value;
    navigator.clipboard.writeText(text).then(() => {
        flashCopied(document.getElementById('btn-copy-code'));
    });
});

document.getElementById('btn-copy-regs').addEventListener('click', () => {
    if (!cycleData.length) return;
    const state = cycleData[currentCycle];
    let text = `Cycle ${currentCycle} — Registers\n`;
    for (const key of Object.keys(state)) {
        const comp = state[key];
        if (comp && typeof comp === 'object' && comp.registers) {
            const regs = comp.registers;
            for (let i = 0; i < regs.length; i++) {
                const name = i < currentRegNames.length ? currentRegNames[i] : `r${i}`;
                const hex = '0x' + ((regs[i] >>> 0) & 0xFFFFFFFF).toString(16).padStart(8, '0').toUpperCase();
                text += `${name.padEnd(6)} ${hex}  (${regs[i]})\n`;
            }
            break;
        }
    }
    navigator.clipboard.writeText(text).then(() => {
        flashCopied(document.getElementById('btn-copy-regs'));
    });
});

document.getElementById('btn-copy-mem').addEventListener('click', () => {
    if (!cycleData.length) return;
    const state = cycleData[currentCycle];
    const label = memViewMode === 'dmem' ? 'Data Memory' : 'Instruction Memory';
    let text = `Cycle ${currentCycle} — ${label}\n`;
    if (memViewMode === 'dmem') {
        const dmem = state['dmem'];
        if (dmem && dmem.memory) {
            const mem = dmem.memory;
            const hi = dmem.memory_hi || {};
            const cells = [];
            for (let i = 0; i < mem.length; i++) if (mem[i] !== 0) cells.push([i, mem[i]]);
            for (const k in hi) if (hi[k] !== 0) cells.push([+k, hi[k]]);
            cells.sort((a, b) => a[0] - b[0]);
            for (const [i, v] of cells) {
                const addr = '0x' + (i * 4).toString(16).padStart(4, '0');
                const hex = '0x' + ((v >>> 0) & 0xFFFFFFFF).toString(16).padStart(8, '0').toUpperCase();
                text += `${addr}: ${hex}  (${v})\n`;
            }
            if (!cells.length) text += '(all zeros)\n';
        }
    } else {
        const imem = state['imem'];
        if (imem && imem.program) {
            for (let i = 0; i < imem.program.length; i++) {
                const addr = '0x' + (i * 4).toString(16).padStart(4, '0');
                const hex = '0x' + ((imem.program[i] >>> 0) & 0xFFFFFFFF).toString(16).padStart(8, '0').toUpperCase();
                text += `${addr}: ${hex}\n`;
            }
        }
    }
    navigator.clipboard.writeText(text).then(() => {
        flashCopied(document.getElementById('btn-copy-mem'));
    });
});

// ── Initialization ───────────────────────────────────────────────
async function init() {
    try {
        const res = await fetch(`${API}/isa/${currentISA}`);
        const info = await res.json();
        currentRegNames = info.reg_names;
        currentProgramFormat = info.program_format;
        // Default to assembly mode with assembly text
        if (info.demo_program_asm) {
            progInput.value = info.demo_program_asm;
            switchInputMode('asm');
        } else {
            progInput.value = info.demo_program_text;
            switchInputMode('hex');
        }
    } catch (e) {
        console.error('Failed to load initial ISA info:', e);
    }
    // Program Lab handoff (stashed by the inline consumer in the template):
    // the lab's compiled assembly replaces the demo program for this load.
    if (window.__labHandoffAsm) {
        progInput.value = window.__labHandoffAsm;
        switchInputMode('asm');
        delete window.__labHandoffAsm;
    }
    updatePanelVisibility();
    // Populate predictors BEFORE the first topology load: loadTopology() builds
    // its query from bpSel.value, so the initial diagram must see the
    // default/saved predictor (otherwise the first paint omits it).
    await loadPredictors();
    await loadTopology();
    loadCheatsheet();
    // Initialize the Core-C compiler tab (null-guarded inside the module).
    if (typeof CompilerTab !== 'undefined' && CompilerTab.init) {
        CompilerTab.init();
    }
}

// ── Interface for compiler_tab.js (separate script) ──────────────
// compiler_tab.js runs in its own script scope and cannot see this module's
// const/let/functions directly, so the few it needs are exposed here. This is
// the documented, minimal surface (keep it stable if either file changes).
window.CpuSim = {
    get API() { return API; },
    get currentISA() { return currentISA; },
    get progInput() { return progInput; },
    switchInputMode: (m) => switchInputMode(m),
    loadTopology: () => loadTopology(),
    runSimulation: () => runSimulation(),
};

init();
