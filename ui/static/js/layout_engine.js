/**
 * RTL CPU Simulator -- Layout Engine
 *
 * Generic renderer that takes a layout descriptor + simulation state and
 * produces a textbook-quality SVG diagram using D3.js.
 *
 * Layout descriptor structure:
 * {
 *   width, height,
 *   components: {
 *     id: {
 *       x, y, w, h,
 *       shape: 'rect' | 'mux' | 'pipeline_bar',
 *       label: string,
 *       category: string,
 *       ports: { name: { side: 'left'|'right'|'top'|'bottom', offset: number } }
 *     }
 *   },
 *   wires: [
 *     {
 *       from: 'comp.port', to: 'comp.port',
 *       path: 'direct' | 'manhattan' | [[x,y], ...],
 *       label: string,
 *       style: 'data' | 'control'
 *     }
 *   ],
 *   annotations: [
 *     { type: 'label'|'dashed_box'|'stage_header', x, y, w, h, text, color }
 *   ],
 *   stages: [
 *     { id, label, x, w, color }
 *   ]
 * }
 */

/* global d3 */

class LayoutEngine {
    // ------------------------------------------------------------------ //
    //  Category colour palette                                            //
    // ------------------------------------------------------------------ //
    static CATEGORY_COLORS = {
        fetch:     { fill: '#1a2740', stroke: '#3b82f6', text: '#93bbfc' },
        decode:    { fill: '#1a2930', stroke: '#14b8a6', text: '#5eead4' },
        execute:   { fill: '#2a1a30', stroke: '#a78bfa', text: '#c4b5fd' },
        memory:    { fill: '#2a2210', stroke: '#f59e0b', text: '#fcd34d' },
        control:   { fill: '#2a1520', stroke: '#f43f5e', text: '#fda4af' },
        writeback: { fill: '#152a1a', stroke: '#22c55e', text: '#86efac' },
        pipeline:  { fill: '#1a1a30', stroke: '#818cf8', text: '#a5b4fc' },
        ooo:       { fill: '#301a1a', stroke: '#fb923c', text: '#fdba74' },
        default:   { fill: '#1e2330', stroke: '#6b7280', text: '#d1d5db' },
    };

    static STAGE_ALPHA = 0.06;

    // ------------------------------------------------------------------ //
    //  Constructor                                                        //
    // ------------------------------------------------------------------ //
    constructor(svgElement) {
        // Accept either a D3 selection or a raw DOM element / selector string
        this.svg = (svgElement instanceof d3.selection) ? svgElement : d3.select(svgElement);
        this.layout = null;
        this.rootG = null;
        this.componentsG = null;
        this.wiresG = null;
        this.stagesG = null;
        this.annotationsG = null;
        this.tooltipDiv = null;
        this._state = null;
        this._selectedCompId = null;
    }

    // ================================================================== //
    //  PUBLIC: full render                                                 //
    // ================================================================== //
    renderLayout(layout, state) {
        this.layout = layout;
        this._state = state || {};

        // 1. Clear
        this.svg.selectAll('*').remove();
        this._removeTooltip();

        // 2. ViewBox
        const w = layout.width  || 1200;
        const h = layout.height || 600;
        this.svg
            .attr('viewBox', `0 0 ${w} ${h}`)
            .attr('preserveAspectRatio', 'xMidYMid meet');

        // 3. Defs
        this._addDefs(w, h);

        // 4. Root group (zoom / pan target)
        this.rootG = this.svg.append('g').attr('class', 'le-root');

        // 5. Layers (render back-to-front)
        this.stagesG      = this.rootG.append('g').attr('class', 'le-stages');
        this.annotationsG = this.rootG.append('g').attr('class', 'le-annotations');
        this.wiresG       = this.rootG.append('g').attr('class', 'le-wires');
        this.componentsG  = this.rootG.append('g').attr('class', 'le-components');

        // 6. Draw each layer
        this._renderStages(layout.stages);
        this._renderAnnotations(layout.annotations);
        this._renderWires(layout.wires, layout.components);
        this._renderComponents(layout.components);

        // 7. Apply state overlay
        if (state) this.updateState(state);

        // 8. Zoom / pan
        this._setupZoom();

        // 9. Tooltip
        this._setupTooltip(layout.components);
    }

    // ================================================================== //
    //  PUBLIC: state-only update (no layout re-render)                     //
    // ================================================================== //
    updateState(state, instrMap) {
        this._state = state || {};
        const layout = this.layout;
        if (!layout) return;

        // -- Update component detail text and activity class ----------- //
        const compIds = Object.keys(layout.components);
        compIds.forEach(id => {
            const g = this.componentsG.select(`[data-comp-id="${id}"]`);
            if (g.empty()) return;

            const compState = state[id];
            const detail = g.select('.le-comp-detail');
            const summary = compState ? this._summarize(id, compState) : '';
            detail.text(summary);

            // Instruction text
            const instr = g.select('.le-comp-instr');
            if (!instr.empty()) {
                const instrText = (instrMap && instrMap[id]) || '';
                // Truncate if too long for the component width
                const maxChars = Math.floor((layout.components[id]?.w || 100) / 5);
                instr.text(instrText.length > maxChars
                    ? instrText.slice(0, maxChars - 1) + '\u2026'
                    : instrText);
            }

            g.classed('le-comp--active', !!summary);
        });

        // -- Highlight active wires ----------------------------------- //
        if (layout.collapseBuses) {
            // TECHNIQUE 3 — enable-signal-driven active path (OoO). Compute the
            // set of active wire keys and light members + collapsed trunks.
            const activeKeys = this._activeWireKeys(state);
            this.wiresG.selectAll('.le-wire').each(function (d) {
                d3.select(this).classed('le-wire--active', LayoutEngine._wireIsActive(d, activeKeys));
            });
            // Light collapsed bus trunks whose bus id is active (or any member is).
            if (this._busTrunks) {
                Object.keys(this._busTrunks).forEach(bus => {
                    const trunk = this._busTrunks[bus];
                    if (!trunk || trunk.empty()) return;
                    let busActive = activeKeys.has('bus:' + bus);
                    if (!busActive) {
                        // Fall back to "any member active".
                        trunk.selectAll('.le-bus-members .le-wire').each(function (d) {
                            if (LayoutEngine._wireIsActive(d, activeKeys)) busActive = true;
                        });
                    }
                    trunk.classed('le-bus--active', busActive);
                });
            }
        } else {
            // EXISTING source-nonzero rule (verbatim) for all other layouts.
            this.wiresG.selectAll('.le-wire').each(function (d) {
                const fromComp = d.from.split('.')[0];
                const fromPort = d.from.split('.')[1];
                const compState = state[fromComp];
                let active = false;
                if (compState) {
                    let val = compState[fromPort];
                    // Treat all-zero hex strings ("0x00000000") as zero so only
                    // buses carrying real data light up.
                    if (typeof val === 'string' && /^0x0+$/i.test(val)) val = 0;
                    active = val !== undefined && val !== 0 && val !== false &&
                             val !== null && val !== '' && val !== '0';
                }
                d3.select(this).classed('le-wire--active', active);
            });
        }

        // -- Update stage status badges ------------------------------- //
        if (layout.stages) {
            layout.stages.forEach(s => {
                const badge = this.stagesG.select(`[data-stage-id="${s.id}"]`);
                if (badge.empty()) return;
                // Pipeline stages get status from hazard/branch state
                const hazard = state.hazard_det;
                const branch = state.branch;
                let status = '';
                if (hazard && hazard.stall === 'STALL' && (s.id === 'IF' || s.id === 'ID')) {
                    status = 'STALL';
                } else if (branch && branch.mispredict && (s.id === 'IF' || s.id === 'ID' || s.id === 'EX')) {
                    status = 'FLUSH';
                }
                badge.select('.le-stage-status').text(status);
            });
        }
    }

