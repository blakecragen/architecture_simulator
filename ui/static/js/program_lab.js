/**
 * Program Lab — the Translation Bench (/lab).
 *
 * A Core-C-first page: the C source and its generated assembly sit side by
 * side, joined by source-map ribbons (drawn from /compile's source_map).
 * The machine (ISA / model / predictor) is deliberately miniature — an
 * instrument strip at the bottom driven by /simulate — and "Compile & Race"
 * fills the proving-ground grid from /compare.
 *
 * Geometry contract: line height + editor padding come from the CSS custom
 * properties --code-lh / --code-pad (see program_lab.css).
 */
(function () {
    'use strict';

    const API = window.CPU_API_URL || '';

    // ── DOM refs ─────────────────────────────────────────────────
    const $ = (id) => document.getElementById(id);
    const cInput       = $('c-input');
    const cBackdrop    = $('c-backdrop');
    const cEditor      = $('c-editor');
    const cEdited      = $('c-edited');
    const ribbonSvg    = $('ribbon-svg');
    const ribbonWrap   = ribbonSvg.parentElement;
    const stageBody    = $('stage-body');
    const stageTabs    = document.querySelectorAll('.stage-tab');
    const asmTarget    = $('asm-target');
    const compileStatus= $('compile-status');
    const exampleSel   = $('example-select');
    const btnCompile   = $('btn-compile');
    const btnRace      = $('btn-race');
    const racePanel    = $('race-panel');
    const raceBody     = $('race-body');
    const btnRaceClose = $('btn-race-close');
    const rkModal      = $('rk-modal');
    const rkBackdrop   = $('rk-backdrop');
    const rkModalClose = $('rk-modal-close');
    const costInputs   = { alu: $('cost-alu'), load: $('cost-load'),
                           store: $('cost-store'), branch: $('cost-branch') };
    const isaSel       = $('isa-select');
    const modelSel     = $('model-select');
    const bpSel        = $('bp-select');
    const lanesCtl     = $('lanes-ctl');
    const lanesSel     = $('lanes-select');
    const btnRun       = $('btn-run');
    const runStatus    = $('run-status');
    const btnOpenSim   = $('btn-open-sim');
    const miniCpu      = $('mini-cpu');
    const btnPrev      = $('btn-prev');
    const btnNext      = $('btn-next');
    const btnPlay      = $('btn-play');
    const cycleSlider  = $('cycle-slider');
    const cycleLabel   = $('cycle-label');
    const regTicker    = $('reg-ticker');
    const varsBody     = $('vars-body');
    const varsNote     = $('vars-note');
    const terminal     = $('terminal');
    const archSvg      = $('arch-svg');
    const archTitle    = $('arch-title');
    const btnStepBack  = $('btn-step-back');
    const btnStepInto  = $('btn-step-into');
    const btnStepOver  = $('btn-step-over');
    const btnStepOut   = $('btn-step-out');
    const debugStatus  = $('debug-status');

    // Code geometry from CSS (single source of truth).
    const rootStyle = getComputedStyle(document.documentElement);
    const LH  = parseInt(rootStyle.getPropertyValue('--code-lh'), 10) || 20;
    const PAD = parseInt(rootStyle.getPropertyValue('--code-pad'), 10) || 10;
    const RIBBON_COLORS = [0, 1, 2, 3, 4, 5]
        .map(i => rootStyle.getPropertyValue(`--rb-${i}`).trim() || '#dd8f5c');

    const MODELS = ['single_cycle', 'configurable', 'multicycle', 'pipeline', 'ooo', 'superscalar'];
    const MODEL_SHORT = { single_cycle: 'Single', configurable: 'Custom', multicycle: 'FetDecExe',
                          pipeline: 'Pipe', ooo: 'OoO', superscalar: 'Super' };
    const MODEL_LABELS = { single_cycle: 'Single-Cycle Datapath',
                           configurable: 'Configurable (per-op cycle costs)',
                           multicycle: 'FetDecExe Datapath',
                           pipeline: '5-Stage Pipeline Datapath',
                           ooo: 'Out-of-Order (Tomasulo) Datapath',
                           superscalar: 'Superscalar Datapath' };
    const COST_CLASSES = ['alu', 'load', 'store', 'branch'];
    const PRINT_WORD = 510;   // byte 2040 >> 2 — the compiler's console word
    const ISA_LABELS = { riscv: 'RISC-V', arm: 'ARM', x86: 'x86' };
    const ISA_ORDER = ['riscv', 'arm', 'x86'];

    const DEMO_C =
`// Fibonacci with a console: print(expr) writes to the terminal below.
int main() {
    int a = 0;
    int b = 1;
    int n = 10;
    int i;
    for (i = 1; i < n; i = i + 1) {
        int t = a + b;
        a = b;
        b = t;
        print(b);
    }
    return b;
}`;

    // ── State ────────────────────────────────────────────────────
    let compiled = null;      // last /compile result + the source it came from
    let stale = false;        // source edited since last compile
    let cHues = {};           // c_line -> ribbon color index
    let cToAsm = {};          // c_line -> [asm_line, ...]
    let asmToC = {};          // asm_line -> c_line
    let addrToLine = {};      // instruction byte address -> asm line (1-based)
    let mapReliable = false;  // client-side addr estimate matched the program
    let activeStage = 'asm';
    let hoverCLine = null;    // hover highlight
    let pcCLine = null;       // play-head highlight
    let pcAsmLine = null;
    let sim = null;           // {states, regNames, model, completed, rtc}
    let cyc = 0;
    let playTimer = null;
    let raceCells = {};       // `${isa}/${model}` -> cell element
    let printEvents = [];     // [{cycle, value}] — print() stores found in sim
    let archEngine = null;    // LayoutEngine instance for the preview

    // Source-level stepping (step into/over/out + breakpoints). Built once
    // per run from the same currentPC() walk the play-head already uses.
    let execTrace = [];       // [{cycle, asmLine, cLine, depth, stack:[names]}]
    let cycleToStep = [];     // cycleToStep[cycle] -> index into execTrace (or -1)
    const breakpoints = new Set();   // C line numbers, persists across reruns

    const escapeHtml = (s) => String(s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const pcToNum = (v) => (typeof v === 'string') ? parseInt(v, 16) : (v >>> 0);
    const toSigned = (v) => (v > 0x7FFFFFFF) ? v - 0x100000000 : v;

    // The data memory component is 'dmem' in every preset; fall back to a
    // scan for any non-imem component exposing a memory array.
    function dmemState(state) {
        if (!state) return null;
        if (state.dmem && state.dmem.memory) return state.dmem;
        for (const [k, comp] of Object.entries(state)) {
            if (comp && typeof comp === 'object' && comp.memory &&
                !k.toLowerCase().includes('imem')) return comp;
        }
        return null;
    }

    // The cycle snapshot's dmem is a dense low window (`memory`) + a sparse high
    // map (`memory_hi`, keyed by word index) — the compiled software stack lives
    // high, so read through here to see main's frame locals.
    const memWord = (d, addr) => {
        const size = d.size || d.memory.length;
        const w = (addr >>> 2) % size;
        if (w < d.memory.length) return d.memory[w];
        const hi = d.memory_hi;
        const v = hi ? hi[w] : undefined;
        return (v === undefined || v === null) ? 0 : v;
    };

    // ═════════════════════════════════════════════════════════════
    //  C editor: backdrop stripes + scroll sync
    // ═════════════════════════════════════════════════════════════
    function rebuildBackdrop() {
        const lines = cInput.value.split('\n');
        let html = `<div class="bd-lines" style="padding-top:${PAD}px">`;
        for (let i = 1; i <= lines.length; i++) {
            const hue = cHues[i];
            const mapped = hue !== undefined && !stale;
            const cls = ['bd-line', mapped ? 'bd-line--mapped' : '',
                         (i === hoverCLine) ? 'bd-line--hl' : '',
                         (i === pcCLine) ? 'bd-line--pc' : '',
                         breakpoints.has(i) ? 'bd-line--bp' : ''].join(' ');
            const style = mapped ? ` style="--rb:${RIBBON_COLORS[hue % 6]}"` : '';
            html += `<div class="${cls}" data-line="${i}"${style}>` +
                `<span class="bd-line__num">${i}</span>` +
                `<span class="bd-line__stripe"></span></div>`;
        }
        html += '</div>';
        cBackdrop.innerHTML = html;
        syncBackdropScroll();
    }

    function syncBackdropScroll() {
        const inner = cBackdrop.firstElementChild;
        if (inner) inner.style.transform = `translateY(${-cInput.scrollTop}px)`;
    }

    cInput.addEventListener('scroll', () => { syncBackdropScroll(); scheduleRibbons(); });

    cInput.addEventListener('input', () => {
        if (compiled && !stale && cInput.value !== compiled.source) {
            stale = true;
            cEdited.hidden = false;
            cEditor.classList.add('editor--stale');
            ribbonWrap.classList.add('stale');
        } else if (compiled && stale && cInput.value === compiled.source) {
            stale = false;
            cEdited.hidden = true;
            cEditor.classList.remove('editor--stale');
            ribbonWrap.classList.remove('stale');
        }
        rebuildBackdrop();
    });

    cInput.addEventListener('keydown', (e) => {
        if (e.key === 'Tab') {
            e.preventDefault();
            const { selectionStart: s, selectionEnd: en, value } = cInput;
            cInput.value = value.slice(0, s) + '    ' + value.slice(en);
            cInput.selectionStart = cInput.selectionEnd = s + 4;
            cInput.dispatchEvent(new Event('input'));
        }
    });

    // Hover a C line -> light its ribbon + asm lines.
    cInput.addEventListener('mousemove', (e) => {
        const rect = cInput.getBoundingClientRect();
        const line = Math.floor(
            (e.clientY - rect.top + cInput.scrollTop - PAD) / LH) + 1;
        setHover(cHues[line] !== undefined ? line : null);
    });
    cInput.addEventListener('mouseleave', () => setHover(null));

    // ═════════════════════════════════════════════════════════════
    //  Compile + stage rendering
    // ═════════════════════════════════════════════════════════════
    function setCompileStatus(text, kind) {
        compileStatus.textContent = text || '';
        compileStatus.title = text || '';
        compileStatus.className = 'compile-status' + (kind ? ` compile-status--${kind}` : '');
    }

    async function compile() {
        const source = cInput.value;
        if (!source.trim()) { setCompileStatus('source is empty', 'err'); return false; }
        btnCompile.disabled = true;
        btnCompile.textContent = 'Compiling…';
        try {
            const res = await fetch(`${API}/compile`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source, isa: isaSel.value }),
            });
            const data = await res.json();
            if (data.error) {
                compiled = null;
                clearMaps();
                stageBody.innerHTML = `<div class="stage-error">${escapeHtml(data.error)}</div>`;
                asmTarget.textContent = '—';
                setCompileStatus(data.error, 'err');
                drawRibbons();
                rebuildBackdrop();
                return false;
            }
            compiled = {
                source,
                isa: data.isa,
                asm: data.asm || '',
                tokens: (data.stages && data.stages.tokens) || [],
                ast: data.stages ? data.stages.ast : null,
                sourceMap: data.source_map || [],
                symbols: data.symbols || [],
                program: data.program || [],
            };
            stale = false;
            cEdited.hidden = true;
            cEditor.classList.remove('editor--stale');
            ribbonWrap.classList.remove('stale');
            buildMaps();
            invalidateSim('machine ready — Run');
            selectStage('asm');
            rebuildBackdrop();
            drawRibbons();
            asmTarget.textContent = ISA_LABELS[data.isa] || data.isa;
            renderVars(null, null);
            const n = compiled.program.length;
            const unit = data.isa === 'x86' ? 'bytes' : 'words';
            setCompileStatus(`compiled for ${data.isa} · ${n} ${unit}`, 'ok');
            return true;
        } catch (e) {
            setCompileStatus('compile failed: ' + e.message, 'err');
            return false;
        } finally {
            btnCompile.disabled = false;
            btnCompile.textContent = 'Compile';
        }
    }

    function clearMaps() {
        cHues = {}; cToAsm = {}; asmToC = {}; addrToLine = {};
        mapReliable = false;
        pcCLine = pcAsmLine = null;
    }

    // The same instruction-size heuristic the simulator page uses for x86
    // (variable-length encoding — verified against program length below).
    function estimateX86Size(code) {
        const parts = code.trim().split(/[\s,]+/).filter(t => t);
        const mnem = (parts[0] || '').toUpperCase();
        const dst = parts[1] || '', src = parts.length > 2 ? parts[2] : null;
        if (/^J/.test(mnem)) return 2;
        if (mnem === 'PUSH' || mnem === 'POP') return 1;
        if (mnem === 'NOP' || mnem === 'RET') return 1;
        if (mnem === 'INT') return 2;
        if (mnem === 'MOV' && src && /^\d|^-|^0x/.test(src) && !/^\[/.test(dst)) return 5;
        if (mnem === 'MOV' && src && /^E[A-Z]{2}$/i.test(src) && /^E[A-Z]{2}$/i.test(dst)) return 2;
        if (mnem === 'MOV' && src && (/\[/.test(src) || /\[/.test(dst))) {
            const memOp = /\[/.test(src) ? src : dst;
            return /\+/.test(memOp) ? 3 : 2;
        }
        if (src && /^\d|^-|^0x/.test(src)) return 3;
        if (src && /^E[A-Z]{2}$/i.test(src)) return 2;
        return 2;
    }

    // Classify each asm text line and estimate its address so the play-head
    // can map PC -> asm line -> C line.
    // Call/return classification for the step-over/step-out call-stack model.
    // Both call-capable backends always call through 'ra'/'x1' (riscv) or use
    // BL (arm) — see codegen/{riscv,arm}.py emit_call/emit_return/emit_soft_*.
    // x86 models no CALL/RET stack, so it never matches (call depth stays 0).
    function classifyCallRet(isa, code) {
        if (isa === 'riscv') {
            const call = code.match(/^JAL\s+(?:ra|x1)\s*,\s*(\w+)/i);
            if (call) return { kind: 'call', target: call[1] };
            if (/^JALR\s+(?:x0|zero)\s*,\s*(?:ra|x1)\s*,/i.test(code)) {
                return { kind: 'ret' };
            }
        } else if (isa === 'arm') {
            const call = code.match(/^BL\s+(\w+)/i);
            if (call) return { kind: 'call', target: call[1] };
            if (/^RET\b/i.test(code)) return { kind: 'ret' };
        }
        return { kind: 'instr' };
    }

    function buildMaps() {
        clearMaps();
        const isa = compiled.isa;
        const lines = compiled.asm.split('\n');
        let addr = 0;
        const lineMeta = [];
        const lineCallKind = [];   // 'call' | 'ret' | 'instr' | 'other'
        const lineCallTarget = []; // callee label for 'call' lines
        for (let i = 0; i < lines.length; i++) {
            let code = lines[i].replace(/;.*$/, '').replace(/\/\/.*$/, '');
            if (isa === 'riscv') code = code.replace(/#.*$/, '');
            code = code.trim();
            let kind = 'other';
            let callInfo = { kind: 'other' };
            if (code) {
                const label = code.match(/^\w+:\s*(.*)$/);
                if (label) code = label[1].trim();
                if (code) {
                    kind = 'instr';
                    callInfo = classifyCallRet(isa, code);
                    addrToLine[addr] = i + 1;
                    addr += (isa === 'x86') ? estimateX86Size(code) : 4;
                }
            }
            lineMeta.push(kind);
            lineCallKind.push(callInfo.kind);
            lineCallTarget.push(callInfo.target || null);
        }
        compiled.lineMeta = lineMeta;
        compiled.lineCallKind = lineCallKind;
        compiled.lineCallTarget = lineCallTarget;
        // Reliable only if the client-side size walk covers exactly the
        // assembled program (words are 4 bytes; x86 program is flat bytes).
        const progBytes = (isa === 'x86')
            ? compiled.program.length : compiled.program.length * 4;
        mapReliable = (addr === progBytes);

        for (const m of compiled.sourceMap) {
            if (!m || m.asm_line == null || m.c_line == null) continue;
            asmToC[m.asm_line] = m.c_line;
            (cToAsm[m.c_line] = cToAsm[m.c_line] || []).push(m.asm_line);
        }
        let hue = 0;
        for (const cl of Object.keys(cToAsm).map(Number).sort((a, b) => a - b)) {
            cHues[cl] = hue++ % 6;
        }
    }

    // ── Stage tabs (Assembly / Tokens / AST) ─────────────────────
    stageTabs.forEach(t => t.addEventListener('click', () => selectStage(t.dataset.stage)));

    function selectStage(name) {
        activeStage = name;
        stageTabs.forEach(t =>
            t.classList.toggle('stage-tab--active', t.dataset.stage === name));
        renderStage();
        drawRibbons();   // ribbons only exist while the assembly is visible
        // Re-paint stage badges onto the freshly-built rows (asm tab only).
        if (activeStage === 'asm') {
            applyStageBadges(sim ? computeResidency(sim.states[cyc]).byLine : {});
        }
    }

    function renderStage() {
        if (!compiled) return;
        if (activeStage === 'asm') {
            renderAsmListing();
        } else if (activeStage === 'tokens') {
            const toks = compiled.tokens;
            stageBody.innerHTML = !toks.length
                ? '<div class="stage-empty">No tokens</div>'
                : '<div class="stage-tokens">' + toks.map(t =>
                    `<span class="stage-token" title="line ${t.line != null ? t.line : '?'}">` +
                    `<span class="stage-token__kind">${escapeHtml(t.kind || '')}</span>` +
                    `<span class="stage-token__val">${escapeHtml(t.value != null ? t.value : '')}</span>` +
                    '</span>').join('') + '</div>';
        } else {
            let text;
            try { text = JSON.stringify(compiled.ast, null, 2); }
            catch (_) { text = String(compiled.ast); }
            stageBody.innerHTML = `<div class="stage-ast">${escapeHtml(text)}</div>`;
        }
    }

    function renderAsmListing() {
        const lines = compiled.asm.split('\n');
        let html = '<div class="asm-lines">';
        for (let i = 0; i < lines.length; i++) {
            const ln = i + 1;
            const cl = asmToC[ln];
            const mapped = cl !== undefined;
            const dim = compiled.lineMeta[i] !== 'instr';
            const cls = ['lab-line', mapped ? 'lab-line--mapped' : '',
                         dim ? 'lab-line--dim' : '',
                         (ln === pcAsmLine) ? 'lab-line--pc' : '',
                         (mapped && cl === hoverCLine) ? 'lab-line--hl' : ''].join(' ');
            const style = mapped ? ` style="--rb:${RIBBON_COLORS[cHues[cl] % 6]}"` : '';
            html += `<div class="${cls}" data-line="${ln}"` +
                (mapped ? ` data-cline="${cl}"` : '') + style + '>' +
                `<span class="lab-line__num">${ln}</span>` +
                `<span class="lab-line__text">${escapeHtml(lines[i]) || ' '}</span>` +
                `<span class="lab-line__badge"></span></div>`;
        }
        stageBody.innerHTML = html + '</div>';
    }

    stageBody.addEventListener('scroll', scheduleRibbons);
    stageBody.addEventListener('mouseover', (e) => {
        const row = e.target.closest('.lab-line[data-cline]');
        setHover(row ? Number(row.dataset.cline) : null);
    });
    stageBody.addEventListener('mouseleave', () => setHover(null));

    // ═════════════════════════════════════════════════════════════
    //  Ribbons (the signature): C line -> asm run bands in the gutter
    // ═════════════════════════════════════════════════════════════
    let ribbonRaf = 0;
    function scheduleRibbons() {
        if (ribbonRaf) return;
        ribbonRaf = requestAnimationFrame(() => { ribbonRaf = 0; drawRibbons(); });
    }

    function contiguousRuns(sorted) {
        const runs = [];
        let start = sorted[0], prev = sorted[0];
        for (let i = 1; i <= sorted.length; i++) {
            if (i < sorted.length && sorted[i] === prev + 1) { prev = sorted[i]; continue; }
            runs.push([start, prev]);
            start = prev = sorted[i];
        }
        return runs;
    }

    function drawRibbons() {
        const svgRect = ribbonWrap.getBoundingClientRect();
        const W = svgRect.width, H = svgRect.height;
        ribbonSvg.setAttribute('viewBox', `0 0 ${W} ${H}`);
        if (!compiled || activeStage !== 'asm') { ribbonSvg.innerHTML = ''; return; }

        const cRect = cInput.getBoundingClientRect();
        const aRect = stageBody.getBoundingClientRect();
        const cTop = cRect.top - svgRect.top;
        const aTop = aRect.top - svgRect.top;
        const cScroll = cInput.scrollTop, aScroll = stageBody.scrollTop;
        const anyFocus = (hoverCLine != null) || (pcCLine != null);

        // Linker-map style: one thin thread per C line -> asm run, with a
        // notch at the C end and a bracket bar spanning the asm run. Full
        // bands overlap into mud when a short C program fans out into a much
        // longer assembly.
        let paths = '';
        for (const clStr of Object.keys(cToAsm)) {
            const cl = Number(clStr);
            const color = RIBBON_COLORS[cHues[cl] % 6];
            const cyc = cTop + PAD + (cl - 1) * LH - cScroll + LH / 2;
            for (const [r0, r1] of contiguousRuns(cToAsm[cl].slice().sort((a, b) => a - b))) {
                const ay1 = aTop + PAD + (r0 - 1) * LH - aScroll + 2;
                const ay2 = aTop + PAD + r1 * LH - aScroll - 2;
                // Only thread what's actually on screen on the ASM side (the
                // asm is several times longer than the C). Focused
                // (hover/play-head) threads always draw.
                const focused = (cl === hoverCLine) || (cl === pcCLine);
                if (!focused && (ay2 < 4 || ay1 > H - 4)) continue;
                const ayc = (ay1 + ay2) / 2;
                const cls = 'rb' + (focused ? ' rb--hl' : (anyFocus ? ' rb--dim' : ''));
                paths += `<path class="${cls}" stroke="${color}" fill="none" ` +
                    `d="M3,${cyc} C${W * 0.45},${cyc} ${W * 0.55},${ayc} ${W - 4},${ayc}"/>` +
                    `<rect class="${cls} rb-notch" fill="${color}" ` +
                    `x="0" y="${cyc - 5}" width="3" height="10" rx="1.5"/>` +
                    `<rect class="${cls} rb-bracket" fill="${color}" ` +
                    `x="${W - 3.5}" y="${ay1}" width="3" height="${Math.max(4, ay2 - ay1)}" rx="1.5"/>`;
            }
        }
        ribbonSvg.innerHTML = paths;
    }

    window.addEventListener('resize', scheduleRibbons);
    if (window.ResizeObserver) new ResizeObserver(scheduleRibbons).observe(ribbonWrap);

    // ── Hover / play-head highlighting ───────────────────────────
    function setHover(cline) {
        if (cline === hoverCLine) return;
        hoverCLine = cline;
        applyLineClasses();
        scheduleRibbons();
    }

    function setPlayhead(asmLine, cline) {
        if (asmLine === pcAsmLine && cline === pcCLine) return;
        pcAsmLine = asmLine;
        pcCLine = cline;
        applyLineClasses();
        scheduleRibbons();
        const row = asmLine != null &&
            stageBody.querySelector(`.lab-line[data-line="${asmLine}"]`);
        if (row) scrollRowIntoStageBody(row);
    }

    // Keep the play-head row visible WITHIN the asm pane's own scroll box
    // (stageBody, overflow:auto) — never scrollIntoView, which would also
    // scroll the document/window to the top when the pane is above the fold.
    function scrollRowIntoStageBody(row) {
        const cRect = stageBody.getBoundingClientRect();
        const rRect = row.getBoundingClientRect();
        const pad = 8;   // keep a little breathing room at the edges
        if (rRect.top < cRect.top + pad) {
            stageBody.scrollTop -= (cRect.top + pad) - rRect.top;
        } else if (rRect.bottom > cRect.bottom - pad) {
            stageBody.scrollTop += rRect.bottom - (cRect.bottom - pad);
        }
    }

    function applyLineClasses() {
        stageBody.querySelectorAll('.lab-line').forEach(el => {
            const ln = Number(el.dataset.line);
            const cl = el.dataset.cline ? Number(el.dataset.cline) : null;
            el.classList.toggle('lab-line--pc', ln === pcAsmLine);
            el.classList.toggle('lab-line--hl', cl != null && cl === hoverCLine);
        });
        cBackdrop.querySelectorAll('.bd-line').forEach(el => {
            const ln = Number(el.dataset.line);
            el.classList.toggle('bd-line--hl', ln === hoverCLine);
            el.classList.toggle('bd-line--pc', ln === pcCLine);
        });
    }

    // Per-cycle stage-residency badges on the asm rows — updates the existing
    // .lab-line__badge span in place (never rebuilds the listing), the same way
    // applyLineClasses() toggles row classes each scrub tick. byLine maps an
    // asm line -> { stage, lane }. An empty/omitted map clears every badge.
    function applyStageBadges(byLine) {
        const map = byLine || {};
        stageBody.querySelectorAll('.lab-line').forEach(el => {
            const badge = el.querySelector('.lab-line__badge');
            if (!badge) return;
            const info = map[Number(el.dataset.line)];
            if (info) {
                badge.textContent = info.lane != null
                    ? `L${info.lane}·${info.stage}` : info.stage;
                el.classList.add('lab-line--resident');
            } else {
                badge.textContent = '';
                el.classList.remove('lab-line--resident');
            }
        });
    }

    // ═════════════════════════════════════════════════════════════
    //  Machine: run + instrument strip
    // ═════════════════════════════════════════════════════════════
    function setRunStatus(text, kind) {
        runStatus.textContent = text || '';
        runStatus.className = 'run-status' + (kind ? ` run-status--${kind}` : '');
    }

    function invalidateSim(msg) {
        stopPlay();
        sim = null;
        cyc = 0;
        printEvents = [];
        execTrace = [];
        cycleToStep = [];
        cycleSlider.min = 0; cycleSlider.max = 0; cycleSlider.value = 0;
        cycleSlider.disabled = btnPrev.disabled = btnNext.disabled = btnPlay.disabled = true;
        setStepButtonsEnabled(false);
        cycleLabel.textContent = 'cycle –';
        miniCpu.innerHTML = '<span class="mini-cpu__idle">no run yet</span>';
        regTicker.innerHTML = '';
        setPlayhead(null, null);
        applyStageBadges({});
        renderVars(null, null);
        renderTerminal();
        renderDebugStatus();
        if (msg) setRunStatus(msg);
    }

    function setStepButtonsEnabled(on) {
        [btnStepBack, btnStepInto, btnStepOver, btnStepOut].forEach(b => {
            if (b) b.disabled = !on;
        });
    }

    async function ensureCompiled() {
        if (compiled && !stale && compiled.isa === isaSel.value) return true;
        return compile();
    }

    async function run() {
        btnRun.disabled = true;
        setRunStatus('');
        try {
            if (!await ensureCompiled()) { setRunStatus('fix the compile first', 'err'); return; }
            setRunStatus('running…');
            const body = {
                preset: `${isaSel.value}/${modelSel.value}`,
                input_mode: 'asm',
                asm_text: compiled.asm,
                branch_predictor: bpSel.value || '',
                prediction_stage: 'id',
                num_lanes: parseInt(lanesSel.value, 10) || 2,
                run_to_completion: true,
            };
            const res = await fetch(`${API}/simulate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (data.error) { setRunStatus(data.error, 'err'); return; }
            sim = {
                states: data.cycles || [],
                regNames: data.reg_names || [],
                model: data.model,
                completed: data.completed !== false,
            };
            computePrintEvents();
            computeExecTrace();
            const n = sim.states.length;
            cycleSlider.min = 0;
            cycleSlider.max = Math.max(0, n - 1);
            cycleSlider.disabled = btnPrev.disabled = btnNext.disabled = btnPlay.disabled = (n === 0);
            setStepButtonsEnabled(n > 0 && mapReliable && execTrace.length > 0);
            // n-1 includes the quiet settle-detection window, so it reads a
            // little higher than the race grid's settle-point numbers.
            setRunStatus(sim.completed
                ? `done — ${Math.max(0, n - 1)} cycles captured ✓`
                : 'hit the 10,000-cycle cap ⚠', sim.completed ? 'ok' : 'warn');
            showCycle(n - 1);   // land on the final state — the answer
        } catch (e) {
            setRunStatus('run failed: ' + e.message, 'err');
        } finally {
            btnRun.disabled = false;
        }
    }

    function showCycle(i) {
        if (!sim || !sim.states.length) return;
        cyc = Math.max(0, Math.min(i, sim.states.length - 1));
        cycleSlider.value = cyc;
        cycleLabel.textContent = `cycle ${cyc} / ${sim.states.length - 1}`;
        const state = sim.states[cyc];
        const prev = cyc > 0 ? sim.states[cyc - 1] : null;
        renderMiniCpu(state);
        renderRegTicker(state, prev);
        renderVars(state, prev);
        renderTerminal();
        renderDebugStatus();
        // Bidirectional overlay: resolve which instruction sits in which
        // stage/lane this cycle, then feed BOTH the diagram (per-component
        // instruction labels) and the asm listing (per-line stage badges) from
        // the one map so they always agree. Empty/no-op when unreliable.
        const residency = computeResidency(state);
        if (archEngine && archEngine.layout) {
            const instrMap = {};
            for (const id in residency.byComp) instrMap[id] = residency.byComp[id];
            archEngine.updateState(state, instrMap);
        }
        applyStageBadges(residency.byLine);
        // Play-head: current PC -> asm line -> C line.
        if (mapReliable) {
            const pc = currentPC(state);
            const asmLine = (pc != null) ? addrToLine[pc] : undefined;
            setPlayhead(asmLine != null ? asmLine : null,
                        asmLine != null ? (asmToC[asmLine] != null ? asmToC[asmLine] : null) : null);
        }
    }

    // Which PC best represents "now executing" for the play-head.
    function currentPC(state) {
        const model = sim.model;
        const f = state.fetch;
        if (model === 'multicycle') {
            return state.pc_latch && state.pc_latch.pc != null
                ? pcToNum(state.pc_latch.pc) : null;
        }
        if (model === 'pipeline') {
            for (const reg of ['id_ex', 'if_id']) {
                const r = state[reg];
                if (r && r.valid !== 'BUBBLE' && r.pc != null) return pcToNum(r.pc);
            }
        }
        if (model === 'superscalar' && f && f.pc_lane_0 != null) return pcToNum(f.pc_lane_0);
        return (f && f.pc != null) ? pcToNum(f.pc) : null;
    }

    function instrAt(pcField, validField) {
        if (validField === 'BUBBLE') return null;
        if (pcField == null) return null;
        const line = addrToLine[pcToNum(pcField)];
        if (line == null || !compiled) return null;
        const text = (compiled.asm.split('\n')[line - 1] || '').trim();
        return text.length > 18 ? text.slice(0, 17) + '…' : text;
    }

    function stageCell(label, info, mods) {
        const cls = ['mini-stage'].concat((mods || []).map(m => `mini-stage--${m}`)).join(' ');
        return `<div class="${cls}"><span class="mini-stage__label">${label}</span>` +
            `<span class="mini-stage__info">${escapeHtml(info || '·')}</span></div>`;
    }

    function renderMiniCpu(state) {
        const model = sim.model;
        let html = '';
        if (model === 'single_cycle') {
            const pc = state.fetch && state.fetch.pc;
            html = stageCell('exec', instrAt(pc) || (pc != null ? `PC=${pc}` : ''), ['active']);
        } else if (model === 'multicycle') {
            const phase = state.mc_ctrl ? state.mc_ctrl.phase : null;
            const instr = state.pc_latch ? instrAt(state.pc_latch.pc) : null;
            ['fet', 'dec', 'exe', 'mem'].forEach((p, idx) => {
                html += stageCell(p, idx === phase ? (instr || '·') : '',
                                  idx === phase ? ['active'] : []);
            });
        } else if (model === 'pipeline') {
            const hz = state.hazard_det;
            const stall = hz && (hz.stall === 'STALL' || hz.stall === 1);
            const flush = state.branch && state.branch.mispredict;
            const defs = [
                ['if',  state.fetch && { pc: state.fetch.pc }],
                ['id',  state.if_id],
                ['ex',  state.id_ex],
                ['mem', state.ex_mem],
                ['wb',  state.mem_wb],
            ];
            defs.forEach(([label, reg], idx) => {
                const bubble = reg && reg.valid === 'BUBBLE';
                const instr = reg && !bubble ? instrAt(reg.pc, reg.valid) : null;
                const mods = [];
                if (stall && idx <= 1) mods.push('stall');
                else if (flush && idx <= 2) mods.push('flush');
                else if (bubble) mods.push('bubble');
                else if (instr) mods.push('active');
                html += stageCell(label, bubble ? 'bubble'
                    : (stall && idx <= 1) ? 'stall'
                    : (flush && idx <= 2) ? 'flush'
                    : instr || '', mods);
            });
        } else if (model === 'ooo') {
            const instr = state.fetch ? instrAt(state.fetch.pc) : null;
            html += stageCell('if', instr || '', instr ? ['active'] : []);
            const rob = state.rob || {};
            html += stageCell('rob', rob.count != null ? `${rob.count} in flight` : '',
                              rob.count ? ['active'] : []);
            const rs = state.rs || {};
            html += stageCell('rs', rs.exec_valid ? 'exec' : 'wait',
                              rs.exec_valid ? ['active'] : []);
        } else if (model === 'superscalar') {
            const lanes = parseInt(lanesSel.value, 10) || 2;
            html += stageCell('if', state.fetch && state.fetch.pc_lane_0 != null
                ? instrAt(state.fetch.pc_lane_0) || '' : '', ['active']);
            [['id', 'if_id'], ['ex', 'id_ex'], ['mem', 'ex_mem'], ['wb', 'mem_wb']]
                .forEach(([label, reg]) => {
                    const cs = state[reg];
                    let k = 0;
                    if (cs) for (let i = 0; i < lanes; i++) {
                        const lane = cs[`lane_${i}`];
                        if (lane && lane.valid !== 'BUBBLE') k++;
                    }
                    html += stageCell(label, `${k}/${lanes} lanes`, k ? ['active'] : []);
                });
        }
        miniCpu.innerHTML = html || '<span class="mini-cpu__idle">no state</span>';
    }

    // ── Instruction residency (single source of truth for the overlay) ──
    // For the scrubbed cycle, resolve WHICH asm instruction sits in WHICH
    // stage/lane. Ported from the block-diagram simulator's buildInstrMap +
    // computePipelineBadges (cpu_simulator.js) so /lab agrees with it, and it
    // reuses the same addrToLine/pcToNum walk instrAt()/currentPC() use — no
    // second source of truth. Returns two views of the ONE result:
    //   byComp — LayoutEngine component id -> instruction text
    //            (fed to archEngine.updateState(state, instrMap) so each block
    //             shows the instruction currently occupying it)
    //   byLine — asm line number          -> { stage, lane }
    //            (drives the per-line IF/ID/EX/MEM/WB badges in the listing)
    // No-ops (empty maps) when the map is unreliable or there's no sim.
    function computeResidency(state) {
        const byComp = {};
        const byLine = {};
        if (!sim || !mapReliable || !compiled || !state) return { byComp, byLine };
        const asmLines = compiled.asm.split('\n');
        const model = sim.model;
        const lanes = parseInt(lanesSel.value, 10) || 2;

        // pc -> {line, text}; null for bubbles / unmapped. A leading label is
        // trimmed for a clean diagram label ("L_x: STR ..." -> "STR ...").
        const at = (pcField, validField) => {
            if (validField === 'BUBBLE' || pcField == null) return null;
            const line = addrToLine[pcToNum(pcField)];
            if (line == null) return null;
            const raw = (asmLines[line - 1] || '').trim();
            return { line, text: raw.replace(/^\w+:\s*/, '') };
        };
        const place = (compId, hit) => { if (hit) byComp[compId] = hit.text; };
        const mark = (hit, stage, lane) => {
            if (hit && byLine[hit.line] === undefined) byLine[hit.line] = { stage, lane };
        };

        if (model === 'single_cycle') {
            const hit = state.fetch ? at(state.fetch.pc) : null;
            // one instruction runs the whole datapath spine this cycle
            for (const id in state) if (id !== '_cycle') place(id, hit);
            mark(hit, 'EXE');
        } else if (model === 'multicycle') {
            const phase = state.mc_ctrl ? state.mc_ctrl.phase : null;
            const hit = state.pc_latch ? at(state.pc_latch.pc) : null;
            for (const id in state) if (id !== '_cycle') place(id, hit);
            const labels = ['FET', 'DEC', 'EXE', 'MEM'];
            if (phase != null && labels[phase]) mark(hit, labels[phase]);
        } else if (model === 'pipeline') {
            const ifHit  = state.fetch  ? at(state.fetch.pc)                  : null;
            const idHit  = state.if_id  ? at(state.if_id.pc,  state.if_id.valid)  : null;
            const exHit  = state.id_ex  ? at(state.id_ex.pc,  state.id_ex.valid)  : null;
            const memHit = state.ex_mem ? at(state.ex_mem.pc, state.ex_mem.valid) : null;
            const wbHit  = state.mem_wb ? at(state.mem_wb.pc, state.mem_wb.valid) : null;
            place('fetch', ifHit);  place('imem', ifHit);
            place('if_id', idHit);  place('decode', idHit);  place('regfile', idHit);
            place('id_ex', exHit);  place('forwarding', exHit);
            place('alu_mux', exHit); place('alu', exHit);
            place('ex_mem', memHit); place('branch', memHit); place('dmem', memHit);
            place('mem_wb', wbHit);  place('wb', wbHit);
            mark(ifHit, 'IF'); mark(idHit, 'ID'); mark(exHit, 'EX');
            mark(memHit, 'MEM'); mark(wbHit, 'WB');
        } else if (model === 'ooo') {
            const hit = state.fetch ? at(state.fetch.pc) : null;
            place('fetch', hit); place('imem', hit); place('decode', hit);
            mark(hit, 'IF');
            // ROB entries carry a pc — badge each in-flight instruction.
            const rob = state.rob;
            if (rob && rob.entries) {
                rob.entries.forEach((e) => {
                    if (e && e.valid && e.pc != null) {
                        const h = at(e.pc);
                        if (h && byLine[h.line] === undefined) {
                            byLine[h.line] = { stage: e.ready ? 'ROB✓' : 'ROB' };
                        }
                    }
                });
            }
        } else if (model === 'superscalar') {
            const f = state.fetch;
            if (f) {
                for (let i = 0; i < lanes; i++) {
                    const lpc = f[`pc_lane_${i}`];
                    if (lpc == null) continue;
                    const h = at(lpc);
                    if (i === 0) { place('fetch', h); place('imem', h); }
                    mark(h, 'IF', i);
                }
            }
            // Per-lane pipeline registers -> per-lane diagram components
            // (decode_i / alu_mux_i / alu_i / wb_i); dmem is a shared block
            // driven by lane-0's memory op (matches the layout's lane-0 addr).
            const stageDefs = [
                ['decode', 'ID',  'if_id'],
                ['alu',    'EX',  'id_ex'],
                ['dmem',   'MEM', 'ex_mem'],
                ['wb',     'WB',  'mem_wb'],
            ];
            stageDefs.forEach(([compBase, stage, regKey]) => {
                const cs = state[regKey];
                if (!cs) return;
                for (let i = 0; i < lanes; i++) {
                    const lane = cs[`lane_${i}`];
                    if (!lane || lane.valid === 'BUBBLE') continue;
                    const h = at(lane.pc, lane.valid);
                    if (!h) continue;
                    if (compBase === 'dmem') {
                        if (i === 0) place('dmem', h);
                    } else {
                        place(`${compBase}_${i}`, h);
                        if (compBase === 'alu') place(`alu_mux_${i}`, h);
                    }
                    mark(h, stage, i);
                }
            });
        }
        return { byComp, byLine };
    }

    function renderRegTicker(state, prev) {
        const rf = state.regfile;
        if (!rf || !rf.registers) { regTicker.innerHTML = ''; return; }
        const regs = rf.registers;
        const prevRegs = prev && prev.regfile && prev.regfile.registers;
        let html = '', shown = 0, hidden = 0;
        for (let i = 0; i < regs.length; i++) {
            const changed = prevRegs && prevRegs[i] !== regs[i];
            if (!changed && !regs[i]) continue;
            if (shown >= 20) { hidden++; continue; }
            shown++;
            const name = sim.regNames[i] || `r${i}`;
            html += `<span class="reg-chip${changed ? ' reg-chip--chg' : ''}">` +
                `${escapeHtml(name)}=<b>${escapeHtml(String(regs[i]))}</b></span>`;
        }
        if (hidden) html += `<span class="reg-chip reg-chip--more">+${hidden} more</span>`;
        regTicker.innerHTML = html;
    }

    // ── Scrubber controls ────────────────────────────────────────
    cycleSlider.addEventListener('input', () => showCycle(parseInt(cycleSlider.value, 10)));
    btnPrev.addEventListener('click', () => { stopPlay(); showCycle(cyc - 1); });
    btnNext.addEventListener('click', () => { stopPlay(); showCycle(cyc + 1); });
    btnPlay.addEventListener('click', () => (playTimer ? stopPlay() : startPlay()));

    // Source-level stepping controls. Play (▶) already free-runs the raw
    // cycles; these move by C LINE instead, using the exec trace above.
    if (btnStepBack) btnStepBack.addEventListener('click', () => { stopPlay(); stepInto(-1); });
    if (btnStepInto) btnStepInto.addEventListener('click', () => { stopPlay(); stepInto(1); });
    if (btnStepOver) btnStepOver.addEventListener('click', () => { stopPlay(); stepOver(1); });
    if (btnStepOut)  btnStepOut.addEventListener('click',  () => { stopPlay(); stepOut(1); });

    // Breakpoints: click a line number in the C editor's gutter to toggle.
    // Play (▶) stops at the first one it reaches; persists across recompiles
    // of the SAME file (cleared only when a different example is loaded).
    cBackdrop.addEventListener('click', (e) => {
        const row = e.target.closest('.bd-line');
        if (!row) return;
        const line = Number(row.dataset.line);
        if (breakpoints.has(line)) breakpoints.delete(line);
        else breakpoints.add(line);
        rebuildBackdrop();
    });

    function startPlay() {
        if (!sim) return;
        if (cyc >= sim.states.length - 1) showCycle(0);
        btnPlay.innerHTML = '&#9646;&#9646;';
        playTimer = setInterval(() => {
            if (cyc >= sim.states.length - 1) { stopPlay(); return; }
            showCycle(cyc + 1);
            // Breakpoint check: stop the FIRST cycle we land on a breakpointed
            // line's starting cycle (not every stall cycle spent on that line).
            if (breakpoints.size && execTrace.length) {
                const idx = cycleToStep[cyc];
                if (idx >= 0 && execTrace[idx].cycle === cyc &&
                        breakpoints.has(execTrace[idx].cLine)) {
                    stopPlay();
                }
            }
        }, 110);
    }

    function stopPlay() {
        if (playTimer) clearInterval(playTimer);
        playTimer = null;
        btnPlay.innerHTML = '&#9654;';
    }

    // ═════════════════════════════════════════════════════════════
    //  Variable debugger (main's frame, from /compile symbols)
    // ═════════════════════════════════════════════════════════════
    function renderVars(state, prev) {
        const syms = compiled && compiled.symbols;
        if (!syms || !syms.length) {
            varsBody.innerHTML = '<tr><td colspan="4" class="vars-empty">' +
                (compiled ? 'no locals in main' : 'compile to populate') +
                '</td></tr>';
            varsNote.textContent = compiled ? 'no locals in main' : 'compile to populate';
            return;
        }
        varsNote.textContent = stale
            ? 'edited — recompile to refresh'
            : `main's frame · ${sim ? 'live at cycle ' + cyc : 'run to see values'}`;
        const mem = state ? dmemState(state) : null;
        const pmem = prev ? dmemState(prev) : null;
        let html = '';
        for (const s of syms) {
            let val = '—', chg = false;
            if (mem) {
                if (s.kind === 'array') {
                    const els = [], n = Math.min(s.size, 8);
                    for (let i = 0; i < n; i++) {
                        const a = s.addr + i * s.stride;
                        els.push(toSigned(memWord(mem, a)));
                        if (pmem && memWord(pmem, a) !== memWord(mem, a)) chg = true;
                    }
                    val = `[${els.join(', ')}${s.size > n ? ', …' : ''}]`;
                } else {
                    const v = memWord(mem, s.addr);
                    val = String(toSigned(v));
                    chg = !!pmem && memWord(pmem, s.addr) !== v;
                }
            }
            const label = s.kind === 'array' ? `${s.name}[${s.size}]` : s.name;
            html += `<tr class="${chg ? 'vars-row--chg' : ''}">` +
                `<td>${escapeHtml(label)}</td>` +
                `<td>${escapeHtml(val)}</td>` +
                `<td>0x${s.addr.toString(16).toUpperCase().padStart(4, '0')}</td>` +
                `<td>${escapeHtml(s.location || '')}</td></tr>`;
        }
        varsBody.innerHTML = html;
    }

    // ═════════════════════════════════════════════════════════════
    //  Console: replay print() stores up to the scrubbed cycle
    // ═════════════════════════════════════════════════════════════
    function computePrintEvents() {
        printEvents = [];
        if (!sim) return;
        // A print is a dmem write to the console word. Consecutive identical
        // write signals are one store observed across held cycles, not two.
        let prevSig = null;
        sim.states.forEach((st, i) => {
            const d = dmemState(st);
            if (!d) { prevSig = null; return; }
            const sig = d.wen ? `${d.write_addr}|${d.wdata}` : null;
            const size = d.size || d.memory.length;
            if (d.wen && ((d.write_addr >>> 2) % size) === PRINT_WORD &&
                    sig !== prevSig) {
                printEvents.push({ cycle: i, value: toSigned(d.wdata) });
            }
            prevSig = sig;
        });
    }

    // ═════════════════════════════════════════════════════════════
    //  Source-level stepping: exec trace + call stack
    // ═════════════════════════════════════════════════════════════
    // Walks the same currentPC() sequence the play-head uses, deduping
    // consecutive cycles on the same asm line, and tracks a call stack via
    // the call/ret classification from buildMaps(). Lines with no C-line
    // mapping (program prologue, the untagged __mul/__divmod bodies) still
    // drive the call-stack push/pop but are not recorded as visible steps —
    // so stepping through a '*' never wanders into compiler-generated
    // runtime plumbing, only the user's own function calls.
    function computeExecTrace() {
        execTrace = [];
        cycleToStep = new Array(sim ? sim.states.length : 0).fill(-1);
        if (!sim || !mapReliable || !compiled) return;
        let depth = -1;            // -1 until the program-prologue call lands us in main (depth 0)
        let callStack = [];        // display names, e.g. ['main', 'fib', 'fib']
        let lastAsmLine = null;
        let lastStepIdx = -1;
        sim.states.forEach((st, i) => {
            const pc = currentPC(st);
            const asmLine = (pc != null) ? addrToLine[pc] : undefined;
            if (asmLine == null || asmLine === lastAsmLine) {
                cycleToStep[i] = lastStepIdx;
                return;
            }
            lastAsmLine = asmLine;
            const cLine = asmToC[asmLine];
            if (cLine != null) {
                // A single C statement usually compiles to a RUN of several
                // asm instructions (stack-machine spills/loads) all sharing
                // this cLine — merge them into one logical step, so "step
                // into" advances by SOURCE LINE, not by instruction. A call
                // to a runtime helper (__mul/__divmod) round-trips depth back
                // to the same value before resuming this line's remaining
                // instructions, so it merges too — transparent, like a real
                // debugger skipping library internals. Re-entering the same
                // cLine at the same depth via a loop is NOT merged, because
                // the loop's condition/increment lines sit in between (a
                // different cLine breaks the run).
                const last = execTrace[lastStepIdx];
                const isNewStep = !last || last.cLine !== cLine || last.depth !== depth;
                if (isNewStep) {
                    execTrace.push({ cycle: i, asmLine, cLine, depth,
                                     stack: callStack.slice() });
                    lastStepIdx = execTrace.length - 1;
                }
            }
            cycleToStep[i] = lastStepIdx;
            const callKind = compiled.lineCallKind[asmLine - 1];
            if (callKind === 'call') {
                const target = compiled.lineCallTarget[asmLine - 1] || '?';
                callStack.push(target.replace(/^func_/, ''));
                depth++;
            } else if (callKind === 'ret') {
                callStack.pop();
                depth = Math.max(-1, depth - 1);
            }
        });
    }

    function currentStepIndex() {
        if (!execTrace.length) return -1;
        return cyc < cycleToStep.length ? cycleToStep[cyc] : -1;
    }

    // First step index strictly beyond (dir>0) or before (dir<0) the CURRENT
    // cycle — anchored on cyc rather than the sticky group index, so this
    // stays correct even if the user reached this cycle via the raw slider
    // or Play, landing mid-group (idx±1 would not be reliably "forward").
    function adjacentStepIndex(dir) {
        if (dir > 0) {
            for (let i = 0; i < execTrace.length; i++) {
                if (execTrace[i].cycle > cyc) return i;
            }
        } else {
            for (let i = execTrace.length - 1; i >= 0; i--) {
                if (execTrace[i].cycle < cyc) return i;
            }
        }
        return -1;
    }

    function renderDebugStatus() {
        if (!debugStatus) return;
        if (!compiled) { debugStatus.textContent = ''; return; }
        if (!mapReliable) {
            debugStatus.textContent = 'line stepping unavailable for this program';
            return;
        }
        const idx = currentStepIndex();
        if (idx < 0) {
            debugStatus.textContent = sim ? 'no source line at this cycle' : 'run to step through lines';
            return;
        }
        const step = execTrace[idx];
        const trail = step.stack.length ? step.stack.join(' → ') : '—';
        debugStatus.textContent = `line ${step.cLine} — ${trail}`;
    }

    // dir: +1 forward, -1 backward. All three scan execTrace in CYCLE order
    // starting from the first step beyond the current cycle (not the current
    // step's array index ± dir) — see adjacentStepIndex().
    function stepInto(dir) {
        if (!execTrace.length) return;
        const next = adjacentStepIndex(dir);
        if (next < 0) { showCycle(dir > 0 ? sim.states.length - 1 : 0); return; }
        showCycle(execTrace[next].cycle);
    }

    function stepOver(dir) {
        if (!execTrace.length) return;
        const curIdx = currentStepIndex();
        if (curIdx < 0) { stepInto(dir); return; }
        const baseDepth = execTrace[curIdx].depth;
        let i = adjacentStepIndex(dir);
        while (i >= 0 && i < execTrace.length) {
            if (execTrace[i].depth <= baseDepth) { showCycle(execTrace[i].cycle); return; }
            i += dir;
        }
        showCycle(dir > 0 ? sim.states.length - 1 : 0);
    }

    function stepOut(dir) {
        if (!execTrace.length) return;
        const curIdx = currentStepIndex();
        if (curIdx < 0) return;
        const baseDepth = execTrace[curIdx].depth;
        let i = adjacentStepIndex(dir);
        while (i >= 0 && i < execTrace.length) {
            if (execTrace[i].depth < baseDepth) { showCycle(execTrace[i].cycle); return; }
            i += dir;
        }
        // Stepping out of the outermost frame (forward) = run to completion;
        // (backward) = rewind to the start. Both are reasonable "finish" reads.
        showCycle(dir > 0 ? sim.states.length - 1 : 0);
    }

    function renderTerminal() {
        if (!printEvents.length) {
            terminal.innerHTML = '<div class="terminal__empty">no output — ' +
                'call print(expr) in your Core-C</div>';
            return;
        }
        const shown = printEvents.filter(e => e.cycle <= cyc);
        const pending = printEvents.length - shown.length;
        let html = '';
        shown.forEach((e, i) => {
            const latest = i === shown.length - 1;
            html += `<div class="terminal__line${latest ? ' terminal__line--latest' : ''}">` +
                `<span class="terminal__cycle">cyc ${e.cycle}</span>` +
                `<span class="terminal__val">${escapeHtml(String(e.value))}</span></div>`;
        });
        if (pending) {
            html += `<div class="terminal__pending">… ${pending} more later in the run</div>`;
        }
        if (!shown.length) {
            html = `<div class="terminal__pending">first print at cycle ` +
                `${printEvents[0].cycle} — scrub forward</div>` + html;
        }
        terminal.innerHTML = html;
        terminal.scrollTop = terminal.scrollHeight;
    }

    // ═════════════════════════════════════════════════════════════
    //  Architecture preview (LayoutEngine, shared with the simulator)
    // ═════════════════════════════════════════════════════════════
    function layoutForModel(model) {
        try {
            if (model === 'single_cycle' && window.getSingleCycleLayout)
                return window.getSingleCycleLayout();
            if (model === 'multicycle' && window.getMulticycleLayout)
                return window.getMulticycleLayout();
            if (model === 'pipeline' && window.getPipelineLayout)
                return window.getPipelineLayout();
            if (model === 'ooo' && window.getOoOLayout)
                return window.getOoOLayout();
            if (model === 'superscalar' && window.getSuperscalarLayout)
                return window.getSuperscalarLayout(parseInt(lanesSel.value, 10) || 2);
        } catch (e) {
            console.warn('Layout template error:', e);
        }
        return null;
    }

    function renderPreview() {
        if (!archSvg || !window.LayoutEngine || typeof d3 === 'undefined') return;
        const model = modelSel.value;
        archTitle.textContent =
            `${ISA_LABELS[isaSel.value]} · ${MODEL_LABELS[model] || model}`;
        const layout = layoutForModel(model);
        if (!layout) {
            archSvg.innerHTML = '';
            return;
        }
        if (!archEngine) archEngine = new LayoutEngine(archSvg);
        archEngine.renderLayout(layout, (sim && sim.states[cyc]) || null);
    }

    // ═════════════════════════════════════════════════════════════
    //  Proving ground: Compile & Race (/compare)
    // ═════════════════════════════════════════════════════════════
    async function race() {
        const source = cInput.value;
        if (!source.trim()) { setCompileStatus('source is empty', 'err'); return; }
        racePanel.hidden = false;
        raceBody.innerHTML = '<div class="race-loading">racing across every machine</div>';
        btnRace.disabled = true;
        try {
            const res = await fetch(`${API}/compare`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source, num_lanes: parseInt(lanesSel.value, 10) || 2,
                                       cycle_costs: readCosts() }),
            });
            const data = await res.json();
            if (data.error) {
                raceBody.innerHTML = `<div class="stage-error">${escapeHtml(data.error)}</div>`;
                return;
            }
            renderRaceGrid(data);
        } catch (e) {
            raceBody.innerHTML = `<div class="stage-error">race failed: ${escapeHtml(e.message)}</div>`;
        } finally {
            btnRace.disabled = false;
        }
    }

    // The editable "Custom" column runs the configurable model with these
    // per-instruction-class cycle budgets (clamped 1..64, matching the API).
    function readCosts() {
        const costs = {};
        for (const cls of COST_CLASSES) {
            const v = parseInt(costInputs[cls].value, 10);
            costs[cls] = Math.max(1, Math.min(64, Number.isFinite(v) ? v : 1));
        }
        return costs;
    }

    // Re-race (debounced) whenever a knob changes, but only once the grid is
    // already on screen and there's a program to run.
    let raceDebounce = null;
    for (const cls of COST_CLASSES) {
        costInputs[cls].addEventListener('input', () => {
            if (racePanel.hidden || !cInput.value.trim()) return;
            clearTimeout(raceDebounce);
            raceDebounce = setTimeout(race, 300);
        });
    }

    function renderRaceGrid(data) {
        const byKey = {};
        for (const r of data.results) byKey[`${r.isa}/${r.model}`] = r;
        const isas = ISA_ORDER.filter(i => (data.isas || []).includes(i));
        // single_cycle is the correctness ORACLE the server parity-checks every
        // other model against — it stays in data.results (best-cell math + parity
        // still work). We only DROP it as a displayed column; the numbers stay honest.
        const models = MODELS.filter(m =>
            m !== 'single_cycle' && (data.models || MODELS).includes(m));

        let max = 0;
        for (const r of data.results) {
            if (r.cycles != null && r.completed) max = Math.max(max, r.cycles);
        }

        raceCells = {};
        let html = '<table class="race-table"><thead><tr><th></th>';
        for (const m of models) {
            if (m === 'configurable') {
                html += `<th class="race-th--custom" title="${escapeHtml(MODEL_LABELS[m] || m)}">` +
                    `<button type="button" class="race-th__btn" id="race-th-custom" ` +
                    `title="Edit the per-op cycle costs that drive this column">` +
                    `${MODEL_SHORT[m]}<span class="race-th__edit">✎</span></button></th>`;
            } else {
                html += `<th title="${escapeHtml(MODEL_LABELS[m] || m)}">${MODEL_SHORT[m]}</th>`;
            }
        }
        html += '</tr></thead><tbody>';
        isas.forEach((isa, ri) => {
            const rowBest = Math.min(...models
                .map(m => byKey[`${isa}/${m}`])
                .filter(r => r && r.cycles != null && r.completed)
                .map(r => r.cycles));
            html += `<tr><th>${ISA_LABELS[isa]}</th>`;
            models.forEach((m, ci) => {
                const r = byKey[`${isa}/${m}`];
                const delay = `style="animation-delay:${ri * 60 + ci * 45}ms"`;
                if (!r || r.error) {
                    html += `<td class="race-cell--na" ${delay} title="${escapeHtml(r ? r.error : 'no result')}">—</td>`;
                } else if (!r.completed) {
                    html += `<td class="race-cell race-cell--na" ${delay} title="did not settle within the ${data.cap}-cycle cap">` +
                        `<span class="race-cell__cap">≥${data.cap} ⚠</span></td>`;
                } else {
                    const best = r.cycles === rowBest;
                    const pct = max ? Math.max(2, Math.round(100 * r.cycles / max)) : 0;
                    if (m === 'configurable') {
                        // Editable comparison-only column: not mountable (the
                        // /lab machine bar has no configurable model), so it
                        // carries no data-isa/model and gets no click handler.
                        const costs = data.cycle_costs || {};
                        const costStr = COST_CLASSES.map(c => `${c}=${costs[c]}`).join(' ');
                        const timeStr = r.total_time != null
                            ? ` · ≈${Math.round(r.total_time).toLocaleString()} time units (clock ${r.clock_period.toFixed(2)})`
                            : '';
                        html += `<td class="race-cell race-cell--custom${best ? ' race-cell--best' : ''}" ${delay} ` +
                            `title="Configurable · ${costStr}${timeStr} — click the Custom ✎ header to edit">` +
                            `<span class="race-cell__cycles">${r.cycles.toLocaleString()}</span>` +
                            `<div class="race-cell__bar"><i style="width:${pct}%"></i></div></td>`;
                    } else {
                        html += `<td class="race-cell${best ? ' race-cell--best' : ''}" ${delay} ` +
                            `data-isa="${isa}" data-model="${m}" ` +
                            `title="mount ${ISA_LABELS[isa]} · ${m}">` +
                            `<span class="race-cell__cycles">${r.cycles.toLocaleString()}</span>` +
                            `<div class="race-cell__bar"><i style="width:${pct}%"></i></div></td>`;
                    }
                }
            });
            html += '</tr>';
        });
        html += '</tbody></table>' +
            '<div class="race-note">Cycles to completion, settle-detected, parity-checked ' +
            'against single-cycle (the hidden oracle column). <b>Custom ✎</b> is the ' +
            'configurable model — click its header to open the cycle-cost dials and see the ' +
            'payoff of speeding up a class (comparison-only, not mountable). Click any other ' +
            'cell to mount that machine below. — = not modeled or not portable (hover for why).</div>';
        raceBody.innerHTML = html;

        raceBody.querySelectorAll('.race-cell[data-isa]').forEach(cell => {
            raceCells[`${cell.dataset.isa}/${cell.dataset.model}`] = cell;
            cell.addEventListener('click', async () => {
                isaSel.value = cell.dataset.isa;
                modelSel.value = cell.dataset.model;
                onMachineChanged(false);
                markActiveCell();
                await run();
            });
        });
        const customTh = raceBody.querySelector('#race-th-custom');
        if (customTh) customTh.addEventListener('click', openCostModal);
        markActiveCell();
    }

    function markActiveCell() {
        for (const key of Object.keys(raceCells)) {
            raceCells[key].classList.toggle('race-cell--active',
                key === `${isaSel.value}/${modelSel.value}`);
        }
    }

    // ── Custom-column cost editor (modal) ────────────────────────
    // Hosts the per-op cycle-cost dials that were once inline in the race
    // head. Editing a dial re-races through the same debounced readCosts()/
    // race() path the inputs already own (see the COST_CLASSES listener loop).
    function openCostModal() {
        if (!rkModal) return;
        rkModal.hidden = false;
        // focus the first dial so keyboard users land inside the panel
        const first = costInputs.alu;
        if (first) { first.focus(); if (first.select) first.select(); }
    }

    function closeCostModal() {
        if (rkModal) rkModal.hidden = true;
    }

    if (rkModalClose) rkModalClose.addEventListener('click', closeCostModal);
    if (rkBackdrop)   rkBackdrop.addEventListener('click', closeCostModal);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && rkModal && !rkModal.hidden) closeCostModal();
    });

    btnRaceClose.addEventListener('click', () => { racePanel.hidden = true; });

    // ═════════════════════════════════════════════════════════════
    //  Machine controls / examples / handoff
    // ═════════════════════════════════════════════════════════════
    function onMachineChanged(clearStatus) {
        // Lanes only mean anything for superscalar — hide AND disable the
        // control when it's off-model so its value can't leak into /simulate's
        // num_lanes or /compare (all three ISAs may use 1-6 lanes when on-model).
        const superscalar = (modelSel.value === 'superscalar');
        lanesCtl.hidden = !superscalar;
        lanesSel.disabled = !superscalar;
        invalidateSim(clearStatus === false ? '' : 'machine changed — Run to update');
        markActiveCell();
        renderPreview();
    }

    isaSel.addEventListener('change', () => onMachineChanged());
    modelSel.addEventListener('change', () => onMachineChanged());
    bpSel.addEventListener('change', () => onMachineChanged());
    lanesSel.addEventListener('change', () => onMachineChanged());

    btnCompile.addEventListener('click', compile);
    btnRun.addEventListener('click', run);
    btnRace.addEventListener('click', race);

    btnOpenSim.addEventListener('click', () => {
        const payload = {
            isa: isaSel.value,
            model: modelSel.value,
            bp: bpSel.value || '',
            lanes: parseInt(lanesSel.value, 10) || 2,
            asm: (compiled && !stale && compiled.isa === isaSel.value) ? compiled.asm : null,
        };
        try { localStorage.setItem('rtl_lab_handoff', JSON.stringify(payload)); }
        catch (_) { /* storage full/blocked — still navigate */ }
        window.location.href = '/';
    });

    async function loadPredictors() {
        try {
            const res = await fetch(`${API}/predictors`);
            const data = await res.json();
            for (const p of data.predictors || []) {
                const opt = document.createElement('option');
                opt.value = p.name;
                opt.textContent = p.label || p.name;
                bpSel.appendChild(opt);
            }
        } catch (e) { console.warn('predictors unavailable:', e); }
    }

    async function loadExamples() {
        try {
            const res = await fetch(`${API}/compiler/examples`);
            const data = await res.json();
            for (const ex of data.items || []) {
                const opt = document.createElement('option');
                opt.value = ex.name;
                opt.textContent = ex.label;
                if (ex.description) opt.title = ex.description;
                exampleSel.appendChild(opt);
            }
        } catch (e) { console.warn('examples unavailable:', e); }
    }

    exampleSel.addEventListener('change', async () => {
        if (!exampleSel.value) return;
        try {
            const res = await fetch(`${API}/compiler/examples/${exampleSel.value}`);
            const data = await res.json();
            if (data.error) { setCompileStatus(data.error, 'err'); return; }
            cInput.value = data.content || '';
            compiled = null;
            clearMaps();
            breakpoints.clear();   // line numbers are meaningless for a new file
            stale = false;
            cEdited.hidden = true;
            cEditor.classList.remove('editor--stale');
            ribbonWrap.classList.remove('stale');
            stageBody.innerHTML = '<div class="stage-empty">Compile to see the translation.</div>';
            asmTarget.textContent = '—';
            invalidateSim('');
            setCompileStatus('');
            rebuildBackdrop();
            drawRibbons();
        } catch (e) {
            setCompileStatus('failed to load example: ' + e.message, 'err');
        } finally {
            exampleSel.value = '';
        }
    });

    // ── Init ─────────────────────────────────────────────────────
    async function init() {
        onMachineChanged(false);
        await Promise.all([loadPredictors(), loadExamples()]);
        // Seed with a loop + print() so the ribbons, the race, the debugger
        // AND the console all have something to show on first paint.
        cInput.value = DEMO_C;
        rebuildBackdrop();
        if (await compile()) await run();
        renderPreview();   // after the run so the diagram opens on live state
    }

    init();
})();
