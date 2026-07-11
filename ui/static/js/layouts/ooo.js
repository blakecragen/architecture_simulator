/**
 * RTL CPU Simulator -- Out-of-Order Layout Template
 *
 * Redesigned for clarity:
 *  - Wider column spacing: decode→RAT gap 100 px (was 50 px)
 *  - RS control-signal ports (issue_en/op/imm/alu_src) moved to TOP face so
 *    decode→RS wires bypass the decode→RAT corridor entirely
 *  - decode→RAT wires use a tight right-side bundle (x=513-521)
 *  - decode→Regfile wires use a separate corridor (x=536-540)
 *  - decode→RS wires travel east through y=210-234 (below decode, above OOO_Y)
 *  - ROB dispatch/feedback wires routed on the left margin (x=170-180)
 */

/* global window */

function getOoOLayout() {
    const W = 1310;
    const H = 790;

    // -- Row positions -------------------------------------------------- //
    const FRONTEND_Y = 60;     // fetch → decode row
    const OOO_Y      = 250;    // RAT + RS row
    const EXEC_Y     = 420;    // ALU execution row
    const COMMIT_Y   = 600;    // ROB + regfile commit row
    const BPRED_Y    = 10;     // predictor at top

    // -- Column positions ----------------------------------------------- //
    const COL1 = 30;           // Fetch
    const COL2 = 190;          // IMem
    const COL3 = 380;          // Decode
    const COL4 = 610;          // RAT  (was 560 — 100 px gap from decode right)
    const COL5 = 820;          // RS   (was 760)
    const COL_ALU_MUX = 680;
    const COL_ALU     = 820;
    const COL_ROB     = 200;
    const COL_REGFILE = 610;
    const COL_DMEM    = 1030;
    const COL_WB      = 1030;

    // -- Derived shortcuts ---------------------------------------------- //
    // decode right edge = COL3+130 = 510
    // RAT left edge     = COL4     = 610  → 100 px gap

    const components = {
        // ============================================================== //
        //  Frontend pipeline (top row)                                    //
        // ============================================================== //
        bpred: {
            x: COL3 + 20, y: BPRED_Y, w: 130, h: 38,
            shape: 'rect', label: 'Branch Predictor', category: 'control',
            ports: {
                pc:        { side: 'left',   offset: 0.3 },
                is_branch: { side: 'left',   offset: 0.7 },
                update_en: { side: 'bottom', offset: 0.3 },
                actual:    { side: 'bottom', offset: 0.7 },
            },
        },
        fetch: {
            x: COL1, y: FRONTEND_Y, w: 110, h: 55,
            shape: 'rect', label: 'Fetch / PC', category: 'fetch',
            ports: {
                pc_out:       { side: 'right', offset: 0.35 },
                pc4_out:      { side: 'right', offset: 0.65 },
                next_pc:      { side: 'left',  offset: 0.65 },
                branch_taken: { side: 'left',  offset: 0.35 },
                stall:        { side: 'top',   offset: 0.5  },
            },
        },
        imem: {
            x: COL2, y: FRONTEND_Y, w: 130, h: 55,
            shape: 'rect', label: 'Instr Memory', category: 'fetch',
            ports: {
                addr: { side: 'left',  offset: 0.5 },
                data: { side: 'right', offset: 0.5 },
            },
        },
        decode: {
            x: COL3, y: FRONTEND_Y, w: 130, h: 65,
            shape: 'rect', label: 'Decoder', category: 'decode',
            ports: {
                instr_in:    { side: 'left',   offset: 0.4  },
                rs1:         { side: 'right',  offset: 0.15 },
                rs2:         { side: 'right',  offset: 0.30 },
                rd:          { side: 'right',  offset: 0.45 },
                imm:         { side: 'right',  offset: 0.60 },
                alu_op:      { side: 'right',  offset: 0.75 },
                alu_src:     { side: 'right',  offset: 0.88 },
                wb_sel:      { side: 'right',  offset: 0.95 },
                reg_write:   { side: 'bottom', offset: 0.30 },
                branch:      { side: 'bottom', offset: 0.50 },
                branch_cond: { side: 'bottom', offset: 0.65 },
                jal:         { side: 'bottom', offset: 0.75 },
                jalr:        { side: 'bottom', offset: 0.85 },
                mem_write:   { side: 'bottom', offset: 0.15 },
                mem_read:    { side: 'bottom', offset: 0.95 },
                use_pc:      { side: 'bottom', offset: 0.05 },
            },
        },

        // ============================================================== //
        //  OoO issue stage (second row)                                   //
        // ============================================================== //
        rat: {
            x: COL4, y: OOO_Y, w: 120, h: 70,
            shape: 'rect', label: 'RAT', category: 'ooo',
            ports: {
                rs1_arch:   { side: 'left',   offset: 0.15 },
                rs2_arch:   { side: 'left',   offset: 0.30 },
                rd_arch:    { side: 'left',   offset: 0.45 },
                alloc_en:   { side: 'left',   offset: 0.60 },
                alloc_tag:  { side: 'left',   offset: 0.75 },
                rs1_ready:  { side: 'right',  offset: 0.15 },
                rs1_tag:    { side: 'right',  offset: 0.30 },
                rs2_ready:  { side: 'right',  offset: 0.50 },
                rs2_tag:    { side: 'right',  offset: 0.65 },
                commit_en:  { side: 'bottom', offset: 0.30 },
                commit_rd:  { side: 'bottom', offset: 0.50 },
                commit_tag: { side: 'bottom', offset: 0.70 },
                flush:      { side: 'bottom', offset: 0.90 },
            },
        },
        rs: {
            x: COL5, y: OOO_Y, w: 150, h: 80,
            shape: 'rect', label: 'Reservation Station', category: 'ooo',
            ports: {
                // Left face: readiness + value signals from RAT / RegFile
                issue_src1_ready: { side: 'left', offset: 0.12 },
                issue_src1_tag:   { side: 'left', offset: 0.25 },
                issue_src1_val:   { side: 'left', offset: 0.38 },
                issue_src2_ready: { side: 'left', offset: 0.52 },
                issue_src2_tag:   { side: 'left', offset: 0.65 },
                issue_src2_val:   { side: 'left', offset: 0.78 },
                issue_rob_tag:    { side: 'left', offset: 0.90 },
                // Top face: control signals from Decode (separate corridor)
                issue_en:         { side: 'top',  offset: 0.08 },
                issue_op:         { side: 'top',  offset: 0.22 },
                issue_imm:        { side: 'top',  offset: 0.42 },
                issue_alu_src:    { side: 'top',  offset: 0.58 },
                flush:            { side: 'top',  offset: 0.90 },
                // Bottom face: outputs to ALU
                exec_src1:        { side: 'bottom', offset: 0.20 },
                exec_src2:        { side: 'bottom', offset: 0.40 },
                exec_op:          { side: 'bottom', offset: 0.60 },
                exec_valid:       { side: 'bottom', offset: 0.78 },
                exec_rob_tag:     { side: 'bottom', offset: 0.90 },
                // Right face: CDB snoop feedback
                cdb_en:           { side: 'right', offset: 0.30 },
                cdb_tag:          { side: 'right', offset: 0.50 },
                cdb_value:        { side: 'right', offset: 0.70 },
            },
        },

        // ============================================================== //
        //  Execution stage (third row)                                    //
        // ============================================================== //
        alu_mux: {
            x: COL_ALU_MUX, y: EXEC_Y + 10, w: 28, h: 55,
            shape: 'mux', label: 'M', category: 'execute', direction: 'right',
            ports: {
                rs1_data: { side: 'left',   offset: 0.25 },
                rs2_data: { side: 'left',   offset: 0.5  },
                imm:      { side: 'left',   offset: 0.80 },
                pc:       { side: 'top',    offset: 0.5  },
                use_pc:   { side: 'bottom', offset: 0.3  },
                alu_src:  { side: 'bottom', offset: 0.7  },
                alu_a:    { side: 'right',  offset: 0.3  },
                alu_b:    { side: 'right',  offset: 0.7  },
            },
        },
        alu: {
            x: COL_ALU, y: EXEC_Y, w: 140, h: 60,
            shape: 'rect', label: 'ALU', category: 'execute',
            ports: {
                a:      { side: 'left',  offset: 0.3  },
                b:      { side: 'left',  offset: 0.7  },
                op:     { side: 'top',   offset: 0.5  },
                result: { side: 'right', offset: 0.35 },
                zero:   { side: 'right', offset: 0.7  },
            },
        },
        flags_reg: {
            x: COL_ALU, y: EXEC_Y + 70, w: 120, h: 38,
            shape: 'rect', label: 'Flags Register', category: 'execute',
            ports: {
                alu_zero_in:   { side: 'top',  offset: 0.3 },
                alu_result_in: { side: 'top',  offset: 0.7 },
                zero_out:      { side: 'left', offset: 0.5 },
            },
        },

        // ============================================================== //
        //  Data Memory + Writeback (right side)                           //
        // ============================================================== //
        dmem: {
            x: COL_DMEM, y: EXEC_Y, w: 120, h: 60,
            shape: 'rect', label: 'Data Memory', category: 'memory',
            ports: {
                addr:  { side: 'left',   offset: 0.25 },
                wdata: { side: 'left',   offset: 0.55 },
                wen:   { side: 'top',    offset: 0.5  },
                rdata: { side: 'bottom', offset: 0.5  },
            },
        },
        wb: {
            x: COL_WB, y: EXEC_Y + 90, w: 120, h: 50,
            shape: 'rect', label: 'Writeback Mux', category: 'writeback',
            ports: {
                alu_in:   { side: 'left',   offset: 0.25 },
                mem_in:   { side: 'top',    offset: 0.5  },
                pc4_in:   { side: 'left',   offset: 0.75 },
                sel:      { side: 'right',  offset: 0.8  },
                data_out: { side: 'bottom', offset: 0.5  },
            },
        },

        // ============================================================== //
        //  Commit stage (bottom row)                                       //
        // ============================================================== //
        rob: {
            x: COL_ROB, y: COMMIT_Y, w: 260, h: 80,
            shape: 'rect', label: 'Reorder Buffer (ROB)', category: 'ooo',
            ports: {
                dispatch_en:        { side: 'top',    offset: 0.15 },
                dispatch_rd:        { side: 'top',    offset: 0.30 },
                dispatch_pc:        { side: 'top',    offset: 0.45 },
                dispatch_is_branch: { side: 'top',    offset: 0.60 },
                dispatch_tag:       { side: 'top',    offset: 0.80 },
                complete_en:        { side: 'right',  offset: 0.15 },
                complete_tag:       { side: 'right',  offset: 0.35 },
                complete_value:     { side: 'right',  offset: 0.55 },
                commit_en:          { side: 'right',  offset: 0.70 },
                commit_rd:          { side: 'right',  offset: 0.80 },
                commit_value:       { side: 'right',  offset: 0.90 },
                commit_tag:         { side: 'bottom', offset: 0.50 },
                flush:              { side: 'left',   offset: 0.50 },
            },
        },
        regfile: {
            x: COL_REGFILE, y: COMMIT_Y, w: 140, h: 80,
            shape: 'rect', label: 'Register File', category: 'decode',
            ports: {
                rs1_addr: { side: 'top',  offset: 0.15 },
                rs2_addr: { side: 'top',  offset: 0.35 },
                rs1_data: { side: 'top',  offset: 0.55 },
                rs2_data: { side: 'top',  offset: 0.75 },
                rd_addr:  { side: 'left', offset: 0.30 },
                rd_data:  { side: 'left', offset: 0.55 },
                wen:      { side: 'left', offset: 0.80 },
            },
        },

        // ============================================================== //
        //  Branch Resolution (left, exec row)                             //
        // ============================================================== //
        branch: {
            x: 30, y: EXEC_Y + 5, w: 140, h: 55,
            shape: 'rect', label: 'Branch Resolution', category: 'control',
            ports: {
                pc:           { side: 'top',    offset: 0.15 },
                pc4:          { side: 'top',    offset: 0.35 },
                imm:          { side: 'top',    offset: 0.55 },
                rs1_data:     { side: 'top',    offset: 0.75 },
                branch:       { side: 'left',   offset: 0.2  },
                branch_cond:  { side: 'left',   offset: 0.4  },
                jal:          { side: 'left',   offset: 0.6  },
                jalr:         { side: 'left',   offset: 0.8  },
                alu_zero:     { side: 'right',  offset: 0.3  },
                alu_result:   { side: 'right',  offset: 0.6  },
                next_pc:      { side: 'bottom', offset: 0.3  },
                branch_taken: { side: 'bottom', offset: 0.7  },
            },
        },
    };

    // ================================================================== //
    //  Wire helper: inline coordinate constants                           //
    // ================================================================== //
    // decode right edge   = 510   (COL3+130)
    // decode bottom edge  = 125   (FRONTEND_Y+65)
    // RAT left edge       = 610   (COL4)
    // RAT right edge      = 730   (COL4+120)
    // RAT bottom edge     = 320   (OOO_Y+70)
    // RS left edge        = 820   (COL5)
    // RS top edge         = 250   (OOO_Y)
    // RS bottom edge      = 330   (OOO_Y+80)
    // ALU right edge      = 960   (COL_ALU+140)
    // ROB right edge      = 460   (COL_ROB+260)
    // REGFILE right edge  = 750   (COL_REGFILE+140)

    const wires = [

        // ---------------------------------------------------------------- //
        //  Frontend pipeline                                                //
        // ---------------------------------------------------------------- //
        { from: 'fetch.pc_out',  to: 'imem.addr',       path: 'manhattan', style: 'data', label: 'PC',    layer: 'data' },
        { from: 'imem.data',     to: 'decode.instr_in', path: 'manhattan', style: 'data', label: 'instr', layer: 'data' },

        // ---------------------------------------------------------------- //
        //  Bundle A: decode → RegFile read addresses                        //
        //  Corridor x=536-540, turning east at y=155-162                   //
        // ---------------------------------------------------------------- //
        {
            from: 'decode.rs1', to: 'regfile.rs1_addr', style: 'data', label: 'rs1',
            bus: 'operand', layer: 'data',
            path: [
                [510, FRONTEND_Y + 10],
                [536, FRONTEND_Y + 10],
                [536, 155],
                [COL_REGFILE + 21, 155],
                [COL_REGFILE + 21, COMMIT_Y],
            ],
        },
        {
            from: 'decode.rs2', to: 'regfile.rs2_addr', style: 'data', label: 'rs2',
            bus: 'operand', layer: 'data',
            path: [
                [510, FRONTEND_Y + 20],
                [540, FRONTEND_Y + 20],
                [540, 162],
                [COL_REGFILE + 49, 162],
                [COL_REGFILE + 49, COMMIT_Y],
            ],
        },

        // ---------------------------------------------------------------- //
        //  Bundle B: decode → RAT (register renaming)                       //
        //  Corridor x=513/517/521, going south then east into RAT left     //
        // ---------------------------------------------------------------- //
        {
            from: 'decode.rs1', to: 'rat.rs1_arch', style: 'data',
            bus: 'operand', layer: 'data',
            path: [
                [510, FRONTEND_Y + 10],
                [513, FRONTEND_Y + 10],
                [513, OOO_Y + 11],
                [COL4, OOO_Y + 11],
            ],
        },
        {
            from: 'decode.rs2', to: 'rat.rs2_arch', style: 'data',
            bus: 'operand', layer: 'data',
            path: [
                [510, FRONTEND_Y + 20],
                [517, FRONTEND_Y + 20],
                [517, OOO_Y + 21],
                [COL4, OOO_Y + 21],
            ],
        },
        {
            from: 'decode.rd', to: 'rat.rd_arch', style: 'data', label: 'rd',
            bus: 'operand', layer: 'data',
            path: [
                [510, FRONTEND_Y + 29],
                [521, FRONTEND_Y + 29],
                [521, OOO_Y + 32],
                [COL4, OOO_Y + 32],
            ],
        },
        // reg_write → RAT alloc_en: straight south from decode bottom then east
        {
            from: 'decode.reg_write', to: 'rat.alloc_en', style: 'control',
            bus: 'dispatch', layer: 'control',
            path: [
                [COL3 + 39, 125],
                [COL3 + 39, OOO_Y + 42],
                [COL4,      OOO_Y + 42],
            ],
        },

        // ---------------------------------------------------------------- //
        //  Bundle C: decode → RS (control signals via RS TOP face)          //
        //  Corridor x=547-554 going south, turning east at y=210-234       //
        //  These wires are completely separate from Bundle A/B above        //
        // ---------------------------------------------------------------- //
        {
            from: 'decode.reg_write', to: 'rs.issue_en', style: 'control',
            bus: 'dispatch', layer: 'control',
            path: [
                [COL3 + 39, 125],
                [COL3 + 39, 234],
                [COL5 + 12,  234],
                [COL5 + 12,  OOO_Y],
            ],
        },
        {
            from: 'decode.alu_op', to: 'rs.issue_op', style: 'control',
            bus: 'dispatch', layer: 'control',
            path: [
                [510, FRONTEND_Y + 49],
                [547, FRONTEND_Y + 49],
                [547, 226],
                [COL5 + 33, 226],
                [COL5 + 33, OOO_Y],
            ],
        },
        {
            from: 'decode.imm', to: 'rs.issue_imm', style: 'data',
            bus: 'dispatch', layer: 'data',
            path: [
                [510, FRONTEND_Y + 39],
                [550, FRONTEND_Y + 39],
                [550, 218],
                [COL5 + 63, 218],
                [COL5 + 63, OOO_Y],
            ],
        },
        {
            from: 'decode.alu_src', to: 'rs.issue_alu_src', style: 'control',
            bus: 'dispatch', layer: 'control',
            path: [
                [510, FRONTEND_Y + 57],
                [554, FRONTEND_Y + 57],
                [554, 210],
                [COL5 + 87, 210],
                [COL5 + 87, OOO_Y],
            ],
        },

        // ---------------------------------------------------------------- //
        //  ROB dispatch: decode → ROB (going west along dedicated lanes)    //
        // ---------------------------------------------------------------- //
        {
            from: 'decode.reg_write', to: 'rob.dispatch_en', style: 'control',
            bus: 'dispatch', layer: 'control',
            path: [
                [COL3 + 39, 125],
                [COL3 + 39, 140],
                [COL_ROB + 39, 140],
                [COL_ROB + 39, COMMIT_Y],
            ],
        },
        {
            from: 'decode.rd', to: 'rob.dispatch_rd', style: 'data',
            bus: 'dispatch', layer: 'data',
            path: [
                [510, FRONTEND_Y + 29],
                [524, FRONTEND_Y + 29],
                [524, 144],
                [COL_ROB + 78, 144],
                [COL_ROB + 78, COMMIT_Y],
            ],
        },
        {
            from: 'fetch.pc_out', to: 'rob.dispatch_pc', style: 'data',
            bus: 'dispatch', layer: 'data',
            path: [
                [COL1 + 110, FRONTEND_Y + 19],
                [155, FRONTEND_Y + 19],
                [155, 170],
                [COL_ROB + 117, 170],
                [COL_ROB + 117, COMMIT_Y],
            ],
        },

        // ---------------------------------------------------------------- //
        //  ROB dispatch_tag → RAT + RS  (via left-margin corridor x=186-192)//
        // ---------------------------------------------------------------- //
        {
            from: 'rob.dispatch_tag', to: 'rat.alloc_tag', style: 'data', label: 'tag',
            bus: 'dispatch', layer: 'data',
            path: [
                [COL_ROB + 208, COMMIT_Y],
                [192, COMMIT_Y],
                [192, OOO_Y + 53],
                [COL4, OOO_Y + 53],
            ],
        },
        {
            from: 'rob.dispatch_tag', to: 'rs.issue_rob_tag', style: 'data',
            bus: 'dispatch', layer: 'data',
            path: [
                [COL_ROB + 208, COMMIT_Y],
                [COL_ROB + 208, 560],
                [COL5 + 135,    560],
                [COL5 + 135,    OOO_Y + 72],
                [COL5,          OOO_Y + 72],
            ],
        },

        // ---------------------------------------------------------------- //
        //  RAT → RS (operand readiness tags) — short horizontal runs        //
        // ---------------------------------------------------------------- //
        { from: 'rat.rs1_ready', to: 'rs.issue_src1_ready', path: 'manhattan', style: 'data', bus: 'operand', layer: 'data' },
        { from: 'rat.rs1_tag',   to: 'rs.issue_src1_tag',   path: 'manhattan', style: 'data', bus: 'operand', layer: 'data' },
        { from: 'rat.rs2_ready', to: 'rs.issue_src2_ready', path: 'manhattan', style: 'data', bus: 'operand', layer: 'data' },
        { from: 'rat.rs2_tag',   to: 'rs.issue_src2_tag',   path: 'manhattan', style: 'data', bus: 'operand', layer: 'data' },

        // ---------------------------------------------------------------- //
        //  RegFile → RS (source operand values, routed east then north)     //
        // ---------------------------------------------------------------- //
        {
            from: 'regfile.rs1_data', to: 'rs.issue_src1_val', style: 'data',
            bus: 'operand', layer: 'data',
            path: [
                [COL_REGFILE + 77, COMMIT_Y],
                [COL_REGFILE + 77, 568],
                [COL5 + 131,       568],
                [COL5 + 131,       OOO_Y + 30],
                [COL5,             OOO_Y + 30],
            ],
        },
        {
            from: 'regfile.rs2_data', to: 'rs.issue_src2_val', style: 'data',
            bus: 'operand', layer: 'data',
            path: [
                [COL_REGFILE + 105, COMMIT_Y],
                [COL_REGFILE + 105, 564],
                [COL5 + 127,        564],
                [COL5 + 127,        OOO_Y + 62],
                [COL5,              OOO_Y + 62],
            ],
        },

        // ---------------------------------------------------------------- //
        //  RS → ALU (execution dispatch)                                    //
        // ---------------------------------------------------------------- //
        {
            from: 'rs.exec_src1', to: 'alu.a', style: 'data', label: 'src1',
            bus: 'execute', layer: 'data',
            path: [
                [COL5 + 30, OOO_Y + 80],
                [COL5 + 30, EXEC_Y + 18],
                [COL_ALU,   EXEC_Y + 18],
            ],
        },
        {
            from: 'rs.exec_src2', to: 'alu.b', style: 'data', label: 'src2',
            bus: 'execute', layer: 'data',
            path: [
                [COL5 + 60, OOO_Y + 80],
                [COL5 + 60, EXEC_Y + 42],
                [COL_ALU,   EXEC_Y + 42],
            ],
        },
        {
            from: 'rs.exec_op', to: 'alu.op', style: 'control', label: 'op',
            bus: 'execute', layer: 'data',
            path: [
                [COL5 + 90, OOO_Y + 80],
                [COL5 + 90, EXEC_Y - 8],
                [COL_ALU + 70, EXEC_Y - 8],
                [COL_ALU + 70, EXEC_Y],
            ],
        },

        // ---------------------------------------------------------------- //
        //  CDB: ALU result → ROB complete + RS snoop                        //
        // ---------------------------------------------------------------- //
        {
            from: 'alu.result', to: 'rob.complete_value', style: 'data', label: 'CDB value',
            bus: 'cdb', layer: 'cdb',
            path: [
                [COL_ALU + 140, EXEC_Y + 21],
                [980,           EXEC_Y + 21],
                [980,           COMMIT_Y + 44],
                [COL_ROB + 260, COMMIT_Y + 44],
            ],
        },
        {
            from: 'rs.exec_valid', to: 'rob.complete_en', style: 'control',
            bus: 'cdb', layer: 'cdb',
            path: [
                [COL5 + 117, OOO_Y + 80],
                [COL5 + 117, EXEC_Y - 15],
                [984,        EXEC_Y - 15],
                [984,        COMMIT_Y + 12],
                [COL_ROB + 260, COMMIT_Y + 12],
            ],
        },
        {
            from: 'rs.exec_rob_tag', to: 'rob.complete_tag', style: 'data',
            bus: 'cdb', layer: 'cdb',
            path: [
                [COL5 + 135, OOO_Y + 80],
                [COL5 + 135, EXEC_Y - 20],
                [988,        EXEC_Y - 20],
                [988,        COMMIT_Y + 28],
                [COL_ROB + 260, COMMIT_Y + 28],
            ],
        },
        // CDB → RS snoop (right-side feedback)
        {
            from: 'rs.exec_valid', to: 'rs.cdb_en', style: 'control', label: 'CDB snoop',
            bus: 'cdb', layer: 'cdb',
            path: [
                [COL5 + 117, OOO_Y + 80],
                [COL5 + 117, OOO_Y + 88],
                [COL5 + 175, OOO_Y + 88],
                [COL5 + 175, OOO_Y + 24],
                [COL5 + 150, OOO_Y + 24],
            ],
        },
        {
            from: 'alu.result', to: 'rs.cdb_value', style: 'data',
            bus: 'cdb', layer: 'cdb',
            path: [
                [COL_ALU + 140, EXEC_Y + 21],
                [COL_ALU + 160, EXEC_Y + 21],
                [COL_ALU + 160, OOO_Y + 56],
                [COL5 + 150,    OOO_Y + 56],
            ],
        },

        // ---------------------------------------------------------------- //
        //  ROB commit → RegFile                                             //
        // ---------------------------------------------------------------- //
        {
            from: 'rob.commit_rd', to: 'regfile.rd_addr', style: 'data', label: 'commit rd',
            bus: 'commit', layer: 'commit',
            path: [
                [COL_ROB + 260, COMMIT_Y + 64],
                [552, COMMIT_Y + 64],
                [552, COMMIT_Y + 24],
                [COL_REGFILE,   COMMIT_Y + 24],
            ],
        },
        {
            from: 'rob.commit_value', to: 'regfile.rd_data', style: 'data', label: 'commit val',
            bus: 'commit', layer: 'commit',
            path: [
                [COL_ROB + 260, COMMIT_Y + 72],
                [557, COMMIT_Y + 72],
                [557, COMMIT_Y + 44],
                [COL_REGFILE,   COMMIT_Y + 44],
            ],
        },
        {
            from: 'rob.commit_en', to: 'regfile.wen', style: 'control', label: 'commit wen',
            bus: 'commit', layer: 'commit',
            path: [
                [COL_ROB + 260, COMMIT_Y + 56],
                [562, COMMIT_Y + 56],
                [562, COMMIT_Y + 64],
                [COL_REGFILE,   COMMIT_Y + 64],
            ],
        },

        // ---------------------------------------------------------------- //
        //  ROB commit → RAT (free mappings, via mid-column corridor x=558-566)//
        // ---------------------------------------------------------------- //
        {
            from: 'rob.commit_en', to: 'rat.commit_en', style: 'control',
            bus: 'commit', layer: 'commit',
            path: [
                [COL_ROB + 260, COMMIT_Y + 56],
                [558, COMMIT_Y + 56],
                [558, OOO_Y + 70],
                [COL4 + 36, OOO_Y + 70],
            ],
        },
        {
            from: 'rob.commit_tag', to: 'rat.commit_tag', style: 'data',
            bus: 'commit', layer: 'commit',
            path: [
                [COL_ROB + 130, COMMIT_Y + 80],
                [COL_ROB + 130, COMMIT_Y + 96],
                [564, COMMIT_Y + 96],
                [564, OOO_Y + 70],
                [COL4 + 84, OOO_Y + 70],
            ],
        },

        // ---------------------------------------------------------------- //
        //  ROB flush → RS, RAT                                              //
        // ---------------------------------------------------------------- //
        {
            from: 'rob.flush', to: 'rs.flush', style: 'control', label: 'flush',
            bus: 'branch', layer: 'control',
            path: [
                [COL_ROB, COMMIT_Y + 40],
                [178, COMMIT_Y + 40],
                [178, OOO_Y - 18],
                [COL5 + 135, OOO_Y - 18],
                [COL5 + 135, OOO_Y],
            ],
        },
        {
            from: 'rob.flush', to: 'rat.flush', style: 'control',
            bus: 'branch', layer: 'control',
            path: [
                [COL_ROB, COMMIT_Y + 40],
                [182, COMMIT_Y + 40],
                [182, OOO_Y + 88],
                [COL4 + 108, OOO_Y + 88],
                [COL4 + 108, OOO_Y + 70],
            ],
        },

        // ---------------------------------------------------------------- //
        //  Branch Resolution                                                //
        // ---------------------------------------------------------------- //
        {
            from: 'fetch.pc_out', to: 'branch.pc', style: 'data',
            bus: 'branch', layer: 'control',
            path: [
                [COL1 + 110, FRONTEND_Y + 19],
                [158,        FRONTEND_Y + 19],
                [158,        EXEC_Y - 10],
                [51,         EXEC_Y - 10],
                [51,         EXEC_Y + 5],
            ],
        },
        {
            from: 'fetch.pc4_out', to: 'branch.pc4', style: 'data',
            bus: 'branch', layer: 'control',
            path: [
                [COL1 + 110, FRONTEND_Y + 36],
                [162,        FRONTEND_Y + 36],
                [162,        EXEC_Y - 5],
                [79,         EXEC_Y - 5],
                [79,         EXEC_Y + 5],
            ],
        },
        {
            from: 'decode.imm', to: 'branch.imm', style: 'data',
            bus: 'branch', layer: 'control',
            path: [
                [510, FRONTEND_Y + 39],
                [510, 130],
                [370, 130],
                [370, EXEC_Y + 8],
                [107, EXEC_Y + 8],
            ],
        },
        {
            from: 'alu.zero', to: 'branch.alu_zero', style: 'data',
            bus: 'branch', layer: 'control',
            path: [
                [COL_ALU + 140, EXEC_Y + 42],
                [COL_ALU + 150, EXEC_Y + 42],
                [COL_ALU + 150, EXEC_Y + 80],
                [195,           EXEC_Y + 80],
                [195,           EXEC_Y + 21],
                [170,           EXEC_Y + 21],
            ],
        },
        {
            from: 'alu.result', to: 'branch.alu_result', style: 'data',
            bus: 'branch', layer: 'control',
            path: [
                [COL_ALU + 140, EXEC_Y + 21],
                [COL_ALU + 155, EXEC_Y + 21],
                [COL_ALU + 155, EXEC_Y + 85],
                [200,           EXEC_Y + 85],
                [200,           EXEC_Y + 38],
                [170,           EXEC_Y + 38],
            ],
        },
        // Branch → Fetch feedback
        {
            from: 'branch.next_pc', to: 'fetch.next_pc', style: 'data', label: 'next_pc',
            bus: 'branch', layer: 'control',
            path: [
                [72,         EXEC_Y + 60],
                [72,         EXEC_Y + 100],
                [COL1 - 10,  EXEC_Y + 100],
                [COL1 - 10,  FRONTEND_Y + 36],
                [COL1,       FRONTEND_Y + 36],
            ],
        },
        {
            from: 'branch.branch_taken', to: 'fetch.branch_taken', style: 'control', label: 'taken',
            bus: 'branch', layer: 'control',
            path: [
                [128,        EXEC_Y + 60],
                [128,        EXEC_Y + 110],
                [COL1 - 15,  EXEC_Y + 110],
                [COL1 - 15,  FRONTEND_Y + 19],
                [COL1,       FRONTEND_Y + 19],
            ],
        },

        // ---------------------------------------------------------------- //
        //  Branch Predictor                                                 //
        // ---------------------------------------------------------------- //
        {
            from: 'fetch.pc_out', to: 'bpred.pc', style: 'control',
            bus: 'branch', layer: 'control',
            path: [
                [COL1 + 110, FRONTEND_Y + 19],
                [165,        FRONTEND_Y + 19],
                [165,        BPRED_Y + 11],
                [COL3 + 20,  BPRED_Y + 11],
            ],
        },
        {
            from: 'decode.branch', to: 'bpred.is_branch', style: 'control',
            bus: 'branch', layer: 'control',
            path: [
                [COL3 + 65, FRONTEND_Y + 65],
                [COL3 + 65, FRONTEND_Y + 70],
                [COL3 + 10, FRONTEND_Y + 70],
                [COL3 + 10, BPRED_Y + 26],
                [COL3 + 20, BPRED_Y + 26],
            ],
        },
        {
            from: 'branch.branch_taken', to: 'bpred.actual', style: 'control',
            bus: 'branch', layer: 'control',
            path: [
                [128,           EXEC_Y + 60],
                [128,           EXEC_Y + 115],
                [COL3 + 160,    EXEC_Y + 115],
                [COL3 + 160,    BPRED_Y + 26],
                [COL3 + 150,    BPRED_Y + 26],
            ],
        },

        // ---------------------------------------------------------------- //
        //  Data Memory + Writeback                                          //
        // ---------------------------------------------------------------- //
        { from: 'alu.result', to: 'dmem.addr', path: 'manhattan', style: 'data', label: 'addr', layer: 'data' },
        {
            from: 'decode.mem_write', to: 'dmem.wen', style: 'control', layer: 'control',
            path: [
                [COL3 + 20, FRONTEND_Y + 65],
                [COL3 + 20, FRONTEND_Y + 108],
                [COL_DMEM + 60, FRONTEND_Y + 108],
                [COL_DMEM + 60, EXEC_Y],
            ],
        },
        { from: 'dmem.rdata', to: 'wb.mem_in',  path: 'manhattan', style: 'data', layer: 'data' },
        {
            from: 'alu.result', to: 'wb.alu_in', style: 'data', layer: 'data',
            path: [
                [COL_ALU + 140, EXEC_Y + 21],
                [COL_ALU + 148, EXEC_Y + 21],
                [COL_ALU + 148, EXEC_Y + 83],
                [COL_WB - 15,   EXEC_Y + 83],
                [COL_WB - 15,   EXEC_Y + 102],
                [COL_WB,        EXEC_Y + 102],
            ],
        },
        {
            from: 'fetch.pc4_out', to: 'wb.pc4_in', style: 'data', layer: 'data',
            path: [
                [COL1 + 110, FRONTEND_Y + 36],
                [166,        FRONTEND_Y + 36],
                [166,        EXEC_Y + 128],
                [COL_WB,     EXEC_Y + 128],
            ],
        },
        {
            from: 'decode.wb_sel', to: 'wb.sel', style: 'control', label: 'wb_sel', layer: 'control',
            path: [
                [510, FRONTEND_Y + 62],
                [558, FRONTEND_Y + 62],
                [558, EXEC_Y + 131],
                [COL_WB + 120, EXEC_Y + 131],
            ],
        },

        // ---------------------------------------------------------------- //
        //  ALU Mux (OoO path: RS operands feed mux → ALU)                  //
        // ---------------------------------------------------------------- //
        {
            from: 'regfile.rs1_data', to: 'alu_mux.rs1_data', style: 'data',
            bus: 'execute', layer: 'data',
            path: [
                [COL_REGFILE + 77, COMMIT_Y],
                [COL_REGFILE + 77, 572],
                [COL_ALU_MUX - 15, 572],
                [COL_ALU_MUX - 15, EXEC_Y + 24],
                [COL_ALU_MUX,      EXEC_Y + 24],
            ],
        },
        {
            from: 'regfile.rs2_data', to: 'alu_mux.rs2_data', style: 'data',
            bus: 'execute', layer: 'data',
            path: [
                [COL_REGFILE + 105, COMMIT_Y],
                [COL_REGFILE + 105, 577],
                [COL_ALU_MUX - 20,  577],
                [COL_ALU_MUX - 20,  EXEC_Y + 37],
                [COL_ALU_MUX,       EXEC_Y + 37],
            ],
        },
        {
            from: 'fetch.pc_out', to: 'alu_mux.pc', style: 'data',
            bus: 'execute', layer: 'data',
            path: [
                [COL1 + 110, FRONTEND_Y + 19],
                [168,        FRONTEND_Y + 19],
                [168,        EXEC_Y + 3],
                [COL_ALU_MUX + 14, EXEC_Y + 3],
                [COL_ALU_MUX + 14, EXEC_Y + 10],
            ],
        },
        {
            from: 'regfile.rs2_data', to: 'dmem.wdata', style: 'data', label: 'wdata', layer: 'data',
            path: [
                [COL_REGFILE + 105, COMMIT_Y],
                [COL_REGFILE + 105, 581],
                [COL_DMEM - 10,     581],
                [COL_DMEM - 10,     EXEC_Y + 33],
                [COL_DMEM,          EXEC_Y + 33],
            ],
        },
    ];

    // ================================================================== //
    //  Annotations                                                         //
    // ================================================================== //
    const annotations = [
        {
            type: 'label', x: W / 2, y: BPRED_Y + 2,
            text: 'Out-of-Order Execution',
            color: '#e0e0e6', fontSize: '16px', fontWeight: '700', anchor: 'middle',
        },
        {
            type: 'dashed_box',
            x: COL1 - 10, y: FRONTEND_Y - 10, w: COL3 + 140 - COL1 + 20, h: 85,
            text: 'Frontend (in-order)', color: '#3b82f6',
        },
        {
            type: 'dashed_box',
            x: COL4 - 10, y: OOO_Y - 15, w: COL5 + 160 - COL4 + 20, h: 110,
            text: 'Issue (rename + dispatch)', color: '#fb923c',
        },
        {
            type: 'dashed_box',
            x: COL_ALU_MUX - 10, y: EXEC_Y - 15, w: 320, h: 90,
            text: 'Execution', color: '#a78bfa',
        },
        {
            type: 'dashed_box',
            x: COL_ROB - 10, y: COMMIT_Y - 10, w: COL_REGFILE + 150 - COL_ROB + 20, h: 100,
            text: 'Commit (in-order retire)', color: '#fb923c',
        },
        {
            type: 'label', x: COL_ALU + 170, y: EXEC_Y + 85,
            text: 'Common Data Bus (CDB)', color: '#fb923c', fontSize: '9px',
        },
    ];

    return { width: W, height: H, components, wires, annotations, stages: [], collapseBuses: true };
}

window.getOoOLayout = getOoOLayout;
