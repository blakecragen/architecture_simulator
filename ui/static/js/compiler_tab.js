/**
 * RTL CPU Simulator — Core-C compiler tab.
 *
 * Adds a "Source (C)" input mode: the user writes Core-C, this module POSTs to
 * POST /compile, renders the compiler stages (source / tokens / AST / assembly)
 * with source-line highlighting from the response source_map, then reuses the
 * existing visualize path (set assembly text -> switchInputMode('asm') ->
 * loadTopology + runSimulation).
 *
 * All DOM access is null-guarded so the base UI keeps working if the compiler
 * markup is absent. Interop with cpu_simulator.js goes through window.CpuSim
 * (a small documented interface it exposes).
 */
(function () {
    'use strict';

    // ── DOM refs (all null-guarded) ──────────────────────────────
    const btnCompileRun  = document.getElementById('btn-compile-run');
    const stagesPanel    = document.getElementById('compiler-stages');
    const stageBody      = document.getElementById('cstage-body');
    const stageTabs      = document.querySelectorAll('.cstage-tab');
    const exampleSelect  = document.getElementById('c-example-select');

    // ── Module state ─────────────────────────────────────────────
    let lastResult   = null;          // last successful /compile response
    let activeStage  = 'source';      // which stage tab is shown
    let initialized  = false;
    // Two-buffer model: the single shared textarea shows the C source in
    // Source (C) mode and the compiled assembly in Assembly mode. Without
    // this split, Run after Compile & Run used to feed C SOURCE to the
    // assembler ("Unknown ARM mnemonic 'INT'" from `int main()`).
    let lastCSource     = null;       // C buffer (restored on entering C mode)
    let lastCompiledAsm = null;       // asm buffer (shown when leaving C mode)

    const DEMO_C =
`// Core-C demo — compiled to project mnemonics
int main() {
    int a = 6;
    int b = 7;
    int c = a * b;
    return c;
}`;

    // ── Helpers ──────────────────────────────────────────────────
    function api()  { return (window.CpuSim && window.CpuSim.API) || (window.CPU_API_URL || ''); }
    function isa()  { return (window.CpuSim && window.CpuSim.currentISA) || 'riscv'; }
    function prog() { return window.CpuSim && window.CpuSim.progInput; }

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // ── Stage rendering ──────────────────────────────────────────
    function selectStage(name) {
        activeStage = name;
        stageTabs.forEach(t =>
            t.classList.toggle('cstage-tab--active', t.dataset.cstage === name));
        renderActiveStage();
    }

    function renderActiveStage() {
        if (!stageBody) return;
        if (!lastResult) { stageBody.innerHTML = ''; return; }
        const stages = lastResult.stages || {};
        if (activeStage === 'source') {
            stageBody.innerHTML = renderSource(stages.source || '');
        } else if (activeStage === 'tokens') {
            stageBody.innerHTML = renderTokens(stages.tokens || []);
        } else if (activeStage === 'ast') {
            stageBody.innerHTML = renderAst(stages.ast);
        } else if (activeStage === 'asm') {
            stageBody.innerHTML = renderAsm(lastResult);
        }
    }

    function renderSource(src) {
        const lines = String(src).split('\n');
        let html = '<pre class="cstage-code cstage-code--source">';
        lines.forEach((ln, i) => {
            html += `<div class="cstage-line" data-cline="${i + 1}">` +
                `<span class="cstage-lnum">${i + 1}</span>` +
                `<span class="cstage-ltext">${escapeHtml(ln) || '&nbsp;'}</span></div>`;
        });
        html += '</pre>';
        return html;
    }

    function renderTokens(tokens) {
        if (!tokens.length) return '<div class="cstage-empty">No tokens</div>';
        let html = '<div class="cstage-tokens">';
        for (const t of tokens) {
            const kind = escapeHtml(t.kind || '');
            const val  = escapeHtml(t.value != null ? t.value : '');
            const loc  = (t.line != null) ? `${t.line}:${t.col != null ? t.col : 0}` : '';
            html += `<span class="cstage-token" title="line ${loc}">` +
                `<span class="cstoken-kind">${kind}</span>` +
                `<span class="cstoken-val">${val}</span></span>`;
        }
        html += '</div>';
        return html;
    }

    function renderAst(ast) {
        if (ast == null) return '<div class="cstage-empty">No AST</div>';
        let text;
        try { text = JSON.stringify(ast, null, 2); }
        catch (_) { text = String(ast); }
        return `<pre class="cstage-code cstage-code--ast">${escapeHtml(text)}</pre>`;
    }

    // Render generated assembly with source-line highlighting: hovering an asm
    // line highlights the C line it maps to (from source_map), and vice-versa.
    function renderAsm(result) {
        const asm = (result.stages && result.stages.asm) || result.asm || '';
        const lines = String(asm).split('\n');
        // asm_line -> c_line
        const map = {};
        for (const m of (result.source_map || [])) {
            if (m && m.asm_line != null) map[m.asm_line] = m.c_line;
        }
        let html = '<pre class="cstage-code cstage-code--asm">';
        lines.forEach((ln, i) => {
            const asmLine = i + 1;
            const cLine = map[asmLine];
            const attr = (cLine != null) ? ` data-cline="${cLine}"` : '';
            html += `<div class="cstage-line cstage-line--asm"${attr} data-asmline="${asmLine}">` +
                `<span class="cstage-lnum">${asmLine}</span>` +
                `<span class="cstage-ltext">${escapeHtml(ln) || '&nbsp;'}</span></div>`;
        });
        html += '</pre>';
        return html;
    }

    // Cross-highlight C<->asm lines on hover (delegated; works for both stages).
    function wireStageHover() {
        if (!stageBody) return;
        stageBody.addEventListener('mouseover', (e) => {
            const row = e.target.closest('.cstage-line');
            if (!row) return;
            const cLine = row.dataset.cline;
            if (cLine == null) return;
            stageBody.querySelectorAll('.cstage-line[data-cline="' + cLine + '"]')
                .forEach(el => el.classList.add('cstage-line--hl'));
        });
        stageBody.addEventListener('mouseout', () => {
            stageBody.querySelectorAll('.cstage-line--hl')
                .forEach(el => el.classList.remove('cstage-line--hl'));
        });
    }

    // ── Core-C examples (GET /compiler/examples) ─────────────────
    // Populate the "Examples…" dropdown; selecting one loads its source into
    // the editor. Samples that don't target the current ISA stay selectable
    // (their header explains the limitation) but are marked in the label.
    let cExamples = [];   // [{name, label, file, description, targets}]

    async function loadCExamples() {
        if (!exampleSelect) return;
        try {
            const res = await fetch(`${api()}/compiler/examples`);
            if (!res.ok) throw new Error('examples ' + res.status);
            cExamples = (await res.json()).items || [];
        } catch (e) {
            console.warn('Core-C examples unavailable:', e);
            cExamples = [];
        }
        renderCExampleOptions();
    }

    function renderCExampleOptions() {
        if (!exampleSelect) return;
        const current = exampleSelect.value;
        exampleSelect.innerHTML = '<option value="">Examples…</option>';
        for (const ex of cExamples) {
            const opt = document.createElement('option');
            opt.value = ex.name;
            const fits = !ex.targets || !ex.targets.length || ex.targets.includes(isa());
            opt.textContent = fits ? ex.label : `${ex.label} (not ${isa()})`;
            if (ex.description) opt.title = ex.description;
            exampleSelect.appendChild(opt);
        }
        exampleSelect.value = current || '';
    }

    async function onExampleChosen() {
        if (!exampleSelect || !exampleSelect.value) return;
        const name = exampleSelect.value;
        const p = prog();
        if (!p) return;
        try {
            const res = await fetch(`${api()}/compiler/examples/${name}`);
            const data = await res.json();
            if (data.error) { alert(data.error); return; }
            p.value = data.content || '';
            if (stagesPanel) stagesPanel.style.display = 'none';
            lastResult = null;
        } catch (e) {
            console.error('Failed to load example:', e);
            alert('Failed to load example: ' + e.message);
        } finally {
            // Reset to the placeholder so re-choosing the same sample re-loads.
            exampleSelect.value = '';
        }
    }

    // ── Compile & Run ────────────────────────────────────────────
    async function compileAndRun() {
        const p = prog();
        if (!p) return;
        const source = p.value;
        if (!source || !source.trim()) {
            alert('Source is empty — write some Core-C first.');
            return;
        }
        const body = {
            source: source,
            isa: isa(),
        };
        if (btnCompileRun) { btnCompileRun.disabled = true; btnCompileRun.textContent = 'Compiling...'; }
        try {
            const res = await fetch(`${api()}/compile`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (data.error) {          // mirror runSimulation's error handling
                alert(data.error);
                return;
            }
            lastResult = data;
            if (stagesPanel) stagesPanel.style.display = 'block';
            selectStage('asm');

            // Reuse the whole visualize path: record both buffers, flip to
            // Assembly mode (onLeaveMode swaps the compiled asm into the
            // editor — NEVER '#'-strip ARM asm), then (re)load topology + run.
            // The C source stays in lastCSource and is restored by
            // onEnterMode when the user returns to Source (C).
            if (window.CpuSim) {
                lastCSource = source;
                lastCompiledAsm = data.asm || '';
                // Compiled Core-C is verbose: the naive stack-machine codegen
                // needs far more cycles than hand asm (measured worst case
                // ~1050 on riscv/pipeline; API cap is 2000). Bump the cycle
                // count so the program actually converges — but only raise it,
                // never lower a larger value the user chose deliberately, and
                // skip entirely in auto (run-to-completion) mode, where the
                // server decides and the input just reports the actual count.
                const auto = document.getElementById('auto-cycles');
                if (!auto || !auto.checked) {
                    const cyc = document.getElementById('num-cycles');
                    if (cyc && (parseInt(cyc.value, 10) || 0) < 1500) cyc.value = 1500;
                }
                window.CpuSim.switchInputMode('asm');
                await window.CpuSim.loadTopology();
                await window.CpuSim.runSimulation();
            }
        } catch (e) {
            console.error('Compile failed:', e);
            alert('Compile failed: ' + e.message);
        } finally {
            if (btnCompileRun) { btnCompileRun.disabled = false; btnCompileRun.textContent = 'Compile & Run'; }
        }
    }

    // ── Public interface (window.CompilerTab) ────────────────────
    // Called by cpu_simulator.js when the user switches into 'c' mode:
    // restore the C buffer (or seed the demo).
    function onEnterMode() {
        const p = prog();
        if (p) {
            if (lastCSource != null) p.value = lastCSource;
            else if (!p.value.trim()) p.value = DEMO_C;
        }
        renderCExampleOptions();   // re-mark samples for the (possibly new) ISA
    }

    // Called by cpu_simulator.js when the user switches OUT of 'c' mode: save
    // the C buffer and show the last compiled assembly (empty until the first
    // compile — the assembler rejects C source, so never leave C in place).
    function onLeaveMode() {
        const p = prog();
        if (!p) return;
        lastCSource = p.value;
        p.value = lastCompiledAsm || '';
    }

    function init() {
        if (initialized) return;
        initialized = true;
        if (btnCompileRun) btnCompileRun.addEventListener('click', compileAndRun);
        if (exampleSelect) exampleSelect.addEventListener('change', onExampleChosen);
        stageTabs.forEach(t =>
            t.addEventListener('click', () => selectStage(t.dataset.cstage)));
        wireStageHover();
        loadCExamples();
    }

    window.CompilerTab = { init, onEnterMode, onLeaveMode, compileAndRun };
})();