    // ================================================================== //
    //  PUBLIC: TECHNIQUE 2 — layer visibility toggle                       //
    // ================================================================== //
    /**
     * Show / hide every wire (and collapsed bus trunk) belonging to a layer.
     * Toggling a class on the wires container lets CSS do the hiding:
     *   .le-wires.hide-<layer> .le-wire--layer-<layer> { display: none; }
     * The bus trunks are also flagged so trunks of a hidden layer disappear.
     *
     * @param {string}  layer   one of 'data' | 'control' | 'cdb' | 'commit'
     * @param {boolean} visible true to show, false to hide
     */
    setLayerVisible(layer, visible) {
        if (!this.wiresG || !layer) return;
        this.wiresG.classed('hide-' + layer, !visible);
        // Hide any collapsed bus trunk whose dominant layer matches. (Trunks
        // carry le-wire--layer-<layer> too, so the CSS rule above already
        // covers them; this also flips a data-attr for defensive styling.)
        this.wiresG.selectAll(`.le-bus.le-wire--layer-${layer}`)
            .classed('le-bus--hidden', !visible);
    }

    // ================================================================== //
    //  TECHNIQUE 3 — enable-signal-driven active-path computation (OoO)    //
    // ================================================================== //
    /**
     * Return a Set of keys describing which wires / buses are active this
     * cycle, driven by ENABLE signals (not raw source values). Keys are:
     *   'bus:<busId>'      — the whole bus is active
     *   '<from>'           — a specific wire source is active
     *   '<from>-><to>'     — a specific wire endpoint pair is active
     * A wire is considered active if its bus, its `from`, or its `from->to`
     * appears in the set (see _wireIsActive).
     */
    _activeWireKeys(state) {
        const keys = new Set();
        state = state || {};
        const truthy = (v) => {
            if (v === undefined || v === null || v === false) return false;
            if (v === 0 || v === '0') return false;
            if (typeof v === 'string' && /^0x0+$/i.test(v)) return false;
            return true;
        };

        const rob   = state.rob   || {};
        const rs    = state.rs    || {};
        const branch = state.branch || {};
        const fetch = state.fetch || {};
        const storeCommit = state.store_commit || {};
        const gate  = state.dispatch_gate || {};

        // Dispatch + operand buses: active when a dispatch is occurring.
        const dispatching = truthy(gate.out) || truthy(rob.dispatch_en);
        if (dispatching) {
            keys.add('bus:dispatch');
            keys.add('bus:operand');
        }

        // Execute + CDB buses: active when the RS drives a ready op onto the
        // execution units / common data bus.
        if (truthy(rs.exec_valid)) {
            keys.add('bus:cdb');
            keys.add('bus:execute');
        }

        // Commit bus: active when the ROB retires; store sub-path when a store
        // actually writes memory this cycle.
        if (truthy(rob.commit_en)) {
            keys.add('bus:commit');
            if (truthy(storeCommit.dmem_wen) || truthy(storeCommit.wen)) {
                keys.add('store_commit.dmem_wen');
                keys.add('store_commit.dmem_wen->dmem.addr');
                keys.add('store_commit.dmem_wen->dmem.wdata');
                keys.add('store_commit.dmem_wen->dmem.wen');
            }
        }

        // Branch bus: active on a resolved redirect, a stall, or a flush.
        if (truthy(branch.branch_taken) || truthy(branch.stall) ||
            truthy(branch.mispredict)   || truthy(rob.flush)) {
            keys.add('bus:branch');
        }

        // Frontend datapath (untagged): fetch -> imem -> decode active whenever
        // the fetch PC is defined (a valid instruction address).
        if (fetch.pc !== undefined && fetch.pc !== null) {
            keys.add('fetch.pc_out');
            keys.add('fetch.pc_out->imem.addr');
            keys.add('imem.data');
            keys.add('imem.data->decode.instr_in');
        }

        return keys;
    }

    /** True if a wire datum is covered by the active-key set. */
    static _wireIsActive(d, keys) {
        if (!d || !keys) return false;
        if (d.bus && keys.has('bus:' + d.bus)) return true;
        if (keys.has(d.from)) return true;
        if (keys.has(d.from + '->' + d.to)) return true;
        return false;
    }

