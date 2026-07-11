"""
ARM AArch64 Out-of-Order execution preset.

Same OoO structure as RISC-V, swapping in the ARM decoder and
configuring the register file for 32 regs with zero register at index 31.
"""
from sim.component.wire import CPUBuilder
from sim.components.fetch.simple import SimpleFetch
from sim.components.memory.imem import InstructionMemory
from sim.components.memory.dmem import DataMemory
from sim.components.regfile.standard import StandardRegisterFile
from sim.components.alu.standard import StandardALU
from sim.components.alu.input_mux import AluInputMux
from sim.components.branch.unit import BranchResolutionUnit
from sim.components.branch.predictors.no_predict import NoPrediction
from sim.components.writeback.standard import WritebackUnit
from sim.components.ooo.rob import ReorderBuffer
from sim.components.ooo.reservation_station import ReservationStation
from sim.components.ooo.rat import RegisterAliasTable
from sim.components.ooo.store_commit import StoreCommitUnit
from sim.components.ooo.committed_flags import CommittedFlags
from sim.components.ooo.branch_flag_mux import BranchFlagMux
from sim.components.multicycle.gate import OrSignal, AndNotSignal
from sim.components.ooo.pc_operand_select import PcOperandSelect
from sim.components.ooo.cdb_value_select import CdbValueSelect
from sim.isa.arm.decoder_component import ARMDecoder


