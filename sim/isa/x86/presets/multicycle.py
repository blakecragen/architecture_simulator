"""
x86-32 multi-cycle (FetDecExe) preset.

Same multi-cycle structure but with X86Fetch (variable-length),
ByteInstructionMemory, X86Decoder, FlagsRegister, and 8-reg file.
"""
from sim.component.wire import CPUBuilder
from sim.components.fetch.x86_fetch import X86Fetch
from sim.components.memory.byte_imem import ByteInstructionMemory
from sim.components.memory.dmem import DataMemory
from sim.components.regfile.standard import StandardRegisterFile
from sim.components.alu.standard import StandardALU
from sim.components.alu.input_mux import AluInputMux
from sim.components.alu.flags_register import FlagsRegister
from sim.components.branch.unit import BranchResolutionUnit
from sim.components.branch.predictors.no_predict import NoPrediction
from sim.components.writeback.standard import WritebackUnit
from sim.components.multicycle.controller import MultiCycleController
from sim.components.multicycle.latch import Latch
from sim.components.multicycle.pc_latch import PCLatch
from sim.components.multicycle.gate import GatedSignal
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

    # ── Add components ────────────────────────────────────────────
    b.add("mc_ctrl",      MultiCycleController())
    b.add("fetch",        X86Fetch(pc_reset=0))
    b.add("imem",         ByteInstructionMemory(program))
    b.add("predecode",    X86Decoder())  # length-only: gives fetch the CURRENT instr length
    b.add("ir",           Latch(ui_label="IR"))
    b.add("decode",       X86Decoder())
    b.add("regfile",      StandardRegisterFile(num_regs=8, zero_reg=False))
    b.add("reg_a",        Latch(ui_label="Reg A"))
    b.add("reg_b",        Latch(ui_label="Reg B"))
    b.add("pc_latch",     PCLatch())
    b.add("alu_mux",      AluInputMux())
    b.add("alu",          alu)
    b.add("flags_reg",    FlagsRegister())
    b.add("alu_out",      Latch(ui_label="ALU Out"))
    b.add("gate_mem_wen", GatedSignal(ui_label="Gate MemW"))
    b.add("dmem",         dmem)
    b.add("wb",           WritebackUnit())
    b.add("gate_reg_wen", GatedSignal(ui_label="Gate RegW"))
    b.add("gate_branch",  GatedSignal(ui_label="Gate Branch"))
    b.add("branch",       BranchResolutionUnit(compare_mode="sub"))
    b.add("bpred",        branch_predictor)

    # ── Evaluation order ──────────────────────────────────────────
    b.set_eval_order([
        "mc_ctrl",
        "fetch", "imem", "predecode",
        "ir",
        "decode", "regfile",
        "reg_a", "reg_b", "pc_latch",
        "alu_mux", "alu", "flags_reg", "alu_out",
        "gate_mem_wen",
        "dmem", "wb",
        "gate_reg_wen",
        "branch", "gate_branch", "bpred",
    ])

    # ── Controller stalls fetch ──────────────────────────────────
    b.wire("mc_ctrl.fetch_stall", "fetch.stall")

    # ── Fetch → IMem ─────────────────────────────────────────────
    b.wire("fetch.pc_out", "imem.addr")

    # ── IMem → IR latch ──────────────────────────────────────────
    b.wire("imem.data",        "ir.data_in")
    b.wire("mc_ctrl.ir_latch", "ir.enable")

    # ── IR → Decoder ─────────────────────────────────────────────
    b.wire("ir.data_out",      "decode.instr_in")
    b.wire("fetch.pc_out",     "decode.pc_in")

    # ── Predecode → Fetch (length of the CURRENT instruction) ────
    # X86Fetch advances the PC by the instruction length; the real decoder
    # reads the latched IR (one step behind), so a fetch-stage length
    # predecode reading imem directly is needed for variable-length x86.
    b.wire("imem.data",        "predecode.instr_in")
    b.wire("fetch.pc_out",     "predecode.pc_in")
    b.wire("predecode.instr_len", "fetch.instr_len")

    # ── Decoder → Controller ─────────────────────────────────────
    b.wire("decode.mem_read",  "mc_ctrl.dec_mem_read")
    b.wire("decode.mem_write", "mc_ctrl.dec_mem_write")
    b.wire("decode.reg_write", "mc_ctrl.dec_reg_write")

    # ── Decoder → Register File ──────────────────────────────────
    b.wire("decode.rs1", "regfile.rs1_addr")
    b.wire("decode.rs2", "regfile.rs2_addr")

    # ── Register File → A/B latches ──────────────────────────────
    b.wire("regfile.rs1_data",  "reg_a.data_in")
    b.wire("regfile.rs2_data",  "reg_b.data_in")
    b.wire("mc_ctrl.ab_latch",  "reg_a.enable")
    b.wire("mc_ctrl.ab_latch",  "reg_b.enable")

    # ── PC Latch ─────────────────────────────────────────────────
    b.wire("fetch.pc_out",      "pc_latch.data_in")
    b.wire("mc_ctrl.ir_latch",  "pc_latch.enable")

    # ── ALU Input Mux ────────────────────────────────────────────
    b.wire("reg_a.data_out",    "alu_mux.rs1_data")
    b.wire("reg_b.data_out",    "alu_mux.rs2_data")
    b.wire("pc_latch.data_out", "alu_mux.pc")
    b.wire("decode.imm",        "alu_mux.imm")
    b.wire("decode.use_pc",     "alu_mux.use_pc")
    b.wire("decode.alu_src",    "alu_mux.alu_src")

    # ── ALU ──────────────────────────────────────────────────────
    b.wire("alu_mux.alu_a", "alu.a")
    b.wire("alu_mux.alu_b", "alu.b")
    b.wire("decode.alu_op", "alu.op")

    # ── Flags Register (x86) ─────────────────────────────────────
    b.wire("alu.zero",              "flags_reg.alu_zero_in")
    b.wire("alu.result",            "flags_reg.alu_result_in")
    b.wire("decode.write_flags",    "flags_reg.write_flags")

    # ── ALU → ALU output latch ───────────────────────────────────
    b.wire("alu.result",              "alu_out.data_in")
    b.wire("mc_ctrl.alu_out_latch",   "alu_out.enable")

    # ── Gated memory write enable ────────────────────────────────
    b.wire("decode.mem_write",     "gate_mem_wen.a")
    b.wire("mc_ctrl.mem_write_en", "gate_mem_wen.b")

    # ── Data Memory ──────────────────────────────────────────────
    b.wire("alu_out.data_out",  "dmem.addr")
    b.wire("reg_b.data_out",    "dmem.wdata")
    b.wire("gate_mem_wen.out",  "dmem.wen")

    # ── Writeback Mux ────────────────────────────────────────────
    b.wire("alu.result",            "wb.alu_in")
    b.wire("dmem.rdata",            "wb.mem_in")
    # NOTE: this is a DEAD path — X86Decoder never selects WBSel.PC4 (CALL is a
    # plain jump with no link register), so wb never picks pc4_in. Unlike
    # riscv/arm multicycle (which source the link PC+4 from pc_latch.pc4_out),
    # x86 has no link-register need here; fetch.pc_plus_len's stale value is
    # therefore intentionally tolerated. If x86 ever adds a true CALL-with-link
    # (wb_sel=PC4), give PCLatch a length-aware output and rewire this.
    b.wire("fetch.pc_plus_len",     "wb.pc4_in")
    b.wire("decode.wb_sel",         "wb.sel")

    # ── Gated register write enable ──────────────────────────────
    b.wire("decode.reg_write",     "gate_reg_wen.a")
    b.wire("mc_ctrl.reg_write_en", "gate_reg_wen.b")

    # ── Writeback → Register File ────────────────────────────────
    b.wire("decode.rd",         "regfile.rd_addr")
    b.wire("wb.data_out",       "regfile.rd_data")
    b.wire("gate_reg_wen.out",  "regfile.wen")

    # ── Branch Resolution (uses flags register) ──────────────────
    b.wire("pc_latch.data_out",      "branch.pc")
    b.wire("fetch.pc_plus_len",      "branch.pc4")
    b.wire("decode.imm",             "branch.imm")
    b.wire("reg_a.data_out",         "branch.rs1_data")
    b.wire("decode.branch",          "branch.branch")
    b.wire("decode.branch_cond",     "branch.branch_cond")
    b.wire("decode.jal",             "branch.jal")
    b.wire("decode.jalr",            "branch.jalr")
    b.wire("flags_reg.zero_out",     "branch.alu_zero")
    b.wire("flags_reg.result_out",   "branch.alu_result")

    # ── Branch → Fetch (gated: only during EXECUTE phase) ──────
    b.wire("branch.branch_taken",        "gate_branch.a")
    b.wire("mc_ctrl.branch_resolve_en",  "gate_branch.b")
    b.wire("branch.next_pc",       "fetch.next_pc")
    b.wire("gate_branch.out",      "fetch.branch_taken")

    # ── Branch Predictor ─────────────────────────────────────────
    b.wire("fetch.pc_out",          "bpred.pc")
    b.wire("decode.branch",         "bpred.is_branch")
    b.wire("decode.branch",         "bpred.update_en")
    b.wire("gate_branch.out",       "bpred.actual")

    return b.build()