    // ================================================================== //
    //  SVG defs                                                           //
    // ================================================================== //
    _addDefs(w, h) {
        const defs = this.svg.append('defs');

        // -- Arrowhead markers ---------------------------------------- //
        const markers = [
            { id: 'le-arrow-data',    color: 'var(--border, #2a2e3a)', size: 8 },
            { id: 'le-arrow-control', color: 'var(--text-muted, #8b8fa3)', size: 6 },
            { id: 'le-arrow-active',  color: 'var(--accent, #a78bfa)', size: 8 },
            { id: 'le-arrow-bus',     color: 'var(--accent, #a78bfa)', size: 9 },
        ];
        markers.forEach(m => {
            defs.append('marker')
                .attr('id', m.id)
                .attr('viewBox', '0 0 10 7')
                .attr('refX', 10)
                .attr('refY', 3.5)
                .attr('markerWidth', m.size)
                .attr('markerHeight', m.size * 0.75)
                .attr('orient', 'auto')
                .append('path')
                .attr('d', 'M0,0 L10,3.5 L0,7 Z')
                .attr('fill', m.color);
        });

        // -- Glow filter ---------------------------------------------- //
        const glow = defs.append('filter')
            .attr('id', 'le-glow')
            .attr('x', '-50%').attr('y', '-50%')
            .attr('width', '200%').attr('height', '200%');
        glow.append('feGaussianBlur')
            .attr('stdDeviation', '3')
            .attr('result', 'blur');
        const merge = glow.append('feMerge');
        merge.append('feMergeNode').attr('in', 'blur');
        merge.append('feMergeNode').attr('in', 'SourceGraphic');

        // -- Active wire glow filter ---------------------------------- //
        const wireGlow = defs.append('filter')
            .attr('id', 'le-wire-glow')
            .attr('x', '-20%').attr('y', '-20%')
            .attr('width', '140%').attr('height', '140%');
        wireGlow.append('feGaussianBlur')
            .attr('stdDeviation', '2')
            .attr('result', 'blur');
        const wMerge = wireGlow.append('feMerge');
        wMerge.append('feMergeNode').attr('in', 'blur');
        wMerge.append('feMergeNode').attr('in', 'SourceGraphic');
    }

    // ================================================================== //
    //  Stage column backgrounds                                           //
    // ================================================================== //
    _renderStages(stages) {
        if (!stages || !stages.length) return;
        const h = this.layout.height || 600;

        stages.forEach(s => {
            const g = this.stagesG.append('g')
                .attr('data-stage-id', s.id);

            // Shaded column
            g.append('rect')
                .attr('x', s.x)
                .attr('y', 0)
                .attr('width', s.w)
                .attr('height', h)
                .attr('fill', s.color || '#3b82f6')
                .attr('opacity', LayoutEngine.STAGE_ALPHA)
                .attr('rx', 4);

            // Header label
            g.append('text')
                .attr('class', 'le-stage-label')
                .attr('x', s.x + s.w / 2)
                .attr('y', 20)
                .attr('text-anchor', 'middle')
                .attr('font-size', '13px')
                .attr('font-weight', '700')
                .attr('fill', s.color || '#93bbfc')
                .attr('letter-spacing', '0.05em')
                .text(s.label);

            // Status badge (for pipeline stall / flush)
            g.append('text')
                .attr('class', 'le-stage-status')
                .attr('x', s.x + s.w / 2)
                .attr('y', 36)
                .attr('text-anchor', 'middle')
                .attr('font-size', '10px')
                .attr('font-weight', '600')
                .attr('fill', '#f87171')
                .text('');
        });
    }

    // ================================================================== //
    //  Annotations                                                        //
    // ================================================================== //
    _renderAnnotations(annotations) {
        if (!annotations || !annotations.length) return;

        annotations.forEach(a => {
            if (a.type === 'dashed_box') {
                this.annotationsG.append('rect')
                    .attr('x', a.x).attr('y', a.y)
                    .attr('width', a.w).attr('height', a.h)
                    .attr('rx', 6)
                    .attr('fill', 'none')
                    .attr('stroke', a.color || '#6b7280')
                    .attr('stroke-width', 1)
                    .attr('stroke-dasharray', '6,4')
                    .attr('opacity', 0.5);
                if (a.text) {
                    this.annotationsG.append('text')
                        .attr('x', a.x + 6)
                        .attr('y', a.y - 4)
                        .attr('font-size', '10px')
                        .attr('fill', a.color || '#6b7280')
                        .attr('opacity', 0.7)
                        .text(a.text);
                }
            } else if (a.type === 'label') {
                this.annotationsG.append('text')
                    .attr('x', a.x).attr('y', a.y)
                    .attr('font-size', a.fontSize || '10px')
                    .attr('font-weight', a.fontWeight || '400')
                    .attr('fill', a.color || '#8b8fa3')
                    .attr('text-anchor', a.anchor || 'start')
                    .text(a.text);
            } else if (a.type === 'stage_header') {
                this.annotationsG.append('text')
                    .attr('x', a.x).attr('y', a.y)
                    .attr('font-size', '14px')
                    .attr('font-weight', '700')
                    .attr('fill', a.color || '#e0e0e6')
                    .attr('text-anchor', 'middle')
                    .attr('letter-spacing', '0.08em')
                    .text(a.text);
            }
        });
    }