def build(
    program: list[int],
    branch_predictor=None,
    dmem=None,
    alu=None,
):
    if branch_predictor is None:
        branch_predictor = NoPrediction()
    if dmem is None:
        dmem = DataMemory()
    if alu is None:
        alu = StandardALU()

    b = CPUBuilder()

    # ── Add components ──────────────────────────────────────────────
    b.add("fetch",   SimpleFetch(pc_reset=0))
    b.add("imem",    InstructionMemory(program))
    b.add("decode",  ARMDecoder())
    b.add("rat",     RegisterAliasTable(zero_reg_index=31))  # ARM XZR is the zero reg
    b.add("regfile", StandardRegisterFile(num_regs=32, zero_reg=True, zero_reg_index=31, write_through=True))
    b.add("rob",     ReorderBuffer())
    b.add("rs",      ReservationStation())
    b.add("alu_mux", AluInputMux())
    b.add("alu",     alu)
    # Dedicated in-order comparator for self-comparing branches (CBNZ/CBZ),
    # which test a register against zero rather than reading prior flags.
    b.add("branch_alu", StandardALU())
    b.add("committed_flags", CommittedFlags())  # flags latched at ROB commit (program order)
    b.add("flag_mux", BranchFlagMux())          # CBNZ/CBZ comparator vs B.cond committed flags
    b.add("branch",  BranchResolutionUnit(compare_mode="sub", serialized=True))
    b.add("bpred",   branch_predictor)
    b.add("dmem",    dmem)
    b.add("wb",      WritebackUnit())
    b.add("store_commit", StoreCommitUnit())
    b.add("dispatch_gate", OrSignal())     # reg_write OR mem_write
    b.add("flagset_gate", AndNotSignal())  # sets_flags AND NOT branch (plain flag-setters only)
    b.add("flag_gate", OrSignal())         # (reg_write OR mem_write) OR plain-flag-setter
    b.add("pc_src", PcOperandSelect())
    b.add("cdb_val", CdbValueSelect())

    # ── Evaluation order ────────────────────────────────────────────
    b.set_eval_order([
        "fetch", "imem", "decode", "dispatch_gate", "flagset_gate", "flag_gate",
        "rob", "regfile", "store_commit", "committed_flags", "rat", "pc_src", "rs",
        "alu", "alu_mux", "branch_alu", "dmem", "cdb_val", "wb",
        "flag_mux", "branch", "bpred",
    ])

    # ── Fetch → Instruction Memory ──────────────────────────────────
    b.wire("fetch.pc_out",      "imem.addr")

    # ── Instruction Memory → Decoder ────────────────────────────────
    b.wire("imem.data",         "decode.instr_in")

    # ── Decoder → Register File (read addresses) ────────────────────
    b.wire("decode.rs1",        "regfile.rs1_addr")
    b.wire("decode.rs2",        "regfile.rs2_addr")

    # ── RAT lookup (rs1/rs2 rename) ─────────────────────────────────
    b.wire("decode.rs1",        "rat.rs1_arch")
    b.wire("decode.rs2",        "rat.rs2_arch")
    b.wire("decode.rd",         "rat.rd_arch")
    b.wire("decode.reg_write",  "rat.alloc_en")
    b.wire("rob.dispatch_tag",  "rat.alloc_tag")

    # ── Dispatch gate: a ROB/RS entry is allocated for register-writing
    #    OR memory-writing OR plain flag-setting (CMP/SUBS) instructions.
    #    Conditional branches (including CBNZ/CBZ, which also set flags) are
    #    NEVER dispatched — they self-resolve, and dispatching a held branch
    #    would re-allocate a ROB entry every stalled cycle.  flagset_gate
    #    isolates plain flag-setters: sets_flags AND NOT branch.
    b.wire("decode.reg_write",  "dispatch_gate.a")
    b.wire("decode.mem_write",  "dispatch_gate.b")
    b.wire("decode.sets_flags", "flagset_gate.a")
    b.wire("decode.branch",     "flagset_gate.b")
    b.wire("dispatch_gate.out", "flag_gate.a")
    b.wire("flagset_gate.out",  "flag_gate.b")

    # ── ROB dispatch ────────────────────────────────────────────────
    b.wire("flag_gate.out",     "rob.dispatch_en")
    b.wire("decode.reg_write",  "rob.dispatch_reg_write")
    b.wire("flagset_gate.out",  "rob.dispatch_write_flags")
    b.wire("decode.rd",         "rob.dispatch_rd")
    b.wire("fetch.pc_out",      "rob.dispatch_pc")
    b.wire("decode.branch",     "rob.dispatch_is_branch")
    b.wire("decode.mem_read",   "rob.dispatch_is_load")
    b.wire("decode.mem_write",  "rob.dispatch_is_store")
    b.wire("decode.rs2",        "rob.dispatch_store_data_reg")

    # ── RS issue (from RAT + regfile) ───────────────────────────────
    b.wire("decode.use_pc",     "pc_src.use_pc")
    b.wire("fetch.pc_out",      "pc_src.pc")
    b.wire("regfile.rs1_data",  "pc_src.reg_val")
    b.wire("rat.rs1_ready",     "pc_src.reg_ready")
    b.wire("rat.rs1_tag",       "pc_src.reg_tag")
    b.wire("flag_gate.out",     "rs.issue_en")
    b.wire("decode.alu_op",     "rs.issue_op")
    b.wire("pc_src.src_ready",  "rs.issue_src1_ready")
    b.wire("pc_src.src_tag",    "rs.issue_src1_tag")
    b.wire("pc_src.src_val",    "rs.issue_src1_val")
    b.wire("rat.rs2_ready",     "rs.issue_src2_ready")
    b.wire("rat.rs2_tag",       "rs.issue_src2_tag")
    b.wire("regfile.rs2_data",  "rs.issue_src2_val")
    b.wire("rob.dispatch_tag",  "rs.issue_rob_tag")
    b.wire("decode.imm",        "rs.issue_imm")
    b.wire("decode.alu_src",    "rs.issue_alu_src")
    b.wire("decode.mem_read",   "rs.issue_is_load")
    # Store->load ordering: loads wait until no older store is uncommitted.
    b.wire("rob.store_pending_mask", "rs.store_mask")
    b.wire("rob.head_ptr",           "rs.rob_head")

    # ── RS → ALU (execution) ───────────────────────────────────────
    # In the OoO model the RS already resolves operand values (including
    # imm via alu_src), so we wire RS outputs directly to the ALU,
    # bypassing the alu_mux.
    b.wire("rs.exec_src1",      "alu.a")
    b.wire("rs.exec_src2",      "alu.b")
    b.wire("rs.exec_op",        "alu.op")
    # The alu_mux still receives decode signals for non-RS uses
    b.wire("regfile.rs1_data",  "alu_mux.rs1_data")
    b.wire("regfile.rs2_data",  "alu_mux.rs2_data")
    b.wire("fetch.pc_out",      "alu_mux.pc")
    b.wire("decode.imm",        "alu_mux.imm")
    b.wire("decode.use_pc",     "alu_mux.use_pc")
    b.wire("decode.alu_src",    "alu_mux.alu_src")

    # ── CDB: ALU result → RS snoop + ROB complete ──────────────────
    b.wire("rs.exec_valid",     "rob.complete_en")
    b.wire("rs.exec_rob_tag",   "rob.complete_tag")
    b.wire("alu.result",        "rob.complete_value")
    b.wire("dmem.rdata",        "rob.complete_mem_value")
    b.wire("rs.exec_valid",     "rs.cdb_en")
    b.wire("rs.exec_rob_tag",   "rs.cdb_tag")
    # Loads broadcast the memory read result, not the ALU-computed address
    # (same select the ROB applies internally to complete_mem_value).
    b.wire("rs.exec_is_load",        "cdb_val.is_load")
    b.wire("alu.result",             "cdb_val.alu_value")
    b.wire("dmem.rdata",             "cdb_val.mem_value")
    b.wire("cdb_val.value",          "rs.cdb_value")

    # ── ROB commit → Register File ─────────────────────────────────
    b.wire("rob.commit_rd",     "regfile.rd_addr")
    b.wire("rob.commit_value",  "regfile.rd_data")
    b.wire("rob.commit_reg_write", "regfile.wen")

    # ── ROB commit → RAT (free mapping) ────────────────────────────
    b.wire("rob.commit_reg_write", "rat.commit_en")
    b.wire("rob.commit_rd",     "rat.commit_rd")
    b.wire("rob.commit_tag",    "rat.commit_tag")

    # ── Committed flags (latched at ROB commit, in program order) ───
    b.wire("rob.commit_write_flags", "committed_flags.commit_write_flags")
    b.wire("rob.commit_value",       "committed_flags.commit_value")

    # ── Self-comparing branch comparator (CBNZ/CBZ: reg vs zero) ────
    # Fed by the (serialized, settled) register file via alu_mux.
    b.wire("alu_mux.alu_a",     "branch_alu.a")
    b.wire("alu_mux.alu_b",     "branch_alu.b")
    b.wire("decode.alu_op",     "branch_alu.op")

    # ── Branch flag-source mux: CBNZ/CBZ comparator vs B.cond flags ─
    b.wire("decode.sets_flags",          "flag_mux.select")
    b.wire("branch_alu.zero",            "flag_mux.a_zero")
    b.wire("branch_alu.result",          "flag_mux.a_result")
    b.wire("committed_flags.zero_out",   "flag_mux.b_zero")
    b.wire("committed_flags.result_out", "flag_mux.b_result")

    # ── Branch Resolution ───────────────────────────────────────────
    # The branch is held (fetch stalled) until the ROB drains, so the most
    # recent flag-setter before it has committed (B.cond) and the register
    # operands are settled (CBNZ/CBZ).
    b.wire("fetch.pc_out",      "branch.pc")
    b.wire("fetch.pc4_out",     "branch.pc4")
    b.wire("decode.imm",        "branch.imm")
    b.wire("regfile.rs1_data",  "branch.rs1_data")
    b.wire("decode.branch",     "branch.branch")
    b.wire("decode.branch_cond","branch.branch_cond")
    b.wire("decode.jal",        "branch.jal")
    b.wire("decode.jalr",       "branch.jalr")
    b.wire("flag_mux.zero_out",   "branch.alu_zero")
    b.wire("flag_mux.result_out", "branch.alu_result")
    b.wire("rob.empty",         "branch.rob_empty")
    b.wire("branch.stall",      "fetch.stall")
    b.wire("branch.next_pc",    "fetch.next_pc")
    b.wire("branch.branch_taken","fetch.branch_taken")

    # ── Flush (from ROB → RS, RAT) ─────────────────────────────────
    b.wire("rob.flush",         "rs.flush")
    b.wire("rob.flush",         "rat.flush")

    # ── Branch Predictor (informational) ────────────────────────────
    b.wire("fetch.pc_out",          "bpred.pc")
    b.wire("decode.branch",         "bpred.is_branch")
    b.wire("decode.branch",         "bpred.update_en")
    b.wire("branch.branch_taken",   "bpred.actual")

    # ── Data Memory ────────────────────────────────────────────────
    # Loads: ALU computes address, dmem reads combinationally via addr
    b.wire("alu.result",        "dmem.addr")
    # Stores: committed in-order via StoreCommitUnit
    b.wire("rob.commit_en",          "store_commit.commit_en")
    b.wire("rob.commit_is_store",    "store_commit.commit_is_store")
    b.wire("rob.commit_value",       "store_commit.commit_addr")
    b.wire("rob.commit_store_data_reg", "regfile.rs3_addr")
    b.wire("regfile.rs3_data",       "store_commit.commit_data")
    b.wire("store_commit.dmem_waddr", "dmem.waddr")
    b.wire("store_commit.dmem_wdata", "dmem.wdata")
    b.wire("store_commit.dmem_wen",   "dmem.wen")
    b.wire("store_commit.dmem_wen",   "dmem.waddr_valid")

    # ── Writeback Mux ───────────────────────────────────────────────
    b.wire("alu.result",        "wb.alu_in")
    b.wire("dmem.rdata",        "wb.mem_in")
    b.wire("fetch.pc4_out",     "wb.pc4_in")
    b.wire("decode.wb_sel",     "wb.sel")

    return b.build()
