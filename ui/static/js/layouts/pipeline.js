/**
 * RTL CPU Simulator -- 5-Stage Pipeline Layout Template
 *
 * 5-stage pipeline with column layout:
 *
 *  [IF]    |IF/ID|  [ID]     |ID/EX|  [EX]     |EX/MEM|  [MEM]    |MEM/WB|  [WB]
 *  Fetch   |    |  Decode   |    |  ALU      |     |  DMem    |     |  WB Mux
 *  IMem    |    |  RegFile  |    |  ALU Mux  |     |  Branch  |     |
 *                                   Fwd
 *
 *  [Hazard Detector] spans below ID-EX
 *  [Branch Predictor] at bottom
 *
 * Layout: ~1400 x 620
 */

/* global window */

function getPipelineLayout() {
    const W = 1400;
    const H = 680;

    // -- Stage geometry ------------------------------------------------- //
    const STAGE_W     = 200;
    const GAP         = 52;    // gap between stages (pipeline bar sits here)
    const BAR_W       = 12;
    const MARGIN_L    = 30;
    const HEADER_Y    = 44;    // top of component area

    // x-start of each stage column
    const stageX = (i) => MARGIN_L + i * (STAGE_W + GAP);
    // x-center of pipeline bar between stage i and i+1
    const barX   = (i) => stageX(i) + STAGE_W + (GAP - BAR_W) / 2;

    // -- Vertical positions inside a stage column ----------------------- //
    const COMP_Y1   = HEADER_Y + 10;   // first component row
    const COMP_Y2   = COMP_Y1 + 90;    // second component row (was +80)
    const COMP_Y3   = COMP_Y2 + 90;    // third row (was +80)
    const HAZARD_Y  = 460;
    const BPRED_Y   = 560;
    const BRANCH_Y  = COMP_Y2 + 10;    // branch in MEM stage
    const BAR_H     = 220;

    // -- Stage colours -------------------------------------------------- //
    const stageDefs = [
        { id: 'IF',  label: 'IF',  color: '#3b82f6' },
        { id: 'ID',  label: 'ID',  color: '#14b8a6' },
        { id: 'EX',  label: 'EX',  color: '#a78bfa' },
        { id: 'MEM', label: 'MEM', color: '#f59e0b' },
        { id: 'WB',  label: 'WB',  color: '#22c55e' },
    ];

    const stages = stageDefs.map((s, i) => ({
        id: s.id,
        label: s.label,
        x: stageX(i),
        w: STAGE_W,
        color: s.color,
    }));

    // ================================================================== //
    //  Components                                                         //
    // ================================================================== //
    const components = {};

    // -- IF stage ------------------------------------------------------- //
    components.fetch = {
        x: stageX(0) + 20, y: COMP_Y1, w: 160, h: 55,
        shape: 'rect', label: 'Fetch / PC', category: 'fetch',
        ports: {
            pc_out:       { side: 'right', offset: 0.35 },
            pc4_out:      { side: 'right', offset: 0.65 },
            next_pc:      { side: 'left', offset: 0.65 },
            branch_taken: { side: 'left', offset: 0.35 },
            stall:        { side: 'top', offset: 0.5 },
        },
    };
    components.imem = {
        x: stageX(0) + 20, y: COMP_Y2, w: 160, h: 55,
        shape: 'rect', label: 'Instr Memory', category: 'fetch',
        ports: {
            addr: { side: 'left', offset: 0.5 },
            data: { side: 'right', offset: 0.5 },
        },
    };

    // -- IF/ID pipeline register ---------------------------------------- //
    components.if_id = {
        x: barX(0), y: COMP_Y1, w: BAR_W, h: BAR_H,
        shape: 'pipeline_bar', label: 'IF/ID', category: 'pipeline',
        ports: {
            pc_in:     { side: 'left', offset: 0.2 },
            pc4_in:    { side: 'left', offset: 0.35 },
            instr_in:  { side: 'left', offset: 0.5 },
            stall:     { side: 'top', offset: 0.5 },
            flush:     { side: 'bottom', offset: 0.5 },
            pc_out:    { side: 'right', offset: 0.2 },
            pc4_out:   { side: 'right', offset: 0.35 },
            instr_out: { side: 'right', offset: 0.5 },
        },
    };

    // -- ID stage ------------------------------------------------------- //
    components.decode = {
        x: stageX(1) + 20, y: COMP_Y1, w: 160, h: 60,
        shape: 'rect', label: 'Decoder', category: 'decode',
        ports: {
            instr_in:    { side: 'left', offset: 0.5 },
            rs1:         { side: 'right', offset: 0.2 },
            rs2:         { side: 'right', offset: 0.4 },
            rd:          { side: 'right', offset: 0.55 },
            imm:         { side: 'right', offset: 0.7 },
            alu_op:      { side: 'right', offset: 0.85 },
            alu_src:     { side: 'bottom', offset: 0.2 },
            use_pc:      { side: 'bottom', offset: 0.35 },
            mem_read:    { side: 'bottom', offset: 0.5 },
            mem_write:   { side: 'bottom', offset: 0.6 },
            reg_write:   { side: 'bottom', offset: 0.7 },
            branch:      { side: 'bottom', offset: 0.8 },
            branch_cond: { side: 'bottom', offset: 0.85 },
            jal:         { side: 'bottom', offset: 0.9 },
            jalr:        { side: 'bottom', offset: 0.95 },
            wb_sel:      { side: 'bottom', offset: 0.1 },
        },
    };
    components.regfile = {
        x: stageX(1) + 20, y: COMP_Y2, w: 160, h: 70,
        shape: 'rect', label: 'Register File', category: 'decode',
        ports: {
            rs1_addr: { side: 'left', offset: 0.2 },
            rs2_addr: { side: 'left', offset: 0.4 },
            rs1_data: { side: 'right', offset: 0.2 },
            rs2_data: { side: 'right', offset: 0.4 },
            rd_addr:  { side: 'left', offset: 0.7 },
            rd_data:  { side: 'left', offset: 0.85 },
            wen:      { side: 'top', offset: 0.8 },
        },
    };

    // -- ID/EX pipeline register ---------------------------------------- //
    components.id_ex = {
        x: barX(1), y: COMP_Y1, w: BAR_W, h: BAR_H,
        shape: 'pipeline_bar', label: 'ID/EX', category: 'pipeline',
        ports: {
            // Inputs (left)
            pc_in:          { side: 'left', offset: 0.08 },
            pc4_in:         { side: 'left', offset: 0.15 },
            rs1_data_in:    { side: 'left', offset: 0.22 },
            rs2_data_in:    { side: 'left', offset: 0.29 },
            imm_in:         { side: 'left', offset: 0.36 },
            rs1_addr_in:    { side: 'left', offset: 0.43 },
            rs2_addr_in:    { side: 'left', offset: 0.50 },
            rd_in:          { side: 'left', offset: 0.57 },
            alu_op_in:      { side: 'left', offset: 0.64 },
            alu_src_in:     { side: 'left', offset: 0.71 },
            use_pc_in:      { side: 'left', offset: 0.78 },
            mem_read_in:    { side: 'left', offset: 0.82 },
            mem_write_in:   { side: 'left', offset: 0.85 },
            reg_write_in:   { side: 'left', offset: 0.88 },
            branch_in:      { side: 'left', offset: 0.91 },
            branch_cond_in: { side: 'left', offset: 0.93 },
            jal_in:         { side: 'left', offset: 0.95 },
            jalr_in:        { side: 'left', offset: 0.97 },
            wb_sel_in:      { side: 'left', offset: 0.99 },
            stall:          { side: 'top', offset: 0.5 },
            flush:          { side: 'bottom', offset: 0.5 },
            // Outputs (right) -- matching offsets
            pc_out:          { side: 'right', offset: 0.08 },
            pc4_out:         { side: 'right', offset: 0.15 },
            rs1_data_out:    { side: 'right', offset: 0.22 },
            rs2_data_out:    { side: 'right', offset: 0.29 },
            imm_out:         { side: 'right', offset: 0.36 },
            rs1_addr_out:    { side: 'right', offset: 0.43 },
            rs2_addr_out:    { side: 'right', offset: 0.50 },
            rd_out:          { side: 'right', offset: 0.57 },
            alu_op_out:      { side: 'right', offset: 0.64 },
            alu_src_out:     { side: 'right', offset: 0.71 },
            use_pc_out:      { side: 'right', offset: 0.78 },
            mem_read_out:    { side: 'right', offset: 0.82 },
            mem_write_out:   { side: 'right', offset: 0.85 },
            reg_write_out:   { side: 'right', offset: 0.88 },
            branch_out:      { side: 'right', offset: 0.91 },
            branch_cond_out: { side: 'right', offset: 0.93 },
            jal_out:         { side: 'right', offset: 0.95 },
            jalr_out:        { side: 'right', offset: 0.97 },
            wb_sel_out:      { side: 'right', offset: 0.99 },
        },
    };

    // -- EX stage ------------------------------------------------------- //
    components.forwarding = {
        x: stageX(2) + 20, y: COMP_Y1, w: 160, h: 50,
        shape: 'rect', label: 'Forwarding Unit', category: 'execute',
        ports: {
            id_ex_rs1:        { side: 'left', offset: 0.2 },
            id_ex_rs2:        { side: 'left', offset: 0.4 },
            ex_mem_rd:        { side: 'bottom', offset: 0.2 },
            ex_mem_reg_write: { side: 'bottom', offset: 0.35 },
            ex_mem_alu_result:{ side: 'bottom', offset: 0.5 },
            mem_wb_rd:        { side: 'bottom', offset: 0.65 },
            mem_wb_reg_write: { side: 'bottom', offset: 0.8 },
            mem_wb_data:      { side: 'bottom', offset: 0.95 },
            rs1_data_in:      { side: 'left', offset: 0.7 },
            rs2_data_in:      { side: 'left', offset: 0.9 },
            rs1_data_out:     { side: 'right', offset: 0.3 },
            rs2_data_out:     { side: 'right', offset: 0.7 },
        },
    };
    components.alu_mux = {
        x: stageX(2) + 75, y: COMP_Y2, w: 30, h: 50,
        shape: 'mux', label: 'M', category: 'execute', direction: 'right',
        ports: {
            rs1_data: { side: 'left', offset: 0.25 },
            rs2_data: { side: 'left', offset: 0.55 },
            imm:      { side: 'left', offset: 0.8 },
            pc:       { side: 'top', offset: 0.5 },
            use_pc:   { side: 'bottom', offset: 0.3 },
            alu_src:  { side: 'bottom', offset: 0.7 },
            alu_a:    { side: 'right', offset: 0.3 },
            alu_b:    { side: 'right', offset: 0.7 },
        },
    };
    components.alu = {
        x: stageX(2) + 20, y: COMP_Y3, w: 160, h: 55,
        shape: 'rect', label: 'ALU', category: 'execute',
        ports: {
            a:      { side: 'left', offset: 0.3 },
            b:      { side: 'left', offset: 0.7 },
            op:     { side: 'top', offset: 0.5 },
            result: { side: 'right', offset: 0.35 },
            zero:   { side: 'right', offset: 0.7 },
        },
    };

    // -- Flags Register (in EX stage, for ARM/x86) ---------------------- //
    components.flags_reg = {
        x: stageX(2) + 20, y: COMP_Y3 + 65, w: 130, h: 38,
        shape: 'rect', label: 'Flags Register', category: 'execute',
        ports: {
            alu_zero_in:   { side: 'top', offset: 0.3 },
            alu_result_in: { side: 'top', offset: 0.7 },
            write_flags:   { side: 'left', offset: 0.5 },
            zero_out:      { side: 'right', offset: 0.3 },
            result_out:    { side: 'right', offset: 0.7 },
        },
    };

    // -- EX/MEM pipeline register --------------------------------------- //
    components.ex_mem = {
        x: barX(2), y: COMP_Y1, w: BAR_W, h: BAR_H,
        shape: 'pipeline_bar', label: 'EX/MEM', category: 'pipeline',
        ports: {
            alu_result_in:  { side: 'left', offset: 0.15 },
            alu_zero_in:    { side: 'left', offset: 0.25 },
            rs2_data_in:    { side: 'left', offset: 0.35 },
            rd_in:          { side: 'left', offset: 0.45 },
            pc_in:          { side: 'left', offset: 0.55 },
            pc4_in:         { side: 'left', offset: 0.62 },
            imm_in:         { side: 'left', offset: 0.68 },
            rs1_data_in:    { side: 'left', offset: 0.74 },
            mem_read_in:    { side: 'left', offset: 0.80 },
            mem_write_in:   { side: 'left', offset: 0.84 },
            reg_write_in:   { side: 'left', offset: 0.88 },
            branch_in:      { side: 'left', offset: 0.91 },
            branch_cond_in: { side: 'left', offset: 0.93 },
            jal_in:         { side: 'left', offset: 0.95 },
            jalr_in:        { side: 'left', offset: 0.97 },
            wb_sel_in:      { side: 'left', offset: 0.99 },
            flush:          { side: 'bottom', offset: 0.5 },
            // Outputs
            alu_result_out:  { side: 'right', offset: 0.15 },
            alu_zero_out:    { side: 'right', offset: 0.25 },
            rs2_data_out:    { side: 'right', offset: 0.35 },
            rd_out:          { side: 'right', offset: 0.45 },
            pc_out:          { side: 'right', offset: 0.55 },
            pc4_out:         { side: 'right', offset: 0.62 },
            imm_out:         { side: 'right', offset: 0.68 },
            rs1_data_out:    { side: 'right', offset: 0.74 },
            mem_read_out:    { side: 'right', offset: 0.80 },
            mem_write_out:   { side: 'right', offset: 0.84 },
            reg_write_out:   { side: 'right', offset: 0.88 },
            branch_out:      { side: 'right', offset: 0.91 },
            branch_cond_out: { side: 'right', offset: 0.93 },
            jal_out:         { side: 'right', offset: 0.95 },
            jalr_out:        { side: 'right', offset: 0.97 },
            wb_sel_out:      { side: 'right', offset: 0.99 },
        },
    };

    // -- MEM stage ------------------------------------------------------ //
    components.dmem = {
        x: stageX(3) + 20, y: COMP_Y1, w: 160, h: 60,
        shape: 'rect', label: 'Data Memory', category: 'memory',
        ports: {
            addr:  { side: 'left', offset: 0.3 },
            wdata: { side: 'left', offset: 0.6 },
            wen:   { side: 'top', offset: 0.5 },
            rdata: { side: 'right', offset: 0.5 },
        },
    };
    components.branch = {
        x: stageX(3) + 20, y: BRANCH_Y, w: 160, h: 55,
        shape: 'rect', label: 'Branch Resolution', category: 'control',
        ports: {
            pc:           { side: 'left', offset: 0.15 },
            pc4:          { side: 'left', offset: 0.30 },
            imm:          { side: 'left', offset: 0.45 },
            rs1_data:     { side: 'left', offset: 0.60 },
            branch:       { side: 'left', offset: 0.75 },
            branch_cond:  { side: 'left', offset: 0.82 },
            jal:          { side: 'left', offset: 0.88 },
            jalr:         { side: 'left', offset: 0.95 },
            alu_zero:     { side: 'top', offset: 0.6 },
            alu_result:   { side: 'top', offset: 0.8 },
            next_pc:      { side: 'right', offset: 0.35 },
            branch_taken: { side: 'right', offset: 0.65 },
        },
    };

    // -- MEM/WB pipeline register --------------------------------------- //
    components.mem_wb = {
        x: barX(3), y: COMP_Y1, w: BAR_W, h: BAR_H,
        shape: 'pipeline_bar', label: 'MEM/WB', category: 'pipeline',
        ports: {
            alu_result_in: { side: 'left', offset: 0.2 },
            mem_data_in:   { side: 'left', offset: 0.35 },
            rd_in:         { side: 'left', offset: 0.5 },
            pc4_in:        { side: 'left', offset: 0.65 },
            reg_write_in:  { side: 'left', offset: 0.8 },
            wb_sel_in:     { side: 'left', offset: 0.9 },
            alu_result_out: { side: 'right', offset: 0.2 },
            mem_data_out:   { side: 'right', offset: 0.35 },
            rd_out:         { side: 'right', offset: 0.5 },
            pc4_out:        { side: 'right', offset: 0.65 },
            reg_write_out:  { side: 'right', offset: 0.8 },
            wb_sel_out:     { side: 'right', offset: 0.9 },
        },
    };

    // -- WB stage ------------------------------------------------------- //
    components.wb = {
        x: stageX(4) + 30, y: COMP_Y1, w: 140, h: 55,
        shape: 'rect', label: 'Writeback', category: 'writeback',
        ports: {
            alu_in:   { side: 'left', offset: 0.25 },
            mem_in:   { side: 'left', offset: 0.5 },
            pc4_in:   { side: 'left', offset: 0.75 },
            sel:      { side: 'top', offset: 0.5 },
            data_out: { side: 'right', offset: 0.5 },
        },
    };

    // -- Hazard Detector (spanning below ID-EX) ------------------------- //
    components.hazard_det = {
        x: stageX(1), y: HAZARD_Y, w: STAGE_W + GAP + STAGE_W, h: 45,
        shape: 'rect', label: 'Hazard Detector', category: 'control',
        ports: {
            id_ex_mem_read: { side: 'right', offset: 0.25 },
            id_ex_rd:       { side: 'right', offset: 0.5 },
            if_id_rs1:      { side: 'left', offset: 0.35 },
            if_id_rs2:      { side: 'left', offset: 0.65 },
            stall:          { side: 'top', offset: 0.5 },
        },
    };

    // -- Branch Predictor (bottom) -------------------------------------- //
    components.bpred = {
        x: stageX(1) + 20, y: BPRED_Y, w: 160, h: 45,
        shape: 'rect', label: 'Branch Predictor', category: 'control',
        ports: {
            pc:        { side: 'left', offset: 0.3 },
            is_branch: { side: 'left', offset: 0.6 },
            update_en: { side: 'left', offset: 0.8 },
            actual:    { side: 'right', offset: 0.5 },
        },
    };

    // ================================================================== //
    //  Wires -- Key datapath connections                                   //
    // ================================================================== //
    const S = (i) => stageX(i);
    const B = (i) => barX(i);

    const wires = [
        // -- IF stage -- //
        { from: 'fetch.pc_out', to: 'imem.addr', path: [
            [S(0) + 180, COMP_Y1 + 19],
            [S(0) + 195, COMP_Y1 + 19],
            [S(0) + 195, COMP_Y2 + 27],
            [S(0) + 20, COMP_Y2 + 27],
        ], style: 'data', label: 'PC' },

        // IF -> IF/ID
        { from: 'fetch.pc_out', to: 'if_id.pc_in', path: 'manhattan', style: 'data' },
        { from: 'fetch.pc4_out', to: 'if_id.pc4_in', path: 'manhattan', style: 'data' },
        { from: 'imem.data', to: 'if_id.instr_in', path: 'manhattan', style: 'data', label: 'instr' },

        // IF/ID -> ID stage
        { from: 'if_id.instr_out', to: 'decode.instr_in', path: 'manhattan', style: 'data' },

        // Decoder -> RegFile
        { from: 'decode.rs1', to: 'regfile.rs1_addr', path: [
            [S(1) + 180, COMP_Y1 + 12],
            [S(1) + 195, COMP_Y1 + 12],
            [S(1) + 195, COMP_Y2 + 14],
            [S(1) + 20, COMP_Y2 + 14],
        ], style: 'data', label: 'rs1' },
        { from: 'decode.rs2', to: 'regfile.rs2_addr', path: [
            [S(1) + 180, COMP_Y1 + 24],
            [S(1) + 200, COMP_Y1 + 24],
            [S(1) + 200, COMP_Y2 + 28],
            [S(1) + 20, COMP_Y2 + 28],
        ], style: 'data', label: 'rs2' },

        // RegFile -> ID/EX (rs1_data, rs2_data)
        { from: 'regfile.rs1_data', to: 'id_ex.rs1_data_in', path: 'manhattan', style: 'data' },
        { from: 'regfile.rs2_data', to: 'id_ex.rs2_data_in', path: 'manhattan', style: 'data' },

        // IF/ID -> ID/EX (pass-through signals)
        { from: 'if_id.pc_out', to: 'id_ex.pc_in', path: [
            [B(0) + BAR_W, COMP_Y1 + BAR_H * 0.2],
            [B(0) + BAR_W + 8, COMP_Y1 + BAR_H * 0.2],
            [B(0) + BAR_W + 8, COMP_Y1 - 8],
            [B(1) - 8, COMP_Y1 - 8],
            [B(1) - 8, COMP_Y1 + BAR_H * 0.08],
            [B(1), COMP_Y1 + BAR_H * 0.08],
        ], style: 'data' },
        { from: 'if_id.pc4_out', to: 'id_ex.pc4_in', path: [
            [B(0) + BAR_W, COMP_Y1 + BAR_H * 0.35],
            [B(0) + BAR_W + 12, COMP_Y1 + BAR_H * 0.35],
            [B(0) + BAR_W + 12, COMP_Y1 - 14],
            [B(1) - 12, COMP_Y1 - 14],
            [B(1) - 12, COMP_Y1 + BAR_H * 0.15],
            [B(1), COMP_Y1 + BAR_H * 0.15],
        ], style: 'data' },

        // Decoder control -> ID/EX (representative subset)
        { from: 'decode.alu_op', to: 'id_ex.alu_op_in', path: 'manhattan', style: 'control' },
        { from: 'decode.rd', to: 'id_ex.rd_in', path: 'manhattan', style: 'control' },
        { from: 'decode.imm', to: 'id_ex.imm_in', path: 'manhattan', style: 'control' },

        // -- EX stage -- //
        // ID/EX -> Forwarding
        { from: 'id_ex.rs1_addr_out', to: 'forwarding.id_ex_rs1', path: 'manhattan', style: 'data' },
        { from: 'id_ex.rs2_addr_out', to: 'forwarding.id_ex_rs2', path: 'manhattan', style: 'data' },
        { from: 'id_ex.rs1_data_out', to: 'forwarding.rs1_data_in', path: 'manhattan', style: 'data' },
        { from: 'id_ex.rs2_data_out', to: 'forwarding.rs2_data_in', path: 'manhattan', style: 'data' },

        // Forwarding -> ALU Mux
        { from: 'forwarding.rs1_data_out', to: 'alu_mux.rs1_data', path: [
            [S(2) + 180, COMP_Y1 + 15],
            [S(2) + 65, COMP_Y1 + 15],
            [S(2) + 65, COMP_Y2 + 12],
            [S(2) + 75, COMP_Y2 + 12],
        ], style: 'data' },
        { from: 'forwarding.rs2_data_out', to: 'alu_mux.rs2_data', path: [
            [S(2) + 180, COMP_Y1 + 35],
            [S(2) + 60, COMP_Y1 + 35],
            [S(2) + 60, COMP_Y2 + 27],
            [S(2) + 75, COMP_Y2 + 27],
        ], style: 'data' },

        // ALU Mux -> ALU
        { from: 'alu_mux.alu_a', to: 'alu.a', path: [
            [S(2) + 105, COMP_Y2 + 15],
            [S(2) + 115, COMP_Y2 + 15],
            [S(2) + 115, COMP_Y3 + 16],
            [S(2) + 20, COMP_Y3 + 16],
        ], style: 'data' },
        { from: 'alu_mux.alu_b', to: 'alu.b', path: [
            [S(2) + 105, COMP_Y2 + 35],
            [S(2) + 120, COMP_Y2 + 35],
            [S(2) + 120, COMP_Y3 + 38],
            [S(2) + 20, COMP_Y3 + 38],
        ], style: 'data' },

        // ALU -> EX/MEM
        { from: 'alu.result', to: 'ex_mem.alu_result_in', path: 'manhattan', style: 'data', label: 'result' },
        { from: 'alu.zero', to: 'ex_mem.alu_zero_in', path: 'manhattan', style: 'data' },

        // -- MEM stage -- //
        // EX/MEM -> DMem
        { from: 'ex_mem.alu_result_out', to: 'dmem.addr', path: 'manhattan', style: 'data', label: 'addr' },
        { from: 'ex_mem.rs2_data_out', to: 'dmem.wdata', path: 'manhattan', style: 'data' },
        { from: 'ex_mem.mem_write_out', to: 'dmem.wen', path: [
            [B(2) + BAR_W, COMP_Y1 + BAR_H * 0.84],
            [S(3) + 100, COMP_Y1 + BAR_H * 0.84],
            [S(3) + 100, COMP_Y1],
        ], style: 'control', label: 'wen' },

        // EX/MEM -> Branch Resolution
        { from: 'ex_mem.pc_out', to: 'branch.pc', path: 'manhattan', style: 'data' },
        { from: 'ex_mem.pc4_out', to: 'branch.pc4', path: 'manhattan', style: 'data' },
        { from: 'ex_mem.imm_out', to: 'branch.imm', path: 'manhattan', style: 'data' },
        { from: 'ex_mem.branch_out', to: 'branch.branch', path: 'manhattan', style: 'control' },
        { from: 'ex_mem.alu_zero_out', to: 'branch.alu_zero', path: [
            [B(2) + BAR_W, COMP_Y1 + BAR_H * 0.25],
            [S(3) + 130, COMP_Y1 + BAR_H * 0.25],
            [S(3) + 130, BRANCH_Y],
        ], style: 'data' },

        // DMem -> MEM/WB
        { from: 'dmem.rdata', to: 'mem_wb.mem_data_in', path: 'manhattan', style: 'data', label: 'rdata' },

        // EX/MEM -> MEM/WB (pass-through)
        { from: 'ex_mem.alu_result_out', to: 'mem_wb.alu_result_in', path: [
            [B(2) + BAR_W, COMP_Y1 + BAR_H * 0.15],
            [B(2) + BAR_W + 8, COMP_Y1 + BAR_H * 0.15],
            [B(2) + BAR_W + 8, COMP_Y1 - 10],
            [B(3) - 8, COMP_Y1 - 10],
            [B(3) - 8, COMP_Y1 + BAR_H * 0.2],
            [B(3), COMP_Y1 + BAR_H * 0.2],
        ], style: 'data' },
        { from: 'ex_mem.rd_out', to: 'mem_wb.rd_in', path: [
            [B(2) + BAR_W, COMP_Y1 + BAR_H * 0.45],
            [B(2) + BAR_W + 12, COMP_Y1 + BAR_H * 0.45],
            [B(2) + BAR_W + 12, COMP_Y1 - 16],
            [B(3) - 12, COMP_Y1 - 16],
            [B(3) - 12, COMP_Y1 + BAR_H * 0.5],
            [B(3), COMP_Y1 + BAR_H * 0.5],
        ], style: 'data' },
        { from: 'ex_mem.reg_write_out', to: 'mem_wb.reg_write_in', path: [
            [B(2) + BAR_W, COMP_Y1 + BAR_H * 0.88],
            [B(2) + BAR_W + 5, COMP_Y1 + BAR_H * 0.88],
            [B(2) + BAR_W + 5, COMP_Y1 + BAR_H + 10],
            [B(3) - 5, COMP_Y1 + BAR_H + 10],
            [B(3) - 5, COMP_Y1 + BAR_H * 0.8],
            [B(3), COMP_Y1 + BAR_H * 0.8],
        ], style: 'control' },
        { from: 'ex_mem.wb_sel_out', to: 'mem_wb.wb_sel_in', path: [
            [B(2) + BAR_W, COMP_Y1 + BAR_H * 0.99],
            [B(2) + BAR_W + 3, COMP_Y1 + BAR_H * 0.99],
            [B(2) + BAR_W + 3, COMP_Y1 + BAR_H + 14],
            [B(3) - 3, COMP_Y1 + BAR_H + 14],
            [B(3) - 3, COMP_Y1 + BAR_H * 0.9],
            [B(3), COMP_Y1 + BAR_H * 0.9],
        ], style: 'control' },

        // -- WB stage -- //
        { from: 'mem_wb.alu_result_out', to: 'wb.alu_in', path: 'manhattan', style: 'data' },
        { from: 'mem_wb.mem_data_out', to: 'wb.mem_in', path: 'manhattan', style: 'data' },
        { from: 'mem_wb.pc4_out', to: 'wb.pc4_in', path: 'manhattan', style: 'data' },
        { from: 'mem_wb.wb_sel_out', to: 'wb.sel', path: [
            [B(3) + BAR_W, COMP_Y1 + BAR_H * 0.9],
            [S(4) + 100, COMP_Y1 + BAR_H * 0.9],
            [S(4) + 100, COMP_Y1],
        ], style: 'control', label: 'wb_sel' },

        // WB -> RegFile (writeback feedback)
        {
            from: 'wb.data_out', to: 'regfile.rd_data', style: 'data', label: 'WB data',
            path: [
                [S(4) + 170, COMP_Y1 + 27],
                [S(4) + 190, COMP_Y1 + 27],
                [S(4) + 190, H - 20],
                [S(1) + 5, H - 20],
                [S(1) + 5, COMP_Y2 + 59],
                [S(1) + 20, COMP_Y2 + 59],
            ],
            _feedbackY: H - 20,
        },
        {
            from: 'mem_wb.rd_out', to: 'regfile.rd_addr', style: 'data', label: 'rd',
            path: [
                [B(3) + BAR_W, COMP_Y1 + BAR_H * 0.5],
                [B(3) + BAR_W + 15, COMP_Y1 + BAR_H * 0.5],
                [B(3) + BAR_W + 15, H - 28],
                [S(1) + 10, H - 28],
                [S(1) + 10, COMP_Y2 + 49],
                [S(1) + 20, COMP_Y2 + 49],
            ],
            _feedbackY: H - 28,
        },
        {
            from: 'mem_wb.reg_write_out', to: 'regfile.wen', style: 'control', label: 'wen',
            path: [
                [B(3) + BAR_W, COMP_Y1 + BAR_H * 0.8],
                [B(3) + BAR_W + 20, COMP_Y1 + BAR_H * 0.8],
                [B(3) + BAR_W + 20, H - 35],
                [S(1) + 148, H - 35],
                [S(1) + 148, COMP_Y2],
            ],
            _feedbackY: H - 35,
        },

        // -- Branch -> Fetch (feedback) -- //
        {
            from: 'branch.next_pc', to: 'fetch.next_pc', style: 'data', label: 'next_pc',
            path: [
                [S(3) + 180, BRANCH_Y + 19],
                [S(3) + 195, BRANCH_Y + 19],
                [S(3) + 195, BRANCH_Y + 75],
                [S(0) - 10, BRANCH_Y + 75],
                [S(0) - 10, COMP_Y1 + 36],
                [S(0) + 20, COMP_Y1 + 36],
            ],
            _feedbackY: BRANCH_Y + 75,
        },
        {
            from: 'branch.mispredict', to: 'fetch.branch_taken', style: 'control', label: 'flush',
            path: [
                [S(3) + 180, BRANCH_Y + 36],
                [S(3) + 200, BRANCH_Y + 36],
                [S(3) + 200, BRANCH_Y + 85],
                [S(0) - 15, BRANCH_Y + 85],
                [S(0) - 15, COMP_Y1 + 19],
                [S(0) + 20, COMP_Y1 + 19],
            ],
            _feedbackY: BRANCH_Y + 85,
        },
        // Branch flush -> IF/ID, ID/EX, EX/MEM
        {
            from: 'branch.mispredict', to: 'if_id.flush', style: 'control',
            path: [
                [S(3) + 180, BRANCH_Y + 36],
                [S(3) + 200, BRANCH_Y + 36],
                [S(3) + 200, BRANCH_Y + 85],
                [B(0) + BAR_W / 2, BRANCH_Y + 85],
                [B(0) + BAR_W / 2, COMP_Y1 + BAR_H],
            ],
            _feedbackY: BRANCH_Y + 85,
        },
        {
            from: 'branch.mispredict', to: 'id_ex.flush', style: 'control',
            path: [
                [S(3) + 180, BRANCH_Y + 36],
                [S(3) + 200, BRANCH_Y + 36],
                [S(3) + 200, BRANCH_Y + 80],
                [B(1) + BAR_W / 2, BRANCH_Y + 80],
                [B(1) + BAR_W / 2, COMP_Y1 + BAR_H],
            ],
            _feedbackY: BRANCH_Y + 80,
        },

        // -- Forwarding backward arcs (EX/MEM -> Forwarding, MEM/WB -> Forwarding) -- //
        {
            from: 'ex_mem.rd_out', to: 'forwarding.ex_mem_rd', style: 'control', label: 'fwd EX',
            path: [
                [B(2) + BAR_W, COMP_Y1 + BAR_H * 0.45],
                [B(2) + BAR_W + 18, COMP_Y1 + BAR_H * 0.45],
                [B(2) + BAR_W + 18, COMP_Y1 + 60],
                [S(2) + 52, COMP_Y1 + 60],
                [S(2) + 52, COMP_Y1 + 50],
            ],
        },
        {
            from: 'ex_mem.reg_write_out', to: 'forwarding.ex_mem_reg_write', style: 'control',
            path: [
                [B(2) + BAR_W, COMP_Y1 + BAR_H * 0.88],
                [B(2) + BAR_W + 22, COMP_Y1 + BAR_H * 0.88],
                [B(2) + BAR_W + 22, COMP_Y1 + 65],
                [S(2) + 76, COMP_Y1 + 65],
                [S(2) + 76, COMP_Y1 + 50],
            ],
        },

        // -- Hazard detector -- //
        {
            from: 'hazard_det.stall', to: 'fetch.stall', style: 'control', label: 'stall',
            path: [
                [S(1) + STAGE_W / 2, HAZARD_Y],
                [S(1) + STAGE_W / 2, HAZARD_Y - 10],
                [S(0) + 100, HAZARD_Y - 10],
                [S(0) + 100, COMP_Y1],
            ],
        },
        {
            from: 'hazard_det.stall', to: 'if_id.stall', style: 'control',
            path: [
                [S(1) + STAGE_W / 2, HAZARD_Y],
                [S(1) + STAGE_W / 2, HAZARD_Y - 15],
                [B(0) + BAR_W / 2, HAZARD_Y - 15],
                [B(0) + BAR_W / 2, COMP_Y1],
            ],
        },
        {
            from: 'hazard_det.stall', to: 'id_ex.stall', style: 'control',
            path: [
                [S(1) + STAGE_W / 2, HAZARD_Y],
                [B(1) + BAR_W / 2, HAZARD_Y],
                [B(1) + BAR_W / 2, COMP_Y1],
            ],
        },

        // -- Branch predictor -- //
        {
            from: 'fetch.pc_out', to: 'bpred.pc', style: 'control',
            path: [
                [S(0) + 180, COMP_Y1 + 19],
                [S(0) + 190, COMP_Y1 + 19],
                [S(0) + 190, BPRED_Y + 13],
                [S(1) + 20, BPRED_Y + 13],
            ],
        },
        {
            from: 'branch.branch_taken', to: 'bpred.actual', style: 'control',
            path: [
                [S(3) + 180, BRANCH_Y + 36],
                [S(3) + 205, BRANCH_Y + 36],
                [S(3) + 205, BPRED_Y + 22],
                [S(1) + 180, BPRED_Y + 22],
            ],
        },
    ];

    // ================================================================== //
    //  Annotations                                                        //
    // ================================================================== //
    const annotations = [
        {
            type: 'label', x: W / 2, y: 18, text: '5-Stage Pipeline Datapath',
            color: '#e0e0e6', fontSize: '16px', fontWeight: '700', anchor: 'middle',
        },
        // Dashed box around hazard area
        {
            type: 'dashed_box',
            x: S(1) - 5, y: HAZARD_Y - 8, w: S(2) + STAGE_W - S(1) + 10, h: 60,
            text: 'Hazard Detection', color: '#f43f5e',
        },
        // Forwarding label
        {
            type: 'dashed_box',
            x: S(2) + 14, y: COMP_Y1 - 5, w: 172, h: 62,
            text: 'Forwarding', color: '#a78bfa',
        },
    ];

    return { width: W, height: H, components, wires, annotations, stages };
}

// Export
window.getPipelineLayout = getPipelineLayout;