    // ================================================================== //
    //  Wire rendering                                                     //
    // ================================================================== //
    _renderWires(wires, components) {
        if (!wires || !wires.length) return;
        const self = this;
        this._busTrunks = null;   // cleared per render; repopulated by _renderBuses

        // Pre-pass: spread auto-routed feedback (right-to-left) wires onto
        // distinct horizontal lanes so they don't stack into one line.
        let fbLane = 0;
        wires.forEach(wire => {
            if (Array.isArray(wire.path) || wire.path === 'direct') return;
            const fc = components[wire.from.split('.')[0]];
            const tc = components[wire.to.split('.')[0]];
            if (!fc || !tc) return;
            const s = this._portPosition(fc, wire.from.split('.')[1]);
            const e = this._portPosition(tc, wire.to.split('.')[1]);
            if (s && e && e[0] < s[0] - 1) {
                wire._feedbackY = Math.max(s[1], e[1]) + 36 + fbLane * 16;
                fbLane++;
            }
        });

        // Resolve every wire's polyline up front so overlapping ones can be
        // fanned apart before drawing.
        const routed = [];
        wires.forEach(wire => {
            const pts = this._resolveWirePath(wire, components);
            if (pts && pts.length >= 2) routed.push({ wire, pts });
        });
        this._spreadSegments(routed);

        routed.forEach((entry) => {
            const { wire, pts } = entry;
            const fromComp = wire.from.split('.')[0];
            const toComp   = wire.to.split('.')[0];
            const layer    = wire.layer || this._classifyLayer(wire);
            const g = this.wiresG.append('g')
                .attr('class', `le-wire le-wire--${wire.style || 'data'} le-wire--layer-${layer}`)
                .attr('data-from', fromComp)
                .attr('data-to', toComp)
                .attr('data-layer', layer)
                .datum(wire);
            if (wire.bus) g.attr('data-bus', wire.bus);
            entry._g = g;         // referenced by the bus-collapse pass below
            entry._layer = layer;

            const pathStr = this._pointsToPath(pts);
            const isControl = wire.style === 'control';

            g.append('path')
                .attr('class', 'le-wire-line')
                .attr('d', pathStr)
                .attr('fill', 'none')
                .attr('stroke', isControl ? 'var(--text-muted, #8b8fa3)' : 'var(--border, #2a2e3a)')
                .attr('stroke-width', isControl ? 1 : 1.8)
                .attr('stroke-dasharray', isControl ? '4,3' : 'none')
                .attr('marker-end', isControl ? 'url(#le-arrow-control)' : 'url(#le-arrow-data)');

            // Invisible wide hit-area so a thin wire is easy to hover/trace.
            // (Components render above wires, so this only catches in the gaps.)
            g.append('path')
                .attr('class', 'le-wire-hit')
                .attr('d', pathStr)
                .attr('fill', 'none')
                .attr('stroke', 'transparent')
                .attr('stroke-width', 10)
                .style('pointer-events', 'stroke');

            // Wire label
            if (wire.label) {
                const mid = pts[Math.floor(pts.length / 2)];
                g.append('text')
                    .attr('class', 'le-wire-label')
                    .attr('x', mid[0])
                    .attr('y', mid[1] - 5)
                    .attr('text-anchor', 'middle')
                    .attr('font-size', '8px')
                    .attr('fill', 'var(--text-muted, #8b8fa3)')
                    .text(wire.label);
            }

            // Hover-to-trace: highlight this wire + its two endpoints, fade rest.
            g.on('mouseenter', () => self._trace(w => w === wire, [fromComp, toComp]))
             .on('mouseleave', () => self._clearTrace());
        });

        // Bus-collapse pass: only active for layouts that opt in
        // (layout.collapseBuses !== false) AND that actually tag wires with a
        // `bus` field. Non-OoO layouts carry neither, so this is a no-op there.
        this._renderBuses(routed);
    }

    /**
     * TECHNIQUE 1 — bus collapse. Groups routed wires by their `bus` id and,
     * for any bus with >=2 members, draws ONE thick rounded trunk (following
     * the longest / most-central member polyline) plus a label + count pill.
     * Member wires are moved into a hidden container revealed on hover/click.
     *
     * Scoped: does nothing unless the layout opts in with collapseBuses (any
     * value other than an explicit `false`) AND at least one wire has a `bus`.
     * This keeps single_cycle / pipeline / superscalar / multicycle untouched.
     */
    _renderBuses(routed) {
        const layout = this.layout || {};
        if (layout.collapseBuses === false) return;
        const hasBus = routed.some(r => r.wire && r.wire.bus);
        if (!hasBus) return;

        // Human-readable trunk labels per bus id.
        const BUS_LABELS = {
            cdb:      'CDB',
            dispatch: 'Dispatch',
            operand:  'Operands',
            commit:   'Commit',
            branch:   'Branch',
            execute:  'Execute',
        };

        // Group members by bus id.
        const groups = {};
        routed.forEach(entry => {
            const bus = entry.wire && entry.wire.bus;
            if (!bus) return;
            (groups[bus] = groups[bus] || []).push(entry);
        });

        this._busTrunks = {};   // bus id -> trunk <g> selection

        Object.keys(groups).forEach(bus => {
            const members = groups[bus];
            if (members.length < 2) return;   // a single wire is clearer left alone

            // Representative geometry = the longest member polyline (most
            // central / most likely to visually stand in for the group).
            let rep = members[0];
            let repLen = this._polyLength(rep.pts);
            members.forEach(m => {
                const len = this._polyLength(m.pts);
                if (len > repLen) { rep = m; repLen = len; }
            });

            // Layer of the bus = the (dominant) member layer; members should
            // all share one layer per the contract, so take the rep's.
            const layer = rep._layer || (rep.wire.layer) || this._classifyLayer(rep.wire);

            // Trunk container.
            const trunk = this.wiresG.append('g')
                .attr('class', `le-bus le-bus--${bus} le-wire--layer-${layer}`)
                .attr('data-bus', bus)
                .attr('data-layer', layer);
            this._busTrunks[bus] = trunk;

            const pathStr = this._pointsToPath(rep.pts);

            // Thick rounded trunk line.
            trunk.append('path')
                .attr('class', 'le-bus-trunk')
                .attr('d', pathStr)
                .attr('fill', 'none')
                .attr('stroke', 'var(--accent, #a78bfa)')
                .attr('stroke-width', 6)
                .attr('stroke-linecap', 'round')
                .attr('stroke-linejoin', 'round')
                .attr('opacity', 0.55)
                .attr('marker-end', 'url(#le-arrow-bus)');

            // Wide invisible hit-area for hover/click.
            trunk.append('path')
                .attr('class', 'le-bus-hit')
                .attr('d', pathStr)
                .attr('fill', 'none')
                .attr('stroke', 'transparent')
                .attr('stroke-width', 16)
                .style('pointer-events', 'stroke')
                .style('cursor', 'pointer');

            // Label + count pill at the polyline midpoint.
            const mid = rep.pts[Math.floor(rep.pts.length / 2)];
            const labelText = BUS_LABELS[bus] || bus;
            const pill = trunk.append('g')
                .attr('class', 'le-bus-badge')
                .attr('transform', `translate(${mid[0]},${mid[1] - 8})`);
            pill.append('rect')
                .attr('class', 'le-bus-pill')
                .attr('x', -32).attr('y', -9)
                .attr('width', 64).attr('height', 15)
                .attr('rx', 7).attr('ry', 7)
                .attr('fill', 'var(--bg-elev, #1a1e2a)')
                .attr('stroke', 'var(--accent, #a78bfa)')
                .attr('stroke-width', 0.75)
                .attr('opacity', 0.92);
            pill.append('text')
                .attr('class', 'le-bus-label')
                .attr('x', 0).attr('y', 0)
                .attr('text-anchor', 'middle')
                .attr('dominant-baseline', 'middle')
                .attr('font-size', '8px')
                .attr('font-weight', '700')
                .attr('fill', 'var(--accent, #a78bfa)')
                .text(`${labelText} ×${members.length}`);

            // Move member wire <g>s into a hidden container that the trunk
            // reveals on expand. (Re-appending relocates the existing nodes.)
            // Default to display:none inline so the collapse WORKS even before
            // the integrator's CSS lands; expand toggles it back on.
            const membersG = trunk.append('g')
                .attr('class', 'le-bus-members')
                .style('display', 'none');
            members.forEach(m => {
                if (m._g && !m._g.empty()) {
                    membersG.node().appendChild(m._g.node());
                }
            });

            // Hover expands (temporary); click locks the expanded state.
            let locked = false;
            const setExpanded = (on) => {
                trunk.classed('le-bus--expanded', on);
                membersG.style('display', on ? null : 'none');
            };
            trunk.on('mouseenter', () => { if (!locked) setExpanded(true); })
                 .on('mouseleave', () => { if (!locked) setExpanded(false); })
                 .on('click', (event) => {
                     if (event && event.stopPropagation) event.stopPropagation();
                     locked = !locked;
                     setExpanded(locked);
                     trunk.classed('le-bus--locked', locked);
                 });
        });
    }

