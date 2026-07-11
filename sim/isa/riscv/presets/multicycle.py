"""
RISC-V multi-cycle (FetDecExe) preset.

Classic FSM-based CPU that executes one instruction across multiple cycles:
  - ALU ops: 3 cycles (Fetch, Decode, Execute+WB)
  - Loads:   4 cycles (Fetch, Decode, Execute, Memory+WB)
  - Stores:  4 cycles (Fetch, Decode, Execute, Memory)
  - Branches: 3 cycles (Fetch, Decode, Execute)

Reuses all single-cycle shared components plus multi-cycle latches
and an FSM controller.
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
from sim.components.multicycle.controller import MultiCycleController
from sim.components.multicycle.latch import Latch
from sim.components.multicycle.pc_latch import PCLatch
from sim.components.multicycle.gate import GatedSignal
from sim.isa.riscv.decoder_component import RISCVDecoder


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
    b.add("fetch",        SimpleFetch(pc_reset=0))
    b.add("imem",         InstructionMemory(program))
    b.add("ir",           Latch(ui_label="IR"))
    b.add("decode",       RISCVDecoder())
    b.add("regfile",      StandardRegisterFile(num_regs=32, zero_reg=True))
    b.add("reg_a",        Latch(ui_label="Reg A"))
    b.add("reg_b",        Latch(ui_label="Reg B"))
    b.add("pc_latch",     PCLatch())
    b.add("alu_mux",      AluInputMux())
    b.add("alu",          alu)
    b.add("alu_out",      Latch(ui_label="ALU Out"))
    b.add("gate_mem_wen", GatedSignal(ui_label="Gate MemW"))
    b.add("dmem",         dmem)
    b.add("wb",           WritebackUnit())
    b.add("gate_reg_wen", GatedSignal(ui_label="Gate RegW"))
    b.add("gate_branch",  GatedSignal(ui_label="Gate Branch"))
    b.add("branch",       BranchResolutionUnit())
    b.add("bpred",        branch_predictor)

    # ── Evaluation order ──────────────────────────────────────────
    b.set_eval_order([
        "mc_ctrl",
        "fetch", "imem",
        "ir",
        "decode", "regfile",
        "reg_a", "reg_b", "pc_latch",
        "alu_mux", "alu", "alu_out",
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
    b.wire("ir.data_out", "decode.instr_in")

    # ── Decoder → Controller (for phase transitions) ─────────────
    b.wire("decode.mem_read",  "mc_ctrl.dec_mem_read")
    b.wire("decode.mem_write", "mc_ctrl.dec_mem_write")
    b.wire("decode.reg_write", "mc_ctrl.dec_reg_write")

    # ── Decoder → Register File (read addresses) ─────────────────
    b.wire("decode.rs1", "regfile.rs1_addr")
    b.wire("decode.rs2", "regfile.rs2_addr")

    # ── Register File → A/B latches ──────────────────────────────
    b.wire("regfile.rs1_data",  "reg_a.data_in")
    b.wire("regfile.rs2_data",  "reg_b.data_in")
    b.wire("mc_ctrl.ab_latch",  "reg_a.enable")
    b.wire("mc_ctrl.ab_latch",  "reg_b.enable")

    # ── PC Latch (captures PC during FETCH for badge display) ────
    b.wire("fetch.pc_out",      "pc_latch.data_in")
    b.wire("mc_ctrl.ir_latch",  "pc_latch.enable")  # same timing as IR

    # ── ALU Input Mux (reads from latched register values) ───────
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

    # ── ALU → ALU output latch ───────────────────────────────────
    b.wire("alu.result",              "alu_out.data_in")
    b.wire("mc_ctrl.alu_out_latch",   "alu_out.enable")

    # ── Gated memory write enable ────────────────────────────────
    b.wire("decode.mem_write",     "gate_mem_wen.a")
    b.wire("mc_ctrl.mem_write_en", "gate_mem_wen.b")

    # ── Data Memory (uses latched ALU result as address) ─────────
    b.wire("alu_out.data_out",  "dmem.addr")
    b.wire("reg_b.data_out",    "dmem.wdata")
    b.wire("gate_mem_wen.out",  "dmem.wen")

    # ── Writeback Mux ────────────────────────────────────────────
    b.wire("alu.result",        "wb.alu_in")
    b.wire("dmem.rdata",        "wb.mem_in")
    b.wire("pc_latch.pc4_out",  "wb.pc4_in")     # link/return PC+4 from the latched instr PC
    b.wire("decode.wb_sel",     "wb.sel")

    # ── Gated register write enable ──────────────────────────────
    b.wire("decode.reg_write",     "gate_reg_wen.a")
    b.wire("mc_ctrl.reg_write_en", "gate_reg_wen.b")

    # ── Writeback → Register File (write port) ───────────────────
    b.wire("decode.rd",         "regfile.rd_addr")
    b.wire("wb.data_out",       "regfile.rd_data")
    b.wire("gate_reg_wen.out",  "regfile.wen")

    # ── Branch Resolution ────────────────────────────────────────
    b.wire("pc_latch.data_out",    "branch.pc")
    b.wire("pc_latch.pc4_out",     "branch.pc4")
    b.wire("decode.imm",           "branch.imm")
    b.wire("reg_a.data_out",       "branch.rs1_data")
    b.wire("decode.branch",        "branch.branch")
    b.wire("decode.branch_cond",   "branch.branch_cond")
    b.wire("decode.jal",           "branch.jal")
    b.wire("decode.jalr",          "branch.jalr")
    b.wire("alu.zero",             "branch.alu_zero")
    b.wire("alu.result",           "branch.alu_result")

    # ── Branch → Fetch (gated: only during EXECUTE phase) ──────
    b.wire("branch.branch_taken",        "gate_branch.a")
    b.wire("mc_ctrl.branch_resolve_en",  "gate_branch.b")
    b.wire("branch.next_pc",       "fetch.next_pc")
    b.wire("gate_branch.out",      "fetch.branch_taken")

    # ── Branch Predictor ─────────────────────────────────────────
    b.wire("fetch.pc_out",         "bpred.pc")
    b.wire("decode.branch",        "bpred.is_branch")
    b.wire("decode.branch",        "bpred.update_en")
    b.wire("gate_branch.out",      "bpred.actual")

    return b.build()
