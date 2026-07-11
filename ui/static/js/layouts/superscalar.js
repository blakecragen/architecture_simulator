/**
 * RTL CPU Simulator -- Superscalar Pipeline Layout Template
 *
 * N-lane superscalar (1-6 lanes) with VERTICAL lane stacking.
 *
 * Layout (stages run left-to-right, lanes stack top-to-bottom):
 *
 *           IF        |IF/ID|     ID         |ID/EX|     EX         |EX/MEM|    MEM      |MEM/WB|    WB
 *         ┌────────┐  ║    ║  ┌──────────┐   ║    ║  ┌──────────┐  ║     ║  ┌────────┐  ║     ║  ┌──────────┐
 * Lane 0  │ Wide   │  ║    ║  │ Decoder 0│   ║    ║  │ ALU 0    │  ║     ║  │ Shared │  ║     ║  │  WB 0    │
 *         │ Fetch  │  ║    ║  ├──────────┤   ║    ║  ├──────────┤  ║     ║  │ Data   │  ║     ║  ├──────────┤
 * Lane 1  │        │  ║    ║  │ Decoder 1│   ║    ║  │ ALU 1    │  ║     ║  │ Memory │  ║     ║  │  WB 1    │
 *         │ Wide   │  ║    ║  ├──────────┤   ║    ║  ├──────────┤  ║     ║  │        │  ║     ║  ├──────────┤
 * Lane 2  │ IMem   │  ║    ║  │ Decoder 2│   ║    ║  │ ALU 2    │  ║     ║  │        │  ║     ║  │  WB 2    │
 *         └────────┘  ║    ║  └──────────┘   ║    ║  └──────────┘  ║     ║  └────────┘  ║     ║  └──────────┘
 *                     ║    ║  [Wide RegFile]  ║    ║                ║     ║              ║     ║
 *
 *         [Cross-Lane Hazard Detector]      [Wide Forwarding Unit]
 *         [Branch Predictor]                [Branch Resolution]
 */

/* global window */