    /** Total length of an [x,y] polyline (used to pick a bus trunk). */
    _polyLength(pts) {
        if (!pts || pts.length < 2) return 0;
        let len = 0;
        for (let i = 1; i < pts.length; i++) {
            const dx = pts[i][0] - pts[i - 1][0];
            const dy = pts[i][1] - pts[i - 1][1];
            len += Math.sqrt(dx * dx + dy * dy);
        }
        return len;
    }

    /**
     * TECHNIQUE 2 helper — default layer classification when a wire carries no
     * explicit `layer` field. Mirrors the OoO preset's grouping so even
     * untagged wires get a sensible bucket for the layer-toggle chips.
     */
    _classifyLayer(wire) {
        if (!wire) return 'data';
        if (wire.layer) return wire.layer;
        const from = wire.from || '';
        const to   = wire.to   || '';
        const combined = from + ' ' + to;
        // CDB: completion / common-data-bus traffic.
        if (/\.cdb_|\.complete_|\.exec_valid|\.exec_rob_tag/.test(combined) ||
            from.split('.')[0] === 'cdb_val') {
            return 'cdb';
        }
        // Commit: retire path into regfile / RAT / store commit.
        if (/\.commit_/.test(combined) ||
            from.split('.')[0] === 'store_commit' ||
            /->?\s*regfile\.(wen|rd_)/.test(combined) ||
            (to.indexOf('regfile.wen') !== -1) ||
            (to.indexOf('regfile.rd_') !== -1)) {
            return 'commit';
        }
        // Control-styled wires default to the control layer.
        if (wire.style === 'control') return 'control';
        return 'data';
    }

    /**
     * De-overlap pass: many wires (especially hand-routed ones) share the
     * exact same interior horizontal/vertical segments, smearing into one
     * thick band. Fan those collinear, overlapping interior segments apart
     * into parallel lanes. Endpoints (ports) and the orthogonal corners are
     * preserved — only interior segments whose neighbours are perpendicular
     * are nudged, so connectivity and right angles are kept.
     */
    _spreadSegments(routed) {
        const EPS = 1.5;       // axis-alignment tolerance
        const BUCKET = 5;      // group segments whose coord is within ~5px
        const SPACING = 5;     // lane spacing
        const MAX = 34;        // clamp how far a segment may move

        // Pass A: many hand-routed wires are single-corner "L" bends
        // ([start, corner, end]) that share a corridor and stack with no
        // interior segment to fan. Promote *clustered* L-bends (>=3 sharing a
        // mid-corridor channel) into two-corner "Z" staircases routed through
        // that channel, giving Pass B a spreadable interior segment.
        this._promoteClusteredCorners(routed, EPS);

        const verts = [];      // {pts, i, x, lo, hi}
        const horis = [];      // {pts, i, y, lo, hi}

        routed.forEach(({ pts }) => {
            // Only interior segments (i in [1, len-3]) whose neighbours are
            // perpendicular can be shifted without breaking the polyline.
            for (let i = 1; i <= pts.length - 3; i++) {
                const a = pts[i], b = pts[i + 1], p = pts[i - 1], q = pts[i + 2];
                const dx = Math.abs(a[0] - b[0]), dy = Math.abs(a[1] - b[1]);
                if (dx < EPS && dy >= EPS) {            // vertical segment
                    if (Math.abs(p[1] - a[1]) < EPS && Math.abs(q[1] - b[1]) < EPS) {
                        verts.push({ pts, i, x: a[0], lo: Math.min(a[1], b[1]), hi: Math.max(a[1], b[1]) });
                    }
                } else if (dy < EPS && dx >= EPS) {     // horizontal segment
                    if (Math.abs(p[0] - a[0]) < EPS && Math.abs(q[0] - b[0]) < EPS) {
                        horis.push({ pts, i, y: a[1], lo: Math.min(a[0], b[0]), hi: Math.max(a[0], b[0]) });
                    }
                }
            }
        });

        const fan = (segs, axis) => {                   // axis 0 = x (verticals), 1 = y (horizontals)
            const groups = {};
            segs.forEach(s => {
                const key = Math.round((axis === 0 ? s.x : s.y) / BUCKET);
                (groups[key] = groups[key] || []).push(s);
            });
            Object.values(groups).forEach(g => {
                if (g.length < 2) return;               // nothing to spread
                g.sort((m, n) => m.lo - n.lo);          // stable, top-to-bottom / left-to-right
                const n = g.length;
                g.forEach((s, idx) => {
                    let delta = (idx - (n - 1) / 2) * SPACING;
                    delta = Math.max(-MAX, Math.min(MAX, delta));
                    s.pts[s.i][axis] += delta;
                    s.pts[s.i + 1][axis] += delta;
                });
            });
        };

        fan(verts, 0);
        fan(horis, 1);
    }

