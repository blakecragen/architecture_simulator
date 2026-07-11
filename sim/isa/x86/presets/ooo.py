"""
x86-32 Out-of-Order execution preset.

Uses X86Fetch (variable-length PC increment), ByteInstructionMemory,
X86Decoder, and a FlagsRegister on top of the OoO infrastructure
(ROB, RS, RAT). Register file is 8 GPRs, no zero register.
"""
from sim.component.wire import CPUBuilder
from sim.components.fetch.x86_fetch import X86Fetch
from sim.components.memory.byte_imem import ByteInstructionMemory
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
from sim.components.multicycle.gate import OrSignal
from sim.components.ooo.pc_operand_select import PcOperandSelect
from sim.components.ooo.cdb_value_select import CdbValueSelect
from sim.isa.x86.decoder_component import X86Decoder


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
    b.add("fetch",     X86Fetch(pc_reset=0))
    b.add("imem",      ByteInstructionMemory(program))
    b.add("decode",    X86Decoder())
    b.add("rat",       RegisterAliasTable(has_zero_reg=False))  # x86 EAX(0) is a real GPR
    b.add("regfile",   StandardRegisterFile(num_regs=8, zero_reg=False, write_through=True))
    b.add("rob",       ReorderBuffer())
    b.add("rs",        ReservationStation())
    b.add("alu_mux",   AluInputMux())
    b.add("alu",       alu)
    b.add("committed_flags", CommittedFlags())  # flags latched at ROB commit (program order)
    b.add("branch",    BranchResolutionUnit(compare_mode="sub", serialized=True))
    b.add("bpred",     branch_predictor)
    b.add("dmem",      dmem)
    b.add("wb",        WritebackUnit())
    b.add("store_commit", StoreCommitUnit())
    b.add("dispatch_gate", OrSignal())   # reg_write OR mem_write
    b.add("flag_gate", OrSignal())       # (reg_write OR mem_write) OR write_flags
    b.add("pc_src", PcOperandSelect())
    b.add("cdb_val", CdbValueSelect())

    # ── Evaluation order ────────────────────────────────────────────
    b.set_eval_order([
        "fetch", "imem", "decode", "dispatch_gate", "flag_gate",
        "rob", "regfile", "store_commit", "committed_flags", "rat", "pc_src", "rs",
        "alu", "alu_mux", "dmem", "cdb_val", "wb",
        "branch", "bpred",
    ])

    # ── Fetch → Instruction Memory ──────────────────────────────────
    b.wire("fetch.pc_out",           "imem.addr")

    # ── Instruction Memory → Decoder ────────────────────────────────
    b.wire("imem.data",              "decode.instr_in")
    b.wire("fetch.pc_out",           "decode.pc_in")

    # ── Decoder → Fetch (instruction length feedback) ───────────────
    b.wire("decode.instr_len",       "fetch.instr_len")

    # ── Decoder → Register File (read addresses) ────────────────────
    b.wire("decode.rs1",             "regfile.rs1_addr")
    b.wire("decode.rs2",             "regfile.rs2_addr")

    # ── RAT lookup (rs1/rs2 rename) ─────────────────────────────────
    b.wire("decode.rs1",             "rat.rs1_arch")
    b.wire("decode.rs2",             "rat.rs2_arch")
    b.wire("decode.rd",              "rat.rd_arch")
    b.wire("decode.reg_write",       "rat.alloc_en")
    b.wire("rob.dispatch_tag",       "rat.alloc_tag")

    # ── Dispatch gate: a ROB/RS entry is allocated for register-writing
    #    OR memory-writing OR flag-setting instructions, so stores
    #    (reg_write=0) and CMP (reg_write=0) also enter the ROB and commit
    #    in program order.  Flag-setters must execute so their flags are
    #    produced; the branch reads them after they commit.
    b.wire("decode.reg_write",       "dispatch_gate.a")
    b.wire("decode.mem_write",       "dispatch_gate.b")
    b.wire("dispatch_gate.out",      "flag_gate.a")
    b.wire("decode.write_flags",     "flag_gate.b")

    # ── ROB dispatch ────────────────────────────────────────────────
    b.wire("flag_gate.out",          "rob.dispatch_en")
    b.wire("decode.reg_write",       "rob.dispatch_reg_write")
    b.wire("decode.write_flags",     "rob.dispatch_write_flags")
    b.wire("decode.rd",              "rob.dispatch_rd")
    b.wire("fetch.pc_out",           "rob.dispatch_pc")
    b.wire("decode.branch",          "rob.dispatch_is_branch")
    b.wire("decode.mem_read",        "rob.dispatch_is_load")
    b.wire("decode.mem_write",       "rob.dispatch_is_store")
    b.wire("decode.rs2",             "rob.dispatch_store_data_reg")

    # ── RS issue (from RAT + regfile) ───────────────────────────────
    b.wire("decode.use_pc",          "pc_src.use_pc")
    b.wire("fetch.pc_out",           "pc_src.pc")
    b.wire("regfile.rs1_data",       "pc_src.reg_val")
    b.wire("rat.rs1_ready",          "pc_src.reg_ready")
    b.wire("rat.rs1_tag",            "pc_src.reg_tag")
    b.wire("flag_gate.out",          "rs.issue_en")
    b.wire("decode.alu_op",          "rs.issue_op")
    b.wire("pc_src.src_ready",       "rs.issue_src1_ready")
    b.wire("pc_src.src_tag",         "rs.issue_src1_tag")
    b.wire("pc_src.src_val",         "rs.issue_src1_val")
    b.wire("rat.rs2_ready",          "rs.issue_src2_ready")
    b.wire("rat.rs2_tag",            "rs.issue_src2_tag")
    b.wire("regfile.rs2_data",       "rs.issue_src2_val")
    b.wire("rob.dispatch_tag",       "rs.issue_rob_tag")
    b.wire("decode.imm",             "rs.issue_imm")
    b.wire("decode.alu_src",         "rs.issue_alu_src")
    b.wire("decode.mem_read",        "rs.issue_is_load")
    # Store->load ordering: loads wait until no older store is uncommitted.
    b.wire("rob.store_pending_mask", "rs.store_mask")
    b.wire("rob.head_ptr",           "rs.rob_head")

    # ── RS → ALU (execution) ───────────────────────────────────────
    # In the OoO model the RS already resolves operand values (including
    # imm via alu_src), so we wire RS outputs directly to the ALU.
    b.wire("rs.exec_src1",           "alu.a")
    b.wire("rs.exec_src2",           "alu.b")
    b.wire("rs.exec_op",             "alu.op")
    # The alu_mux still receives decode signals for non-RS uses
    b.wire("regfile.rs1_data",       "alu_mux.rs1_data")
    b.wire("regfile.rs2_data",       "alu_mux.rs2_data")
    b.wire("fetch.pc_out",           "alu_mux.pc")
    b.wire("decode.imm",             "alu_mux.imm")
    b.wire("decode.use_pc",          "alu_mux.use_pc")
    b.wire("decode.alu_src",         "alu_mux.alu_src")

    # ── CDB: ALU result → RS snoop + ROB complete ──────────────────
    b.wire("rs.exec_valid",          "rob.complete_en")
    b.wire("rs.exec_rob_tag",        "rob.complete_tag")
    b.wire("alu.result",             "rob.complete_value")
    b.wire("dmem.rdata",             "rob.complete_mem_value")
    b.wire("rs.exec_valid",          "rs.cdb_en")
    b.wire("rs.exec_rob_tag",        "rs.cdb_tag")
    # Loads broadcast the memory read result, not the ALU-computed address
    # (same select the ROB applies internally to complete_mem_value).
    b.wire("rs.exec_is_load",             "cdb_val.is_load")
    b.wire("alu.result",                "cdb_val.alu_value")
    b.wire("dmem.rdata",                "cdb_val.mem_value")
    b.wire("cdb_val.value",             "rs.cdb_value")

    # ── ROB commit → Register File ─────────────────────────────────
    b.wire("rob.commit_rd",          "regfile.rd_addr")
    b.wire("rob.commit_value",       "regfile.rd_data")
    b.wire("rob.commit_reg_write",   "regfile.wen")

    # ── ROB commit → RAT (free mapping) ────────────────────────────
    b.wire("rob.commit_reg_write",   "rat.commit_en")
    b.wire("rob.commit_rd",          "rat.commit_rd")
    b.wire("rob.commit_tag",         "rat.commit_tag")

    # ── Committed flags (latched at ROB commit, in program order) ───
    b.wire("rob.commit_write_flags", "committed_flags.commit_write_flags")
    b.wire("rob.commit_value",       "committed_flags.commit_value")

    # ── Branch Resolution (uses committed flags, not raw ALU) ───────
    # The branch is held (fetch stalled) until the ROB drains, so the most
    # recent flag-setter before it has committed and committed_flags is settled.
    b.wire("fetch.pc_out",           "branch.pc")
    b.wire("fetch.pc_plus_len",      "branch.pc4")
    b.wire("decode.imm",             "branch.imm")
    b.wire("regfile.rs1_data",       "branch.rs1_data")
    b.wire("decode.branch",          "branch.branch")
    b.wire("decode.branch_cond",     "branch.branch_cond")
    b.wire("decode.jal",             "branch.jal")
    b.wire("decode.jalr",            "branch.jalr")
    b.wire("committed_flags.zero_out",   "branch.alu_zero")
    b.wire("committed_flags.result_out", "branch.alu_result")
    b.wire("rob.empty",              "branch.rob_empty")
    b.wire("branch.stall",           "fetch.stall")

    # ── Branch → Fetch ──────────────────────────────────────────────
    b.wire("branch.next_pc",         "fetch.next_pc")
    b.wire("branch.branch_taken",    "fetch.branch_taken")

    # ── Flush (from ROB → RS, RAT) ─────────────────────────────────
    b.wire("rob.flush",              "rs.flush")
    b.wire("rob.flush",              "rat.flush")

    # ── Branch Predictor (informational) ────────────────────────────
    b.wire("fetch.pc_out",           "bpred.pc")
    b.wire("decode.branch",          "bpred.is_branch")
    b.wire("decode.branch",          "bpred.update_en")
    b.wire("branch.branch_taken",    "bpred.actual")

    # ── Data Memory ────────────────────────────────────────────────
    # Loads: ALU computes address, dmem reads combinationally via addr
    b.wire("alu.result",             "dmem.addr")
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
    b.wire("alu.result",             "wb.alu_in")
    b.wire("dmem.rdata",             "wb.mem_in")
    b.wire("fetch.pc_plus_len",      "wb.pc4_in")
    b.wire("decode.wb_sel",          "wb.sel")

    return b.build()
