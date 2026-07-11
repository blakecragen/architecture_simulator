/**
 * RTL CPU Simulator -- Multi-Cycle (FetDecExe) Layout Template
 *
 * Similar to single-cycle but with latch components visible between stages:
 *   PC -> [IMem] -> |IR| -> [Decode] -> [RegFile] -> |A|B| -> <ALU Mux> -> [ALU] -> |ALUOut| -> [DMem] -> <WB Mux> -> [WB]
 *
 *   [MC Controller] below the datapath
 *   [Branch Resolution] + [Branch Predictor] at bottom
 *
 * Layout: ~1340 x 640
 */

/* global window */

function getMulticycleLayout() {
    const W = 1340;
    const H = 640;

    // --- Main datapath row (y baseline) -------------------------------- //
    const ROW_Y  = 120;
    const ROW_H  = 60;

    // --- Component x positions (left-to-right, with latch gaps) -------- //
    const PC_X      = 20;
    const IMEM_X    = 160;
    const IR_X      = 310;
    const DEC_X     = 355;
    const REG_X     = 520;
    const LATCH_AB_X = 660;
    const MUX_A_X   = 720;
    const ALU_X     = 795;
    const ALU_OUT_X = 925;
    const DMEM_X    = 975;
    const MUX_WB_X  = 1120;
    const WB_X      = 1180;

    // --- Latch dimensions ---------------------------------------------- //
    const LATCH_W = 20;
    const LATCH_H = ROW_H - 4;

    // --- Secondary rows ------------------------------------------------ //
    const CTRL_Y    = 300;
    const BRANCH_Y  = 380;
    const BPRED_Y   = 510;
    const PCLATCH_Y = ROW_Y - 55;

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
            x: IMEM_X, y: ROW_Y, w: 110, h: ROW_H,
            shape: 'rect', label: 'Instr Memory', category: 'fetch',
            ports: {
                addr: { side: 'left', offset: 0.5 },
                data: { side: 'right', offset: 0.5 },
            },
        },
        ir: {
            x: IR_X, y: ROW_Y + 2, w: LATCH_W, h: LATCH_H,
            shape: 'rect', label: 'IR', category: 'pipeline',
            ports: {
                data_in:  { side: 'left', offset: 0.5 },
                data_out: { side: 'right', offset: 0.5 },
                enable:   { side: 'top', offset: 0.5 },
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
        reg_a: {
            x: LATCH_AB_X, y: ROW_Y + 2, w: LATCH_W, h: 24,
            shape: 'rect', label: 'A', category: 'pipeline',
            ports: {
                data_in:  { side: 'left', offset: 0.5 },
                data_out: { side: 'right', offset: 0.5 },
                enable:   { side: 'top', offset: 0.5 },
            },
        },
        reg_b: {
            x: LATCH_AB_X, y: ROW_Y + 32, w: LATCH_W, h: 24,
            shape: 'rect', label: 'B', category: 'pipeline',
            ports: {
                data_in:  { side: 'left', offset: 0.5 },
                data_out: { side: 'right', offset: 0.5 },
                enable:   { side: 'top', offset: 0.5 },
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
            x: ALU_X, y: ROW_Y - 5, w: 100, h: ROW_H + 10,
            shape: 'rect', label: 'ALU', category: 'execute',
            ports: {
                a:      { side: 'left', offset: 0.3 },
                b:      { side: 'left', offset: 0.6 },
                op:     { side: 'top', offset: 0.5 },
                result: { side: 'right', offset: 0.4 },
                zero:   { side: 'right', offset: 0.7 },
            },
        },
        alu_out: {
            x: ALU_OUT_X, y: ROW_Y + 2, w: LATCH_W, h: LATCH_H,
            shape: 'rect', label: 'AO', category: 'pipeline',
            ports: {
                data_in:  { side: 'left', offset: 0.5 },
                data_out: { side: 'right', offset: 0.5 },
                enable:   { side: 'top', offset: 0.5 },
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

        // -- PC Latch (above fetch) --------------------------------------- //
        pc_latch: {
            x: PC_X + 20, y: PCLATCH_Y, w: 60, h: 30,
            shape: 'rect', label: 'PC Latch', category: 'fetch',
            ports: {
                data_in:  { side: 'left', offset: 0.5 },
                data_out: { side: 'right', offset: 0.5 },
                enable:   { side: 'top', offset: 0.5 },
            },
        },

        // -- MC Controller (below main row) ------------------------------- //
        mc_ctrl: {
            x: 350, y: CTRL_Y, w: 180, h: 50,
            shape: 'rect', label: 'MC Controller (FSM)', category: 'control',
            ports: {
                dec_mem_read:  { side: 'top', offset: 0.2 },
                dec_mem_write: { side: 'top', offset: 0.4 },
                dec_reg_write: { side: 'top', offset: 0.6 },
                phase:         { side: 'right', offset: 0.3 },
                fetch_stall:   { side: 'left', offset: 0.3 },
                ir_latch:      { side: 'right', offset: 0.5 },
                ab_latch:      { side: 'right', offset: 0.7 },
                reg_write_en:  { side: 'bottom', offset: 0.3 },
                mem_write_en:  { side: 'bottom', offset: 0.5 },
                alu_out_latch: { side: 'bottom', offset: 0.7 },
            },
        },

        // -- Gate components ---------------------------------------------- //
        gate_reg_wen: {
            x: REG_X + 30, y: ROW_Y - 40, w: 40, h: 20,
            shape: 'rect', label: 'AND', category: 'control',
            ports: {
                a:   { side: 'left', offset: 0.3 },
                b:   { side: 'left', offset: 0.7 },
                out: { side: 'right', offset: 0.5 },
            },
        },
        gate_mem_wen: {
            x: DMEM_X + 20, y: ROW_Y - 40, w: 40, h: 20,
            shape: 'rect', label: 'AND', category: 'control',
            ports: {
                a:   { side: 'left', offset: 0.3 },
                b:   { side: 'left', offset: 0.7 },
                out: { side: 'right', offset: 0.5 },
            },
        },

        // -- Branch unit (below controller) ------------------------------- //
        branch: {
            x: 580, y: BRANCH_Y, w: 140, h: 55,
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

        // -- Flags register (for ARM/x86) --------------------------------- //
        flags_reg: {
            x: ALU_X + 20, y: CTRL_Y, w: 120, h: 40,
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
            x: 510, y: BPRED_Y, w: 120, h: 50,
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

        // IMem -> IR
        { from: 'imem.data', to: 'ir.data_in', path: 'manhattan', style: 'data', label: 'instr' },

        // IR -> Decode
        { from: 'ir.data_out', to: 'decode.instr_in', path: 'manhattan', style: 'data' },

        // Decode -> RegFile (read addresses)
        { from: 'decode.rs1', to: 'regfile.rs1_addr', path: 'manhattan', style: 'data', label: 'rs1' },
        { from: 'decode.rs2', to: 'regfile.rs2_addr', path: 'manhattan', style: 'data', label: 'rs2' },

        // RegFile -> A/B latches
        { from: 'regfile.rs1_data', to: 'reg_a.data_in', path: 'manhattan', style: 'data' },
        { from: 'regfile.rs2_data', to: 'reg_b.data_in', path: 'manhattan', style: 'data' },

        // A/B latches -> ALU Mux
        { from: 'reg_a.data_out', to: 'alu_mux.rs1_data', path: 'manhattan', style: 'data' },
        { from: 'reg_b.data_out', to: 'alu_mux.rs2_data', path: 'manhattan', style: 'data' },

        // Decode -> ALU Mux (immediate)
        {
            from: 'decode.imm', to: 'alu_mux.imm', style: 'data', label: 'imm',
            path: [[DEC_X + 120, ROW_Y + 36], [DEC_X + 145, ROW_Y + 36], [DEC_X + 145, ROW_Y + 50], [MUX_A_X, ROW_Y + 50]],
        },

        // ALU Mux -> ALU
        { from: 'alu_mux.alu_a', to: 'alu.a', path: 'manhattan', style: 'data' },
        { from: 'alu_mux.alu_b', to: 'alu.b', path: 'manhattan', style: 'data' },

        // Decode -> ALU (op)
        {
            from: 'decode.alu_op', to: 'alu.op', style: 'control', label: 'alu_op',
            path: [[DEC_X + 120, ROW_Y + 10], [ALU_X + 50, ROW_Y + 10], [ALU_X + 50, ROW_Y - 5]],
        },

        // ALU -> ALU out latch
        { from: 'alu.result', to: 'alu_out.data_in', path: 'manhattan', style: 'data' },

        // ALU out latch -> DMem
        { from: 'alu_out.data_out', to: 'dmem.addr', path: 'manhattan', style: 'data', label: 'addr' },

        // B latch -> DMem (write data)
        {
            from: 'reg_b.data_out', to: 'dmem.wdata', style: 'data', label: 'wdata',
            path: [
                [LATCH_AB_X + LATCH_W, ROW_Y + 44],
                [LATCH_AB_X + LATCH_W + 10, ROW_Y + 44],
                [LATCH_AB_X + LATCH_W + 10, ROW_Y + 78],
                [DMEM_X - 10, ROW_Y + 78],
                [DMEM_X - 10, ROW_Y + 35],
                [DMEM_X, ROW_Y + 35],
            ],
        },

        // Gate -> DMem (wen)
        {
            from: 'gate_mem_wen.out', to: 'dmem.wen', style: 'control', label: 'wen',
            path: [
                [DMEM_X + 60 + 40, ROW_Y - 40 + 10],
                [DMEM_X + 50, ROW_Y - 40 + 10],
                [DMEM_X + 50, ROW_Y - 5],
            ],
        },

        // ALU -> Writeback
        {
            from: 'alu.result', to: 'wb.alu_in', style: 'data',
            path: [
                [ALU_X + 100, ROW_Y + 25],
                [ALU_X + 110, ROW_Y + 25],
                [ALU_X + 110, ROW_Y + 55],
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

        // Decode -> Writeback (wb_sel)
        {
            from: 'decode.wb_sel', to: 'wb.sel', style: 'control', label: 'wb_sel',
            path: [
                [DEC_X + 96, ROW_Y + 70],
                [DEC_X + 96, ROW_Y + 92],
                [WB_X + 45, ROW_Y + 92],
                [WB_X + 45, ROW_Y + 5],
            ],
        },

        // Writeback -> RegFile (write-back path, feedback)
        {
            from: 'wb.data_out', to: 'regfile.rd_data', style: 'data', label: 'WB data',
            path: [
                [WB_X + 90, ROW_Y + 30],
                [WB_X + 110, ROW_Y + 30],
                [WB_X + 110, ROW_Y - 50],
                [REG_X - 15, ROW_Y - 50],
                [REG_X - 15, ROW_Y + 51],
                [REG_X, ROW_Y + 51],
            ],
        },

        // Decode -> RegFile (rd, for write port)
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

        // Gate -> RegFile (wen)
        {
            from: 'gate_reg_wen.out', to: 'regfile.wen', style: 'control', label: 'wen',
            path: [
                [REG_X + 30 + 40, ROW_Y - 40 + 10],
                [REG_X + 55, ROW_Y - 40 + 10],
                [REG_X + 55, ROW_Y - 15],
            ],
        },

        // MC Controller -> Fetch (stall)
        {
            from: 'mc_ctrl.fetch_stall', to: 'fetch.stall', style: 'control', label: 'stall',
            path: [
                [350, CTRL_Y + 15],
                [PC_X + 50, CTRL_Y + 15],
                [PC_X + 50, ROW_Y],
            ],
        },

        // -- Branch Resolution wiring ----------------------------------- //
        {
            from: 'fetch.pc_out', to: 'branch.pc', style: 'data',
            path: [
                [PC_X + 100, ROW_Y + 21],
                [PC_X + 120, ROW_Y + 21],
                [PC_X + 120, BRANCH_Y + 11],
                [580, BRANCH_Y + 11],
            ],
        },
        {
            from: 'fetch.pc4_out', to: 'branch.pc4', style: 'data',
            path: [
                [PC_X + 100, ROW_Y + 39],
                [PC_X + 130, ROW_Y + 39],
                [PC_X + 130, BRANCH_Y + 22],
                [580, BRANCH_Y + 22],
            ],
        },
        {
            from: 'decode.imm', to: 'branch.imm', style: 'data',
            path: [
                [DEC_X + 120, ROW_Y + 36],
                [DEC_X + 150, ROW_Y + 36],
                [DEC_X + 150, BRANCH_Y + 33],
                [580, BRANCH_Y + 33],
            ],
        },
        {
            from: 'decode.branch', to: 'branch.branch', style: 'control',
            path: [
                [DEC_X + 18, ROW_Y + 70],
                [DEC_X + 18, BRANCH_Y - 10],
                [608, BRANCH_Y - 10],
                [608, BRANCH_Y],
            ],
        },
        {
            from: 'alu.zero', to: 'branch.alu_zero', style: 'data',
            path: [
                [ALU_X + 100, ROW_Y + 40],
                [ALU_X + 115, ROW_Y + 40],
                [ALU_X + 115, BRANCH_Y - 5],
                [692, BRANCH_Y - 5],
                [692, BRANCH_Y],
            ],
        },
        {
            from: 'alu.result', to: 'branch.alu_result', style: 'data',
            path: [
                [ALU_X + 100, ROW_Y + 26],
                [ALU_X + 125, ROW_Y + 26],
                [ALU_X + 125, BRANCH_Y - 1],
                [706, BRANCH_Y - 1],
                [706, BRANCH_Y],
            ],
        },

        // Branch -> Fetch (feedback: next_pc, branch_taken)
        {
            from: 'branch.next_pc', to: 'fetch.next_pc', style: 'data', label: 'next_pc',
            path: [
                [720, BRANCH_Y + 19],
                [740, BRANCH_Y + 19],
                [740, BRANCH_Y + 65],
                [PC_X + 30, BRANCH_Y + 65],
                [PC_X + 30, ROW_Y + ROW_H],
            ],
        },
        {
            from: 'branch.branch_taken', to: 'fetch.branch_taken', style: 'control', label: 'taken',
            path: [
                [720, BRANCH_Y + 36],
                [750, BRANCH_Y + 36],
                [750, BRANCH_Y + 75],
                [PC_X + 70, BRANCH_Y + 75],
                [PC_X + 70, ROW_Y + ROW_H],
            ],
        },

        // -- Branch Predictor ------------------------------------------- //
        {
            from: 'fetch.pc_out', to: 'bpred.pc', style: 'control',
            path: [
                [PC_X + 100, ROW_Y + 21],
                [PC_X + 110, ROW_Y + 21],
                [PC_X + 110, BPRED_Y + 15],
                [510, BPRED_Y + 15],
            ],
        },
        {
            from: 'decode.branch', to: 'bpred.is_branch', style: 'control',
            path: [
                [DEC_X + 18, ROW_Y + 70],
                [DEC_X + 18, BPRED_Y + 30],
                [510, BPRED_Y + 30],
            ],
        },
        {
            from: 'branch.branch_taken', to: 'bpred.actual', style: 'control',
            path: [
                [720, BRANCH_Y + 36],
                [760, BRANCH_Y + 36],
                [760, BPRED_Y + 25],
                [630, BPRED_Y + 25],
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

        // PC Latch -> ALU Mux (for AUIPC / JAL)
        {
            from: 'pc_latch.data_out', to: 'alu_mux.pc', style: 'data',
            path: [
                [PC_X + 80, PCLATCH_Y + 15],
                [MUX_A_X + 14, PCLATCH_Y + 15],
                [MUX_A_X + 14, ROW_Y + 2],
            ],
        },

        // Fetch PC -> PC Latch
        {
            from: 'fetch.pc_out', to: 'pc_latch.data_in', style: 'data',
            path: [
                [PC_X + 100, ROW_Y + 21],
                [PC_X + 110, ROW_Y + 21],
                [PC_X + 110, PCLATCH_Y + 15],
                [PC_X + 20, PCLATCH_Y + 15],
            ],
        },

        // Flags Register (ARM/x86) wires
        {
            from: 'alu.zero', to: 'flags_reg.alu_zero_in', style: 'data',
            path: [
                [ALU_X + 100, ROW_Y + 40],
                [ALU_X + 112, ROW_Y + 40],
                [ALU_X + 112, CTRL_Y - 10],
                [ALU_X + 56, CTRL_Y - 10],
                [ALU_X + 56, CTRL_Y],
            ],
        },
        {
            from: 'alu.result', to: 'flags_reg.alu_result_in', style: 'data',
            path: [
                [ALU_X + 100, ROW_Y + 26],
                [ALU_X + 120, ROW_Y + 26],
                [ALU_X + 120, CTRL_Y - 15],
                [ALU_X + 104, CTRL_Y - 15],
                [ALU_X + 104, CTRL_Y],
            ],
        },
        {
            from: 'flags_reg.zero_out', to: 'branch.alu_zero', style: 'data',
            path: [
                [ALU_X + 56, CTRL_Y + 40],
                [ALU_X + 56, BRANCH_Y - 5],
                [692, BRANCH_Y - 5],
                [692, BRANCH_Y],
            ],
        },
    ];

    // ------------------------------------------------------------------ //
    //  Annotations                                                        //
    // ------------------------------------------------------------------ //
    const annotations = [
        {
            type: 'label', x: W / 2, y: 30, text: 'Multi-Cycle (FetDecExe) Datapath',
            color: '#e0e0e6', fontSize: '16px', fontWeight: '700', anchor: 'middle',
        },
        {
            type: 'dashed_box',
            x: 340, y: CTRL_Y - 10, w: 200, h: 70,
            text: 'FSM Controller', color: '#f43f5e',
        },
        {
            type: 'dashed_box',
            x: 570, y: BRANCH_Y - 15, w: 160, h: 80,
            text: 'Branch Resolution', color: '#f43f5e',
        },
        {
            type: 'label', x: 380, y: BRANCH_Y + 83, text: 'PC feedback',
            color: '#8b8fa3', fontSize: '9px',
        },
        // Latch labels
        {
            type: 'label', x: IR_X + LATCH_W / 2, y: ROW_Y - 8, text: 'IR',
            color: '#60a5fa', fontSize: '9px', anchor: 'middle',
        },
        {
            type: 'label', x: ALU_OUT_X + LATCH_W / 2, y: ROW_Y - 8, text: 'ALU Out',
            color: '#60a5fa', fontSize: '9px', anchor: 'middle',
        },
    ];

    return {
        width: W,
        height: H,
        components,
        wires,
        annotations,
        stages: [],
    };
}

// Export
window.getMulticycleLayout = getMulticycleLayout;