    _promoteClusteredCorners(routed, EPS) {
        const GROUP = 28;       // corridor bucket size
        const cands = [];       // {r, type, c}
        routed.forEach(r => {
            const pts = r.pts;
            if (pts.length !== 3) return;               // only single-corner Ls
            const s = pts[0], w = pts[1], e = pts[2];
            const dxSE = Math.abs(e[0] - s[0]), dySE = Math.abs(e[1] - s[1]);
            if (Math.abs(w[1] - s[1]) < EPS && Math.abs(w[0] - e[0]) < EPS &&
                dxSE > 40 && dySE > 12) {
                // horizontal-then-vertical: channel is a vertical run at midX
                cands.push({ r, type: 'H', c: (s[0] + e[0]) / 2 });
            } else if (Math.abs(w[0] - s[0]) < EPS && Math.abs(w[1] - e[1]) < EPS &&
                       dySE > 40 && dxSE > 12) {
                // vertical-then-horizontal: channel is a horizontal run at midY
                cands.push({ r, type: 'V', c: (s[1] + e[1]) / 2 });
            }
        });
        const groups = {};
        cands.forEach(cd => {
            const k = cd.type + ':' + Math.round(cd.c / GROUP);
            (groups[k] = groups[k] || []).push(cd);
        });
        Object.values(groups).forEach(g => {
            if (g.length < 3) return;                   // only promote real clusters
            g.forEach(cd => {
                const pts = cd.r.pts, s = pts[0], e = pts[2];
                cd.r.pts = cd.type === 'H'
                    ? [s, [cd.c, s[1]], [cd.c, e[1]], e]
                    : [s, [s[0], cd.c], [e[0], cd.c], e];
            });
        });
    }

    // Highlight the wires matching `wirePred` and components in `compIds`,
    // fading everything else so a single connection can be followed.
    _trace(wirePred, compIds) {
        if (this.wiresG) {
            this.wiresG.classed('le-tracing', true);
            this.wiresG.selectAll('.le-wire').classed('le-wire--hot', d => !!(d && wirePred(d)));
        }
        if (this.componentsG) {
            this.componentsG.classed('le-tracing', true);
            this.componentsG.selectAll('.le-comp').classed('le-comp--trace', function () {
                return compIds.indexOf(d3.select(this).attr('data-comp-id')) !== -1;
            });
        }
    }

    _clearTrace() {
        if (this.wiresG) {
            this.wiresG.classed('le-tracing', false);
            this.wiresG.selectAll('.le-wire').classed('le-wire--hot', false);
        }
        if (this.componentsG) {
            this.componentsG.classed('le-tracing', false);
            this.componentsG.selectAll('.le-comp').classed('le-comp--trace', false);
        }
    }

    /**
     * Resolve a wire definition to an array of [x,y] waypoints.
     */
    _resolveWirePath(wire, components) {
        const fromParts = wire.from.split('.');
        const toParts   = wire.to.split('.');
        const fromComp  = components[fromParts[0]];
        const toComp    = components[toParts[0]];
        if (!fromComp || !toComp) return null;

        const fromPort = fromParts[1];
        const toPort   = toParts[1];
        const start    = this._portPosition(fromComp, fromPort);
        const end      = this._portPosition(toComp, toPort);
        if (!start || !end) return null;

        // Explicit waypoints
        if (Array.isArray(wire.path)) {
            return [start, ...wire.path, end];
        }

        // Direct line
        if (wire.path === 'direct') {
            return [start, end];
        }

        // Manhattan routing (default)
        return this._manhattanRoute(start, end, wire);
    }

    /**
     * Get the absolute [x,y] position of a named port on a component.
     */
    _portPosition(comp, portName) {
        const portDef = comp.ports && comp.ports[portName];
        if (portDef) {
            const side   = portDef.side   || 'right';
            const offset = portDef.offset || 0.5;
            return this._sidePos(comp, side, offset);
        }
        // Fallback: guess from port name patterns
        // Inputs go on left, outputs go on right
        const isInput = portName.endsWith('_in') || portName.endsWith('_addr') ||
                        portName === 'a' || portName === 'b' || portName === 'addr' ||
                        portName === 'wdata' || portName === 'wen' || portName === 'sel' ||
                        portName === 'op' || portName === 'stall' || portName === 'flush';
        const side = isInput ? 'left' : 'right';
        return this._sidePos(comp, side, 0.5);
    }

    _sidePos(comp, side, offset) {
        const x = comp.x || 0;
        const y = comp.y || 0;
        const w = comp.w || 100;
        const h = comp.h || 50;
        switch (side) {
            case 'left':   return [x,         y + h * offset];
            case 'right':  return [x + w,     y + h * offset];
            case 'top':    return [x + w * offset, y];
            case 'bottom': return [x + w * offset, y + h];
            default:       return [x + w,     y + h * 0.5];
        }
    }

    /**
     * Simple manhattan routing: one horizontal, one bend, one horizontal.
     * For backward wires, route below or above.
     */
    _manhattanRoute(start, end, wire) {
        const [x1, y1] = start;
        const [x2, y2] = end;
        const dx = x2 - x1;
        const dy = y2 - y1;

        // Forward: simple L-bend
        if (dx >= 0) {
            const midX = x1 + dx * 0.5;
            if (Math.abs(dy) < 3) {
                // Nearly horizontal -- direct
                return [start, end];
            }
            return [start, [midX, y1], [midX, y2], end];
        }

        // Backward wire (feedback): route below the main datapath
        const yOffset = wire._feedbackY || Math.max(y1, y2) + 40;
        return [
            start,
            [x1 + 15, y1],
            [x1 + 15, yOffset],
            [x2 - 15, yOffset],
            [x2 - 15, y2],
            end,
        ];
    }

    /**
     * Convert an array of [x,y] points into an SVG path 'd' string.
     * Uses smooth corners at bends.
     */
    _pointsToPath(pts) {
        if (pts.length < 2) return '';
        if (pts.length === 2) {
            return `M${pts[0][0]},${pts[0][1]} L${pts[1][0]},${pts[1][1]}`;
        }

        const radius = 5; // corner radius
        let d = `M${pts[0][0]},${pts[0][1]}`;

        for (let i = 1; i < pts.length - 1; i++) {
            const prev = pts[i - 1];
            const curr = pts[i];
            const next = pts[i + 1];

            // Direction vectors
            const dxIn  = curr[0] - prev[0];
            const dyIn  = curr[1] - prev[1];
            const dxOut = next[0] - curr[0];
            const dyOut = next[1] - curr[1];

            const lenIn  = Math.sqrt(dxIn * dxIn + dyIn * dyIn);
            const lenOut = Math.sqrt(dxOut * dxOut + dyOut * dyOut);

            if (lenIn === 0 || lenOut === 0) {
                d += ` L${curr[0]},${curr[1]}`;
                continue;
            }

            const r = Math.min(radius, lenIn * 0.4, lenOut * 0.4);

            // Point where we start the arc (on the incoming segment)
            const startArc = [
                curr[0] - (dxIn / lenIn) * r,
                curr[1] - (dyIn / lenIn) * r,
            ];
            // Point where we end the arc (on the outgoing segment)
            const endArc = [
                curr[0] + (dxOut / lenOut) * r,
                curr[1] + (dyOut / lenOut) * r,
            ];

            d += ` L${startArc[0]},${startArc[1]}`;
            d += ` Q${curr[0]},${curr[1]} ${endArc[0]},${endArc[1]}`;
        }

        const last = pts[pts.length - 1];
        d += ` L${last[0]},${last[1]}`;
        return d;
    }

