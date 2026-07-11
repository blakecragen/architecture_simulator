/**
 * RTL CPU Simulator -- Single-Cycle Layout Template
 *
 * Textbook single-cycle datapath, left-to-right flow:
 *
 *   PC -> [IMem] -> [Decode] -> [RegFile] -> <ALU Mux> -> [ALU] -> [DMem] -> <WB Mux> -> [WB]
 *                                                                      |
 *                                                              [Branch Resolution] --> PC feedback
 *
 *   [Branch Predictor] at bottom
 *
 * Layout: ~1200 x 500
 * Component IDs match the simulator: fetch, imem, decode, regfile, alu_mux,
 * alu, dmem, wb, branch, bpred
 */

/* global window */

function getSingleCycleLayout() {
    const W = 1260;
    const H = 460;

    // --- Main datapath row (y baseline) -------------------------------- //
    const ROW_Y  = 100;
    const ROW_H  = 60;

    // --- Component x positions (left-to-right) ------------------------- //
    const PC_X      = 30;
    const IMEM_X    = 180;
    const DEC_X     = 370;
    const REG_X     = 540;
    const MUX_A_X   = 700;
    const ALU_X     = 775;
    const DMEM_X    = 940;
    const MUX_WB_X  = 1080;
    const WB_X      = 1140;

    // --- Secondary rows ------------------------------------------------ //
    const BRANCH_Y  = 220;
    const BPRED_Y   = 340;

    const components = {
        // -- Main datapath ------------------------------------------------ //
        fetch: {
            x: PC_X, y: ROW_Y, w: 100, h: ROW_H,
            shape: 'rect', label: 'Fetch / PC', category: 'fetch',
            ports: {
                pc_out:       { side: 'right', offset: 0.35 },
                pc4_out:      { side: 'right', offset: 0.65 },
                next_pc:      { side: 'bottom', offset: 0.3 },
                branch_taken: { side: 'bottom', offset: 0.7 },
                stall:        { side: 'top', offset: 0.5 },
            },
        },
        imem: {
            x: IMEM_X, y: ROW_Y, w: 120, h: ROW_H,
            shape: 'rect', label: 'Instr Memory', category: 'fetch',
            ports: {
                addr: { side: 'left', offset: 0.5 },
                data: { side: 'right', offset: 0.5 },
            },
        },
        decode: {
            x: DEC_X, y: ROW_Y - 10, w: 120, h: ROW_H + 20,
            shape: 'rect', label: 'Decoder', category: 'decode',
            ports: {
                instr_in:     { side: 'left', offset: 0.35 },
                rs1:          { side: 'right', offset: 0.2 },
                rs2:          { side: 'right', offset: 0.35 },
                rd:           { side: 'right', offset: 0.5 },
                imm:          { side: 'right', offset: 0.65 },
                alu_op:       { side: 'right', offset: 0.8 },
                alu_src:      { side: 'bottom', offset: 0.3 },
                mem_write:    { side: 'bottom', offset: 0.5 },
                mem_read:     { side: 'bottom', offset: 0.6 },
                reg_write:    { side: 'bottom', offset: 0.7 },
                wb_sel:       { side: 'bottom', offset: 0.8 },
                branch:       { side: 'bottom', offset: 0.15 },
                branch_cond:  { side: 'bottom', offset: 0.25 },
                jal:          { side: 'bottom', offset: 0.4 },
                jalr:         { side: 'bottom', offset: 0.5 },
                use_pc:       { side: 'bottom', offset: 0.9 },
            },
        },
        regfile: {
            x: REG_X, y: ROW_Y - 15, w: 110, h: ROW_H + 30,
            shape: 'rect', label: 'Register File', category: 'decode',
            ports: {
                rs1_addr: { side: 'left', offset: 0.25 },
                rs2_addr: { side: 'left', offset: 0.45 },
                rs1_data: { side: 'right', offset: 0.25 },
                rs2_data: { side: 'right', offset: 0.45 },
                rd_addr:  { side: 'left', offset: 0.75 },
                rd_data:  { side: 'left', offset: 0.88 },
                wen:      { side: 'top', offset: 0.5 },
            },
        },
        alu_mux: {
            x: MUX_A_X, y: ROW_Y + 2, w: 28, h: ROW_H - 4,
            shape: 'mux', label: 'M', category: 'execute', direction: 'right',
            ports: {
                rs1_data: { side: 'left', offset: 0.25 },
                rs2_data: { side: 'left', offset: 0.5 },
                imm:      { side: 'left', offset: 0.75 },
                pc:       { side: 'top', offset: 0.5 },
                use_pc:   { side: 'bottom', offset: 0.3 },
                alu_src:  { side: 'bottom', offset: 0.7 },
                alu_a:    { side: 'right', offset: 0.35 },
                alu_b:    { side: 'right', offset: 0.65 },
            },
        },
        alu: {
            x: ALU_X, y: ROW_Y - 5, w: 110, h: ROW_H + 10,
            shape: 'rect', label: 'ALU', category: 'execute',
            ports: {
                a:      { side: 'left', offset: 0.3 },
                b:      { side: 'left', offset: 0.6 },
                op:     { side: 'top', offset: 0.5 },
                result: { side: 'right', offset: 0.4 },
                zero:   { side: 'right', offset: 0.7 },
            },
        },
        dmem: {
            x: DMEM_X, y: ROW_Y - 5, w: 100, h: ROW_H + 10,
            shape: 'rect', label: 'Data Memory', category: 'memory',
            ports: {
                addr:  { side: 'left', offset: 0.3 },
                wdata: { side: 'left', offset: 0.6 },
                wen:   { side: 'top', offset: 0.5 },
                rdata: { side: 'right', offset: 0.5 },
            },
        },
        wb: {
            x: WB_X, y: ROW_Y + 5, w: 90, h: ROW_H - 10,
            shape: 'rect', label: 'Writeback', category: 'writeback',
            ports: {
                alu_in:   { side: 'left', offset: 0.25 },
                mem_in:   { side: 'left', offset: 0.5 },
                pc4_in:   { side: 'left', offset: 0.75 },
                sel:      { side: 'top', offset: 0.5 },
                data_out: { side: 'right', offset: 0.5 },
            },
        },

        // -- Branch unit (below main row) -------------------------------- //
        branch: {
            x: 560, y: BRANCH_Y, w: 140, h: 55,
            shape: 'rect', label: 'Branch Resolution', category: 'control',
            ports: {
                pc:           { side: 'left', offset: 0.2 },
                pc4:          { side: 'left', offset: 0.4 },
                imm:          { side: 'left', offset: 0.6 },
                rs1_data:     { side: 'left', offset: 0.8 },
                branch:       { side: 'top', offset: 0.2 },
                branch_cond:  { side: 'top', offset: 0.35 },
                jal:          { side: 'top', offset: 0.5 },
                jalr:         { side: 'top', offset: 0.65 },
                alu_zero:     { side: 'top', offset: 0.8 },
                alu_result:   { side: 'top', offset: 0.9 },
                next_pc:      { side: 'right', offset: 0.35 },
                branch_taken: { side: 'right', offset: 0.65 },
            },
        },

        // -- Flags register (between ALU and Branch, for ARM/x86) --------- //
        flags_reg: {
            x: ALU_X + 20, y: BRANCH_Y - 70, w: 120, h: 40,
            shape: 'rect', label: 'Flags Register', category: 'execute',
            ports: {
                alu_zero_in:   { side: 'top', offset: 0.3 },
                alu_result_in: { side: 'top', offset: 0.7 },
                write_flags:   { side: 'left', offset: 0.5 },
                zero_out:      { side: 'bottom', offset: 0.3 },
                result_out:    { side: 'bottom', offset: 0.7 },
            },
        },

        // -- Branch predictor (bottom) ----------------------------------- //
        bpred: {
            x: 490, y: BPRED_Y, w: 120, h: 50,
            shape: 'rect', label: 'Branch Predictor', category: 'control',
            ports: {
                pc:        { side: 'left', offset: 0.3 },
                is_branch: { side: 'left', offset: 0.6 },
                update_en: { side: 'left', offset: 0.8 },
                actual:    { side: 'right', offset: 0.5 },
            },
        },
    };

    // ------------------------------------------------------------------ //
    //  Wires                                                              //
    // ------------------------------------------------------------------ //
    const wires = [
        // Fetch -> IMem
        { from: 'fetch.pc_out', to: 'imem.addr', path: 'manhattan', style: 'data', label: 'PC' },

        // IMem -> Decode
        { from: 'imem.data', to: 'decode.instr_in', path: 'manhattan', style: 'data', label: 'instr' },

        // Decode -> RegFile (read addresses)
        { from: 'decode.rs1', to: 'regfile.rs1_addr', path: 'manhattan', style: 'data', label: 'rs1' },
        { from: 'decode.rs2', to: 'regfile.rs2_addr', path: 'manhattan', style: 'data', label: 'rs2' },

        // RegFile -> ALU Mux
        { from: 'regfile.rs1_data', to: 'alu_mux.rs1_data', path: 'manhattan', style: 'data' },
        { from: 'regfile.rs2_data', to: 'alu_mux.rs2_data', path: 'manhattan', style: 'data' },

        // Decode -> ALU Mux (immediate)
        {
            from: 'decode.imm', to: 'alu_mux.imm', style: 'data', label: 'imm',
            path: [[DEC_X + 120, ROW_Y + 50], [MUX_A_X, ROW_Y + 50]],
        },

        // ALU Mux -> ALU
        { from: 'alu_mux.alu_a', to: 'alu.a', path: 'manhattan', style: 'data' },
        { from: 'alu_mux.alu_b', to: 'alu.b', path: 'manhattan', style: 'data' },

        // Decode -> ALU (op) control signal
        {
            from: 'decode.alu_op', to: 'alu.op', style: 'control', label: 'alu_op',
            path: [[DEC_X + 120, ROW_Y + 10], [ALU_X + 55, ROW_Y + 10], [ALU_X + 55, ROW_Y - 5]],
        },

        // ALU -> DMem
        { from: 'alu.result', to: 'dmem.addr', path: 'manhattan', style: 'data', label: 'addr' },

        // RegFile -> DMem (write data) -- routed below
        {
            from: 'regfile.rs2_data', to: 'dmem.wdata', style: 'data', label: 'wdata',
            path: [
                [REG_X + 110, ROW_Y + 25],
                [REG_X + 130, ROW_Y + 25],
                [REG_X + 130, ROW_Y + 75],
                [DMEM_X - 10, ROW_Y + 75],
                [DMEM_X - 10, ROW_Y + 35],
                [DMEM_X, ROW_Y + 35],
            ],
        },

        // Decode -> DMem (wen) control
        {
            from: 'decode.mem_write', to: 'dmem.wen', style: 'control', label: 'mem_wr',
            path: [
                [DEC_X + 60, ROW_Y + 70],
                [DEC_X + 60, ROW_Y + 82],
                [DMEM_X + 50, ROW_Y + 82],
                [DMEM_X + 50, ROW_Y - 5],
            ],
        },

        // ALU -> Writeback
        {
            from: 'alu.result', to: 'wb.alu_in', style: 'data',
            path: [
                [ALU_X + 110, ROW_Y + 25],
                [ALU_X + 130, ROW_Y + 25],
                [ALU_X + 130, ROW_Y + 55],
                [WB_X - 10, ROW_Y + 55],
                [WB_X - 10, ROW_Y + 18],
                [WB_X, ROW_Y + 18],
            ],
        },

        // DMem -> Writeback
        { from: 'dmem.rdata', to: 'wb.mem_in', path: 'manhattan', style: 'data' },

        // Fetch PC+4 -> Writeback
        {
            from: 'fetch.pc4_out', to: 'wb.pc4_in', style: 'data', label: 'PC+4',
            path: [
                [PC_X + 100, ROW_Y + 39],
                [PC_X + 140, ROW_Y + 39],
                [PC_X + 140, ROW_Y - 30],
                [WB_X + 45, ROW_Y - 30],
                [WB_X + 45, ROW_Y + 5],
                [WB_X + 22, ROW_Y + 5],
                [WB_X + 22, ROW_Y + 42],
            ],
        },

        // Decode -> Writeback (wb_sel) control
        {
            from: 'decode.wb_sel', to: 'wb.sel', style: 'control', label: 'wb_sel',
            path: [
                [DEC_X + 96, ROW_Y + 70],
                [DEC_X + 96, ROW_Y + 88],
                [WB_X + 45, ROW_Y + 88],
                [WB_X + 45, ROW_Y + 5],
            ],
        },

        // Writeback -> RegFile (write-back path, feedback)
        {
            from: 'wb.data_out', to: 'regfile.rd_data', style: 'data', label: 'WB data',
            path: [
                [WB_X + 90, ROW_Y + 30],
                [WB_X + 110, ROW_Y + 30],
                [WB_X + 110, ROW_Y - 45],
                [REG_X - 15, ROW_Y - 45],
                [REG_X - 15, ROW_Y + 51],
                [REG_X, ROW_Y + 51],
            ],
            _feedbackY: ROW_Y - 45,
        },

        // Decode -> RegFile (rd, reg_write) for write port
        {
            from: 'decode.rd', to: 'regfile.rd_addr', style: 'data', label: 'rd',
            path: [
                [DEC_X + 120, ROW_Y + 25],
                [DEC_X + 135, ROW_Y + 25],
                [DEC_X + 135, ROW_Y + 65],
                [REG_X - 20, ROW_Y + 65],
                [REG_X - 20, ROW_Y + 41],
                [REG_X, ROW_Y + 41],
            ],
        },
        {
            from: 'decode.reg_write', to: 'regfile.wen', style: 'control', label: 'wen',
            path: [
                [DEC_X + 84, ROW_Y + 70],
                [DEC_X + 84, ROW_Y + 78],
                [REG_X + 55, ROW_Y + 78],
                [REG_X + 55, ROW_Y - 15],
            ],
        },

        // -- Branch Resolution wiring ----------------------------------- //
        // Fetch -> Branch
        {
            from: 'fetch.pc_out', to: 'branch.pc', style: 'data',
            path: [
                [PC_X + 100, ROW_Y + 21],
                [PC_X + 120, ROW_Y + 21],
                [PC_X + 120, BRANCH_Y + 11],
                [560, BRANCH_Y + 11],
            ],
        },
        {
            from: 'fetch.pc4_out', to: 'branch.pc4', style: 'data',
            path: [
                [PC_X + 100, ROW_Y + 39],
                [PC_X + 130, ROW_Y + 39],
                [PC_X + 130, BRANCH_Y + 22],
                [560, BRANCH_Y + 22],
            ],
        },
        // Decode -> Branch (imm)
        {
            from: 'decode.imm', to: 'branch.imm', style: 'data',
            path: [
                [DEC_X + 120, ROW_Y + 36],
                [DEC_X + 145, ROW_Y + 36],
                [DEC_X + 145, BRANCH_Y + 33],
                [560, BRANCH_Y + 33],
            ],
        },
        // RegFile -> Branch (rs1_data)
        {
            from: 'regfile.rs1_data', to: 'branch.rs1_data', style: 'data',
            path: [
                [REG_X + 110, ROW_Y + 4],
                [REG_X + 125, ROW_Y + 4],
                [REG_X + 125, BRANCH_Y + 44],
                [560, BRANCH_Y + 44],
            ],
        },
        // Decode -> Branch (control signals)
        {
            from: 'decode.branch', to: 'branch.branch', style: 'control',
            path: [
                [DEC_X + 18, ROW_Y + 70],
                [DEC_X + 18, BRANCH_Y - 15],
                [588, BRANCH_Y - 15],
                [588, BRANCH_Y],
            ],
        },

        // ALU -> Branch (zero, result)
        {
            from: 'alu.zero', to: 'branch.alu_zero', style: 'data',
            path: [
                [ALU_X + 110, ROW_Y + 40],
                [ALU_X + 125, ROW_Y + 40],
                [ALU_X + 125, BRANCH_Y - 8],
                [672, BRANCH_Y - 8],
                [672, BRANCH_Y],
            ],
        },
        {
            from: 'alu.result', to: 'branch.alu_result', style: 'data',
            path: [
                [ALU_X + 110, ROW_Y + 26],
                [ALU_X + 135, ROW_Y + 26],
                [ALU_X + 135, BRANCH_Y - 3],
                [686, BRANCH_Y - 3],
                [686, BRANCH_Y],
            ],
        },

        // ALU -> Flags Register (for ARM/x86)
        {
            from: 'alu.zero', to: 'flags_reg.alu_zero_in', style: 'data',
            path: [
                [ALU_X + 110, ROW_Y + 40],
                [ALU_X + 120, ROW_Y + 40],
                [ALU_X + 120, BRANCH_Y - 82],
                [ALU_X + 56, BRANCH_Y - 82],
                [ALU_X + 56, BRANCH_Y - 70],
            ],
        },
        {
            from: 'alu.result', to: 'flags_reg.alu_result_in', style: 'data',
            path: [
                [ALU_X + 110, ROW_Y + 26],
                [ALU_X + 130, ROW_Y + 26],
                [ALU_X + 130, BRANCH_Y - 86],
                [ALU_X + 104, BRANCH_Y - 86],
                [ALU_X + 104, BRANCH_Y - 70],
            ],
        },
        // Flags Register -> Branch (zero_out, result_out)
        {
            from: 'flags_reg.zero_out', to: 'branch.alu_zero', style: 'data',
            path: [
                [ALU_X + 56, BRANCH_Y - 30],
                [ALU_X + 56, BRANCH_Y - 15],
                [672, BRANCH_Y - 15],
                [672, BRANCH_Y],
            ],
        },

        // Branch -> Fetch (feedback: next_pc, branch_taken)
        {
            from: 'branch.next_pc', to: 'fetch.next_pc', style: 'data', label: 'next_pc',
            path: [
                [700, BRANCH_Y + 19],
                [720, BRANCH_Y + 19],
                [720, BRANCH_Y + 70],
                [PC_X + 30, BRANCH_Y + 70],
                [PC_X + 30, ROW_Y + ROW_H],
            ],
            _feedbackY: BRANCH_Y + 70,
        },
        {
            from: 'branch.branch_taken', to: 'fetch.branch_taken', style: 'control', label: 'taken',
            path: [
                [700, BRANCH_Y + 36],
                [730, BRANCH_Y + 36],
                [730, BRANCH_Y + 80],
                [PC_X + 70, BRANCH_Y + 80],
                [PC_X + 70, ROW_Y + ROW_H],
            ],
            _feedbackY: BRANCH_Y + 80,
        },

        // -- Branch Predictor ------------------------------------------- //
        {
            from: 'fetch.pc_out', to: 'bpred.pc', style: 'control',
            path: [
                [PC_X + 100, ROW_Y + 21],
                [PC_X + 110, ROW_Y + 21],
                [PC_X + 110, BPRED_Y + 15],
                [490, BPRED_Y + 15],
            ],
        },
        {
            from: 'decode.branch', to: 'bpred.is_branch', style: 'control',
            path: [
                [DEC_X + 18, ROW_Y + 70],
                [DEC_X + 18, BPRED_Y + 30],
                [490, BPRED_Y + 30],
            ],
        },
        {
            from: 'branch.branch_taken', to: 'bpred.actual', style: 'control',
            path: [
                [700, BRANCH_Y + 36],
                [740, BRANCH_Y + 36],
                [740, BPRED_Y + 25],
                [610, BPRED_Y + 25],
            ],
        },

        // Decode -> ALU Mux control signals
        {
            from: 'decode.alu_src', to: 'alu_mux.alu_src', style: 'control', label: 'alu_src',
            path: [
                [DEC_X + 36, ROW_Y + 70],
                [DEC_X + 36, ROW_Y + 95],
                [MUX_A_X + 20, ROW_Y + 95],
                [MUX_A_X + 20, ROW_Y + ROW_H - 2],
            ],
        },

        // Fetch PC -> ALU Mux (for AUIPC / JAL)
        {
            from: 'fetch.pc_out', to: 'alu_mux.pc', style: 'data',
            path: [
                [PC_X + 100, ROW_Y + 21],
                [PC_X + 115, ROW_Y + 21],
                [PC_X + 115, ROW_Y - 20],
                [MUX_A_X + 14, ROW_Y - 20],
                [MUX_A_X + 14, ROW_Y + 2],
            ],
        },
    ];

    // ------------------------------------------------------------------ //
    //  Annotations                                                        //
    // ------------------------------------------------------------------ //
    const annotations = [
        // Main datapath label
        {
            type: 'label', x: W / 2, y: 30, text: 'Single-Cycle Datapath',
            color: '#e0e0e6', fontSize: '16px', fontWeight: '700', anchor: 'middle',
        },
    ];

    return {
        width: W,
        height: H,
        components,
        wires,
        annotations,
        stages: [], // no stage columns for single-cycle
    };
}

// Export
window.getSingleCycleLayout = getSingleCycleLayout;