function getSuperscalarLayout(numLanes) {
    numLanes = Math.max(1, Math.min(numLanes || 2, 6));

    // ── Dimensions ───────────────────────────────────────────────
    const STAGE_W   = 200;
    const GAP       = 48;
    const BAR_W     = 14;
    const MARGIN_L  = 60;   // left margin for lane labels
    const MARGIN_T  = 50;   // top margin for stage headers
    const LANE_H    = 72;   // height per lane row (was 68)
    const LANE_GAP  = 12;   // gap between lane rows (was 6)
    const COMP_H    = 58;   // component height (fits inside LANE_H)
    const COMP_W    = 155;
    const COMP_PAD  = 20;   // horizontal padding inside stage column

    const stageX = (i) => MARGIN_L + i * (STAGE_W + GAP);
    const barX   = (i) => stageX(i) + STAGE_W + (GAP - BAR_W) / 2;

    // Vertical positions
    const HEADER_Y = 10;
    const LANES_TOP = MARGIN_T;
    const laneY = (n) => LANES_TOP + n * (LANE_H + LANE_GAP);
    const lanesBottom = laneY(numLanes);
    const SHARED_ROW_Y = lanesBottom + 10;  // shared components row (regfile, dmem below lanes)
    const SHARED_H = 55;
    const CONTROL_Y = SHARED_ROW_Y + SHARED_H + 58;

    const BAR_H = lanesBottom - LANES_TOP + SHARED_H + 20;  // pipeline bars span all lanes + shared

    const W = stageX(5) + 20;
    const H = CONTROL_Y + 65;

    // ── Stage definitions ────────────────────────────────────────
    const stageDefs = [
        { id: 'IF',  label: 'IF',  color: '#3b82f6' },
        { id: 'ID',  label: 'ID',  color: '#14b8a6' },
        { id: 'EX',  label: 'EX',  color: '#a78bfa' },
        { id: 'MEM', label: 'MEM', color: '#f59e0b' },
        { id: 'WB',  label: 'WB',  color: '#22c55e' },
    ];
    const stages = stageDefs.map((s, i) => ({
        id: s.id, label: s.label,
        x: stageX(i), w: STAGE_W, color: s.color,
    }));

    const components = {};
    const wires = [];

    // ================================================================ //
    //  IF Stage — shared Wide Fetch + Wide IMem (spans all lanes)       //
    // ================================================================ //
    const ifSpanH = numLanes * (LANE_H + LANE_GAP) - LANE_GAP;
    const ifHalfH = Math.max(COMP_H, ifSpanH * 0.45);

    components.fetch = {
        x: stageX(0) + COMP_PAD, y: LANES_TOP, w: COMP_W, h: ifHalfH,
        shape: 'rect', label: 'Wide Fetch', category: 'fetch',
        ports: {
            pc_out:       { side: 'right', offset: 0.3 },
            next_pc:      { side: 'left',  offset: 0.5 },
            branch_taken: { side: 'left',  offset: 0.3 },
            stall:        { side: 'top',   offset: 0.5 },
        },
    };

    components.imem = {
        x: stageX(0) + COMP_PAD, y: LANES_TOP + ifHalfH + 10,
        w: COMP_W, h: Math.max(COMP_H, ifSpanH - ifHalfH - 10),
        shape: 'rect', label: 'Wide IMem', category: 'fetch',
        ports: {
            addr: { side: 'left', offset: 0.5 },
        },
    };
    // Add per-lane data ports to IMem
    for (let n = 0; n < numLanes; n++) {
        const frac = (n + 0.5) / numLanes;
        components.imem.ports[`data_${n}`] = { side: 'right', offset: frac };
    }

    wires.push({ from: 'fetch.pc_out', to: 'imem.addr', path: 'manhattan', style: 'data', label: 'PC' });

    // IF/ID pipeline bar
    components.if_id = {
        x: barX(0), y: LANES_TOP, w: BAR_W, h: BAR_H,
        shape: 'pipeline_bar', label: 'IF/ID', category: 'pipeline',
        ports: (() => {
            const ports = {};
            for (let n = 0; n < numLanes; n++) {
                const frac = (n + 0.5) / numLanes * 0.85 + 0.05;
                ports[`instr_in_${n}`]  = { side: 'left',  offset: frac };
                ports[`instr_out_${n}`] = { side: 'right', offset: frac };
            }
            ports.stall = { side: 'top',    offset: 0.5 };
            ports.flush = { side: 'bottom', offset: 0.5 };
            return ports;
        })(),
    };

    // IMem -> IF/ID per lane
    for (let n = 0; n < numLanes; n++) {
        wires.push({
            from: `imem.data_${n}`, to: `if_id.instr_in_${n}`,
            path: 'manhattan', style: 'data',
        });
    }

    // ================================================================ //
    //  Per-Lane Components (stacked vertically)                         //
    // ================================================================ //
    for (let n = 0; n < numLanes; n++) {
        const yOff = laneY(n);
        const sfx = `_${n}`;

        // -- Decoder -------------------------------------------------- //
        const decId = `decode${sfx}`;
        components[decId] = {
            x: stageX(1) + COMP_PAD, y: yOff, w: COMP_W, h: COMP_H,
            shape: 'rect', label: `Decoder ${n}`, category: 'decode',
            ports: {
                instr_in: { side: 'left',   offset: 0.5 },
                rs1:      { side: 'right',  offset: 0.15 },
                rs2:      { side: 'right',  offset: 0.35 },
                rd:       { side: 'right',  offset: 0.55 },
                imm:      { side: 'right',  offset: 0.7 },
                alu_op:   { side: 'right',  offset: 0.85 },
                reg_write:{ side: 'bottom', offset: 0.5 },
                branch:   { side: 'bottom', offset: 0.2 },
            },
        };

        // IF/ID -> Decoder
        wires.push({
            from: `if_id.instr_out_${n}`, to: `${decId}.instr_in`,
            path: 'manhattan', style: 'data',
        });

        // -- ALU Mux + ALU -------------------------------------------- //
        const muxId = `alu_mux${sfx}`;
        const aluId = `alu${sfx}`;

        components[muxId] = {
            x: stageX(2) + COMP_PAD, y: yOff + 4, w: 28, h: COMP_H - 8,
            shape: 'mux', label: 'M', category: 'execute', direction: 'right',
            ports: {
                rs1_data: { side: 'left',   offset: 0.25 },
                rs2_data: { side: 'left',   offset: 0.55 },
                imm:      { side: 'left',   offset: 0.8 },
                alu_src:  { side: 'bottom', offset: 0.5 },
                alu_a:    { side: 'right',  offset: 0.3 },
                alu_b:    { side: 'right',  offset: 0.7 },
            },
        };

        components[aluId] = {
            x: stageX(2) + COMP_PAD + 40, y: yOff, w: COMP_W - 50, h: COMP_H,
            shape: 'rect', label: `ALU ${n}`, category: 'execute',
            ports: {
                a:      { side: 'left',  offset: 0.3 },
                b:      { side: 'left',  offset: 0.7 },
                op:     { side: 'top',   offset: 0.5 },
                result: { side: 'right', offset: 0.35 },
                zero:   { side: 'right', offset: 0.7 },
            },
        };

        // Mux -> ALU
        wires.push({ from: `${muxId}.alu_a`, to: `${aluId}.a`, path: 'manhattan', style: 'data' });
        wires.push({ from: `${muxId}.alu_b`, to: `${aluId}.b`, path: 'manhattan', style: 'data' });

        // -- Writeback ------------------------------------------------- //
        const wbId = `wb${sfx}`;
        components[wbId] = {
            x: stageX(4) + COMP_PAD, y: yOff, w: COMP_W, h: COMP_H,
            shape: 'rect', label: `WB ${n}`, category: 'writeback',
            ports: {
                alu_in:   { side: 'left',  offset: 0.25 },
                mem_in:   { side: 'left',  offset: 0.55 },
                pc4_in:   { side: 'left',  offset: 0.8 },
                sel:      { side: 'top',   offset: 0.5 },
                data_out: { side: 'right', offset: 0.5 },
            },
        };
    }

    // ================================================================ //
    //  ID/EX Pipeline Bar (spans all lanes)                             //
    // ================================================================ //
    components.id_ex = {
        x: barX(1), y: LANES_TOP, w: BAR_W, h: BAR_H,
        shape: 'pipeline_bar', label: 'ID/EX', category: 'pipeline',
        ports: (() => {
            const ports = {};
            for (let n = 0; n < numLanes; n++) {
                const frac = (n + 0.5) / numLanes * 0.85 + 0.05;
                ports[`data_in_${n}`]  = { side: 'left',  offset: frac };
                ports[`data_out_${n}`] = { side: 'right', offset: frac };
            }
            ports.stall = { side: 'top',    offset: 0.5 };
            ports.flush = { side: 'bottom', offset: 0.5 };
            return ports;
        })(),
    };

    // Decoder -> ID/EX -> ALU Mux (simplified wiring)
    for (let n = 0; n < numLanes; n++) {
        wires.push({
            from: `decode_${n}.alu_op`, to: `id_ex.data_in_${n}`,
            path: 'manhattan', style: 'data',
        });
        wires.push({
            from: `id_ex.data_out_${n}`, to: `alu_mux_${n}.rs1_data`,
            path: 'manhattan', style: 'data',
        });
    }

    // ================================================================ //
    //  EX/MEM Pipeline Bar                                              //
    // ================================================================ //
    components.ex_mem = {
        x: barX(2), y: LANES_TOP, w: BAR_W, h: BAR_H,
        shape: 'pipeline_bar', label: 'EX/MEM', category: 'pipeline',
        ports: (() => {
            const ports = {};
            for (let n = 0; n < numLanes; n++) {
                const frac = (n + 0.5) / numLanes * 0.85 + 0.05;
                ports[`result_in_${n}`]  = { side: 'left',  offset: frac };
                ports[`result_out_${n}`] = { side: 'right', offset: frac };
            }
            ports.flush = { side: 'bottom', offset: 0.5 };
            return ports;
        })(),
    };

    for (let n = 0; n < numLanes; n++) {
        wires.push({
            from: `alu_${n}.result`, to: `ex_mem.result_in_${n}`,
            path: 'manhattan', style: 'data',
        });
    }

    // ================================================================ //
    //  MEM Stage — shared Data Memory                                   //
    // ================================================================ //
    const dmemH = Math.max(COMP_H, numLanes * (LANE_H + LANE_GAP) - LANE_GAP);
    components.dmem = {
        x: stageX(3) + COMP_PAD, y: LANES_TOP, w: COMP_W, h: dmemH,
        shape: 'rect', label: 'Data Memory', category: 'memory',
        ports: {
            addr:  { side: 'left',  offset: 0.15 },
            wdata: { side: 'left',  offset: 0.4 },
            wen:   { side: 'top',   offset: 0.5 },
            rdata: { side: 'right', offset: 0.5 },
        },
    };

    wires.push({
        from: 'ex_mem.result_out_0', to: 'dmem.addr',
        path: 'manhattan', style: 'data', label: 'addr (lane 0)',
    });

    // ================================================================ //
    //  MEM/WB Pipeline Bar                                              //
    // ================================================================ //
    components.mem_wb = {
        x: barX(3), y: LANES_TOP, w: BAR_W, h: BAR_H,
        shape: 'pipeline_bar', label: 'MEM/WB', category: 'pipeline',
        ports: (() => {
            const ports = {};
            for (let n = 0; n < numLanes; n++) {
                const frac = (n + 0.5) / numLanes * 0.85 + 0.05;
                ports[`data_in_${n}`]  = { side: 'left',  offset: frac };
                ports[`data_out_${n}`] = { side: 'right', offset: frac };
            }
            return ports;
        })(),
    };

    // EX/MEM -> MEM/WB pass-through, DMem -> MEM/WB lane 0
    for (let n = 0; n < numLanes; n++) {
        wires.push({
            from: `ex_mem.result_out_${n}`, to: `mem_wb.data_in_${n}`,
            path: [
                [barX(2) + BAR_W, LANES_TOP + BAR_H * ((n + 0.5) / numLanes * 0.85 + 0.05)],
                [barX(2) + BAR_W + 8 + n * 3, LANES_TOP + BAR_H * ((n + 0.5) / numLanes * 0.85 + 0.05)],
                [barX(2) + BAR_W + 8 + n * 3, LANES_TOP - 8 - n * 3],
                [barX(3) - 8 - n * 3, LANES_TOP - 8 - n * 3],
                [barX(3) - 8 - n * 3, LANES_TOP + BAR_H * ((n + 0.5) / numLanes * 0.85 + 0.05)],
                [barX(3), LANES_TOP + BAR_H * ((n + 0.5) / numLanes * 0.85 + 0.05)],
            ],
            style: 'data',
        });
    }

    // MEM/WB -> WB
    for (let n = 0; n < numLanes; n++) {
        wires.push({
            from: `mem_wb.data_out_${n}`, to: `wb_${n}.alu_in`,
            path: 'manhattan', style: 'data',
        });
    }

    // ================================================================ //
    //  Shared: Register File (below lanes in ID column)                 //
    // ================================================================ //
    components.regfile = {
        x: stageX(1) + COMP_PAD, y: SHARED_ROW_Y, w: COMP_W, h: SHARED_H,
        shape: 'rect', label: 'Wide Register File', category: 'decode',
        ports: (() => {
            const p = {};
            for (let n = 0; n < numLanes; n++) {
                const f1 = (n + 0.3) / numLanes;
                const f2 = (n + 0.7) / numLanes;
                p[`rs1_data_${n}`] = { side: 'top', offset: f1 };
                p[`rs2_data_${n}`] = { side: 'top', offset: f2 };
            }
            p.rd_data = { side: 'bottom', offset: 0.3 };
            p.wen     = { side: 'bottom', offset: 0.7 };
            return p;
        })(),
    };

    // Regfile reads feed up into decoders (representative wires)
    for (let n = 0; n < numLanes; n++) {
        wires.push({
            from: `decode_${n}.rs1`, to: `regfile.rs1_data_${n}`,
            path: 'manhattan', style: 'data',
        });
    }

    // ================================================================ //
    //  Shared: Branch Resolution (below lanes in MEM column)            //
    // ================================================================ //
    components.branch = {
        x: stageX(3) + COMP_PAD, y: SHARED_ROW_Y, w: COMP_W, h: SHARED_H,
        shape: 'rect', label: 'Branch Resolution', category: 'control',
        ports: {
            next_pc:      { side: 'left',  offset: 0.35 },
            branch_taken: { side: 'left',  offset: 0.65 },
            pc:           { side: 'right', offset: 0.3 },
            imm:          { side: 'right', offset: 0.6 },
            alu_zero:     { side: 'top',   offset: 0.5 },
        },
    };

    // ================================================================ //
    //  Shared: Flags Register (below lanes in EX column, for ARM/x86)   //
    // ================================================================ //
    components.flags_reg = {
        x: stageX(2) + COMP_PAD, y: SHARED_ROW_Y + SHARED_H + 8, w: COMP_W, h: 38,
        shape: 'rect', label: 'Flags Register', category: 'execute',
        ports: {
            alu_zero_in:   { side: 'top', offset: 0.3 },
            alu_result_in: { side: 'top', offset: 0.7 },
            zero_out:      { side: 'right', offset: 0.5 },
        },
    };

    // Branch -> Fetch feedback
    wires.push({
        from: 'branch.next_pc', to: 'fetch.next_pc',
        path: [
            [stageX(3) + COMP_PAD, SHARED_ROW_Y + SHARED_H * 0.35],
            [stageX(3), SHARED_ROW_Y + SHARED_H * 0.35],
            [stageX(3), H - 15],
            [MARGIN_L - 10, H - 15],
            [MARGIN_L - 10, LANES_TOP + components.fetch.h * 0.5],
            [stageX(0) + COMP_PAD, LANES_TOP + components.fetch.h * 0.5],
        ],
        style: 'data', label: 'next_pc',
    });
    wires.push({
        from: 'branch.mispredict', to: 'fetch.branch_taken',
        path: [
            [stageX(3) + COMP_PAD, SHARED_ROW_Y + SHARED_H * 0.65],
            [stageX(3) - 5, SHARED_ROW_Y + SHARED_H * 0.65],
            [stageX(3) - 5, H - 8],
            [MARGIN_L - 15, H - 8],
            [MARGIN_L - 15, LANES_TOP + components.fetch.h * 0.3],
            [stageX(0) + COMP_PAD, LANES_TOP + components.fetch.h * 0.3],
        ],
        style: 'control', label: 'flush',
    });

    // ================================================================ //
    //  Shared: Branch Predictor (bottom-left)                          //
    // ================================================================ //
    components.bpred = {
        x: stageX(0) + COMP_PAD, y: CONTROL_Y, w: COMP_W, h: 40,
        shape: 'rect', label: 'Branch Predictor', category: 'control',
        ports: {
            pc:        { side: 'left',  offset: 0.5 },
            actual:    { side: 'right', offset: 0.5 },
        },
    };

    // ================================================================ //
    //  Cross-Lane Hazard Detector (spans ID-EX below lanes)             //
    // ================================================================ //
    components.hazard_det = {
        x: stageX(1), y: CONTROL_Y, w: stageX(2) + STAGE_W - stageX(1), h: 40,
        shape: 'rect', label: 'Cross-Lane Hazard Detector', category: 'control',
        ports: {
            stall: { side: 'top', offset: 0.3 },
        },
    };

    // Hazard -> Fetch stall
    wires.push({
        from: 'hazard_det.stall', to: 'fetch.stall',
        path: [
            [stageX(1) + (stageX(2) + STAGE_W - stageX(1)) * 0.3, CONTROL_Y],
            [stageX(1) + (stageX(2) + STAGE_W - stageX(1)) * 0.3, CONTROL_Y - 10],
            [stageX(0) + COMP_PAD + COMP_W * 0.5, CONTROL_Y - 10],
            [stageX(0) + COMP_PAD + COMP_W * 0.5, LANES_TOP],
        ],
        style: 'control', label: 'stall',
    });

    // ================================================================ //
    //  Wide Forwarding Unit (in EX column, below lanes)                 //
    // ================================================================ //
    components.forwarding = {
        x: stageX(2) + COMP_PAD - 5, y: SHARED_ROW_Y, w: COMP_W + 10, h: SHARED_H,
        shape: 'rect', label: 'Wide Forwarding', category: 'execute',
        ports: (() => {
            const p = {};
            for (let n = 0; n < numLanes; n++) {
                const frac = (n + 0.5) / numLanes;
                p[`fwd_out_${n}`] = { side: 'top', offset: frac };
            }
            p.ex_mem_data = { side: 'right', offset: 0.3 };
            p.mem_wb_data = { side: 'right', offset: 0.7 };
            return p;
        })(),
    };

    // Forwarding feedback arcs (from EX/MEM back to forwarding unit)
    wires.push({
        from: 'ex_mem.result_out_0', to: 'forwarding.ex_mem_data',
        path: [
            [barX(2) + BAR_W, LANES_TOP + BAR_H * 0.1],
            [barX(2) + BAR_W + 20, LANES_TOP + BAR_H * 0.1],
            [barX(2) + BAR_W + 20, SHARED_ROW_Y + SHARED_H * 0.3],
            [stageX(2) + COMP_PAD + COMP_W + 5, SHARED_ROW_Y + SHARED_H * 0.3],
        ],
        style: 'control', label: 'fwd EX',
    });

    // ================================================================ //
    //  Annotations                                                      //
    // ================================================================ //
    const annotations = [
        {
            type: 'label', x: W / 2, y: HEADER_Y,
            text: `${numLanes}-Wide Superscalar Pipeline`,
            color: '#e0e0e6', fontSize: '16px', fontWeight: '700', anchor: 'middle',
        },
    ];

    // Lane labels on left side
    for (let n = 0; n < numLanes; n++) {
        annotations.push({
            type: 'label',
            x: 8, y: laneY(n) + COMP_H / 2 + 4,
            text: `L${n}`, color: '#6b7394',
            fontSize: '11px', fontWeight: '700',
        });
        // Horizontal lane divider line (subtle)
        if (n > 0) {
            annotations.push({
                type: 'dashed_box',
                x: MARGIN_L - 5, y: laneY(n) - LANE_GAP / 2 - 1,
                w: W - MARGIN_L - 10, h: 0,
                text: '', color: '#1e2235',
            });
        }
    }

    // Dashed box around hazard detection area
    annotations.push({
        type: 'dashed_box',
        x: stageX(1) - 5, y: CONTROL_Y - 5,
        w: stageX(2) + STAGE_W - stageX(1) + 10, h: 50,
        text: 'Hazard Detection', color: '#f43f5e',
    });

    // Dashed box around forwarding area
    annotations.push({
        type: 'dashed_box',
        x: stageX(2) + COMP_PAD - 10, y: SHARED_ROW_Y - 5,
        w: COMP_W + 20, h: SHARED_H + 10,
        text: 'Forwarding', color: '#a78bfa',
    });

    return { width: W, height: H, components, wires, annotations, stages };
}

// Export
window.getSuperscalarLayout = getSuperscalarLayout;