    // ================================================================== //
    //  Component rendering                                                //
    // ================================================================== //
    _renderComponents(components) {
        if (!components) return;

        Object.entries(components).forEach(([id, comp]) => {
            const shape = comp.shape || 'rect';
            const g = this.componentsG.append('g')
                .attr('class', `le-comp le-comp--${comp.category || 'default'}`)
                .attr('data-comp-id', id)
                .attr('transform', `translate(${comp.x || 0},${comp.y || 0})`);

            const colors = LayoutEngine.CATEGORY_COLORS[comp.category] ||
                           LayoutEngine.CATEGORY_COLORS.default;

            if (shape === 'rect') {
                this._drawRect(g, comp, colors);
            } else if (shape === 'mux') {
                this._drawMux(g, comp, colors);
            } else if (shape === 'pipeline_bar') {
                this._drawPipelineBar(g, comp, colors);
            }

            // Port dots
            this._drawPortDots(g, comp);
        });
    }

    _drawRect(g, comp, colors) {
        const w = comp.w || 100;
        const h = comp.h || 50;

        g.append('rect')
            .attr('class', 'le-comp-body')
            .attr('width', w)
            .attr('height', h)
            .attr('rx', 8).attr('ry', 8)
            .attr('fill', colors.fill)
            .attr('stroke', colors.stroke)
            .attr('stroke-width', 1.5);

        // Label
        g.append('text')
            .attr('class', 'le-comp-label')
            .attr('x', w / 2)
            .attr('y', h * 0.38)
            .attr('text-anchor', 'middle')
            .attr('dominant-baseline', 'middle')
            .attr('font-size', '11px')
            .attr('font-weight', '600')
            .attr('fill', '#e0e0e6')
            .text(comp.label || '');

        // Detail text (updated by state)
        g.append('text')
            .attr('class', 'le-comp-detail')
            .attr('x', w / 2)
            .attr('y', h * 0.62)
            .attr('text-anchor', 'middle')
            .attr('dominant-baseline', 'middle')
            .attr('font-size', '9px')
            .attr('font-family', "'JetBrains Mono', 'Fira Code', monospace")
            .attr('fill', colors.text || '#d1d5db')
            .text('');

        // Instruction text (updated by instrMap)
        if (w >= 60) {
            g.append('text')
                .attr('class', 'le-comp-instr')
                .attr('x', w / 2)
                .attr('y', h * 0.86)
                .attr('text-anchor', 'middle')
                .attr('dominant-baseline', 'middle')
                .attr('font-size', '7px')
                .attr('font-family', "'JetBrains Mono', 'Fira Code', monospace")
                .attr('fill', 'var(--teal, #2dd4bf)')
                .attr('opacity', 0.8)
                .text('');
        }
    }

    _drawMux(g, comp, colors) {
        const w = comp.w || 30;
        const h = comp.h || 50;
        const dir = comp.direction || 'right'; // signal flow direction

        // Trapezoid points based on direction
        let points;
        if (dir === 'right') {
            // Narrow on left (inputs), wide on right (output)
            // Actually: mux selects, so wider on input side, narrow on output
            // Standard textbook: wider top/bottom on input side
            points = `0,0 ${w},${h * 0.2} ${w},${h * 0.8} 0,${h}`;
        } else if (dir === 'left') {
            points = `0,${h * 0.2} ${w},0 ${w},${h} 0,${h * 0.8}`;
        } else if (dir === 'down') {
            points = `0,0 ${w},0 ${w * 0.8},${h} ${w * 0.2},${h}`;
        } else {
            points = `${w * 0.2},0 ${w * 0.8},0 ${w},${h} 0,${h}`;
        }

        g.append('polygon')
            .attr('class', 'le-comp-body')
            .attr('points', points)
            .attr('fill', colors.fill)
            .attr('stroke', colors.stroke)
            .attr('stroke-width', 1.5);

        // Label
        g.append('text')
            .attr('class', 'le-comp-label')
            .attr('x', w / 2)
            .attr('y', h * 0.4)
            .attr('text-anchor', 'middle')
            .attr('dominant-baseline', 'middle')
            .attr('font-size', '9px')
            .attr('font-weight', '600')
            .attr('fill', '#e0e0e6')
            .text(comp.label || '');

        // Detail
        g.append('text')
            .attr('class', 'le-comp-detail')
            .attr('x', w / 2)
            .attr('y', h * 0.7)
            .attr('text-anchor', 'middle')
            .attr('dominant-baseline', 'middle')
            .attr('font-size', '8px')
            .attr('font-family', "'JetBrains Mono', 'Fira Code', monospace")
            .attr('fill', colors.text || '#d1d5db')
            .text('');
    }

    _drawPipelineBar(g, comp, colors) {
        const w = comp.w || 12;
        const h = comp.h || 200;

        g.append('rect')
            .attr('class', 'le-comp-body')
            .attr('width', w)
            .attr('height', h)
            .attr('rx', 3).attr('ry', 3)
            .attr('fill', colors.fill)
            .attr('stroke', colors.stroke)
            .attr('stroke-width', 1.5);

        // Vertical label
        if (comp.label) {
            g.append('text')
                .attr('class', 'le-comp-label')
                .attr('x', w / 2)
                .attr('y', h / 2)
                .attr('text-anchor', 'middle')
                .attr('dominant-baseline', 'middle')
                .attr('font-size', '8px')
                .attr('font-weight', '600')
                .attr('fill', colors.text || '#a5b4fc')
                .attr('transform', `rotate(-90, ${w / 2}, ${h / 2})`)
                .text(comp.label);
        }

        // Detail
        g.append('text')
            .attr('class', 'le-comp-detail')
            .attr('x', w / 2)
            .attr('y', h + 12)
            .attr('text-anchor', 'middle')
            .attr('font-size', '7px')
            .attr('font-family', "'JetBrains Mono', 'Fira Code', monospace")
            .attr('fill', colors.text || '#d1d5db')
            .text('');
    }

    _drawPortDots(g, comp) {
        if (!comp.ports) return;
        Object.entries(comp.ports).forEach(([portName, portDef]) => {
            const side   = portDef.side   || 'right';
            const offset = portDef.offset || 0.5;
            const w = comp.w || 100;
            const h = comp.h || 50;
            let cx, cy;
            switch (side) {
                case 'left':   cx = 0;  cy = h * offset; break;
                case 'right':  cx = w;  cy = h * offset; break;
                case 'top':    cx = w * offset; cy = 0; break;
                case 'bottom': cx = w * offset; cy = h; break;
                default:       cx = w;  cy = h * 0.5; break;
            }
            g.append('circle')
                .attr('class', 'le-port-dot')
                .attr('cx', cx)
                .attr('cy', cy)
                .attr('r', 2.5)
                .attr('fill', (LayoutEngine.CATEGORY_COLORS[comp.category] ||
                               LayoutEngine.CATEGORY_COLORS.default).stroke);
        });
    }

    // ================================================================== //
    //  Zoom / pan                                                         //
    // ================================================================== //
    _setupZoom() {
        const zoom = d3.zoom()
            .scaleExtent([0.25, 4])
            .on('zoom', (event) => {
                this.rootG.attr('transform', event.transform);
            });
        this.svg.call(zoom);

        // Double-click to reset
        this.svg.on('dblclick.zoom', () => {
            this.svg.transition().duration(400).call(zoom.transform, d3.zoomIdentity);
        });
    }

    // ================================================================== //
    //  Tooltips                                                           //
    // ================================================================== //
    _setupTooltip(components) {
        this._removeTooltip();
        this.tooltipDiv = d3.select('body').append('div')
            .attr('class', 'le-tooltip')
            .style('display', 'none');

        const self = this;

        this.componentsG.selectAll('.le-comp')
            .on('mouseenter', function (event) {
                const id = d3.select(this).attr('data-comp-id');
                // Trace this component's wires (works even before a run).
                self._trace(
                    w => w && (w.from.split('.')[0] === id || w.to.split('.')[0] === id),
                    [id]);
                const compState = self._state && self._state[id];
                if (!compState) return;

                let html = `<div class="le-tooltip-title">${components[id]?.label || id}</div><dl>`;
                for (const [k, v] of Object.entries(compState)) {
                    if (k === 'registers' || k === 'entries') continue;
                    if (k === 'memory' || k === 'program' || k === 'program_bytes') continue;
                    const display = typeof v === 'number'
                        ? `0x${(v >>> 0).toString(16).toUpperCase()}`
                        : String(v);
                    html += `<dt>${k}</dt><dd>${display}</dd>`;
                }
                html += '</dl>';
                self.tooltipDiv.html(html).style('display', 'block');
            })
            .on('mousemove', function (event) {
                self.tooltipDiv
                    .style('left', (event.pageX + 14) + 'px')
                    .style('top',  (event.pageY - 12) + 'px');
            })
            .on('mouseleave', function () {
                self.tooltipDiv.style('display', 'none');
                self._clearTrace();
            })
            .on('click', function (event) {
                event.stopPropagation();
                const id = d3.select(this).attr('data-comp-id');
                const label = components[id]?.label || id;
                self._selectedCompId = id;

                // Highlight selected component
                self.componentsG.selectAll('.le-comp').classed('le-comp--selected', false);
                d3.select(this).classed('le-comp--selected', true);

                // Dispatch custom event for cpu_simulator.js to handle
                document.dispatchEvent(new CustomEvent('comp-detail-click', {
                    detail: { compId: id, label: label }
                }));
            });
    }

    clearSelection() {
        this._selectedCompId = null;
        if (this.componentsG) {
            this.componentsG.selectAll('.le-comp').classed('le-comp--selected', false);
        }
    }

    _removeTooltip() {
        if (this.tooltipDiv) {
            this.tooltipDiv.remove();
            this.tooltipDiv = null;
        }
        // Remove any orphaned tooltips from previous renders
        d3.selectAll('.le-tooltip').remove();
    }

    // ================================================================== //
    //  State summarisation (same logic as cpu_simulator.js)                //
    // ================================================================== //
    _summarize(compId, state) {
        if (!state) return '';

        switch (compId) {
            case 'fetch':
                return state.pc !== undefined ? `PC=0x${(state.pc >>> 0).toString(16).toUpperCase()}` : '';
            case 'imem':
                return state.data !== undefined ? `0x${(state.data >>> 0).toString(16).toUpperCase()}` : '';
            case 'decode':
                return `${state.alu_op || ''} rd=${state.rd !== undefined ? state.rd : '?'}`;
            case 'regfile':
                return '';
            case 'alu':
                return state.result !== undefined ? `0x${(state.result >>> 0).toString(16).toUpperCase()}` : '';
            case 'alu_mux':
                return '';
            case 'dmem':
                return state.wen ? 'WRITE' : (state.rdata !== undefined ? 'READ' : '');
            case 'wb':
                return state.sel || '';
            case 'branch':
                return state.branch_taken ? 'TAKEN' : '';
            case 'bpred':
                return String(state.prediction || '');
            case 'flags_reg': {
                const z = state.zero ? 'Z=1' : 'Z=0';
                const wf = state.write_flags ? ' SET' : '';
                return z + wf;
            }

            // Pipeline registers (state exposes bare keys, hex strings)
            case 'if_id':
                return state.instr !== undefined ? `I=${state.instr}` : '';
            case 'id_ex':
                return state.alu_op !== undefined ? `op=${state.alu_op}` : '';
            case 'ex_mem':
                return state.alu_result !== undefined ? `R=${state.alu_result}` : '';
            case 'mem_wb':
                return state.rd !== undefined ? `rd=${state.rd}` : '';

            // Pipeline components
            case 'hazard_det':
                return state.stall === 'STALL' ? 'STALL' : 'OK';
            case 'forwarding':
                return (state.fwd_a || state.fwd_b) ? 'FWD' : '';

            // OoO components
            case 'rob':
                return state.count !== undefined ? `${state.count} entries` : '';
            case 'rs': {
                const n = Array.isArray(state.entries)
                    ? state.entries.filter(e => e.valid).length : 0;
                return n ? `${n} active` : '';
            }
            case 'rat':
                return '';

            default:
                return '';
        }
    }

    // ================================================================== //
    //  Cleanup                                                            //
    // ================================================================== //
    destroy() {
        this._removeTooltip();
        this.svg.selectAll('*').remove();
    }
}

// Export to global scope
window.LayoutEngine = LayoutEngine;
