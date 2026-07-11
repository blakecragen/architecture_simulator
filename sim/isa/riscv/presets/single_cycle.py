"""
RISC-V single-cycle preset.

Assembles a complete single-cycle RISC-V CPU from shared components
and the ISA-specific decoder. Every component is independently swappable.

When ``cycle_costs`` is provided (the "Configurable" model), the exact same
combinational datapath is reused, but a CycleBudgetController holds each
instruction for a per-class number of cycles and gates the register write,
memory write, and PC redirect so they fire only on the instruction's final
cycle. The committed effect is identical to single-cycle (so results still match
the oracle) — only the cycle COUNT changes. ``cycle_costs=None`` (the default)
is byte-for-byte the classic single-cycle machine.
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
from sim.components.multicycle.budget_controller import CycleBudgetController
from sim.components.multicycle.gate import GatedSignal
from sim.isa.riscv.decoder_component import RISCVDecoder


def build(
    program: list[int],
    branch_predictor=None,
    dmem=None,
    alu=None,
    cycle_costs=None,
):
    if branch_predictor is None:
        branch_predictor = NoPrediction()
    if dmem is None:
        dmem = DataMemory()
    if alu is None:
        alu = StandardALU()

    configurable = cycle_costs is not None
    b = CPUBuilder()

    # ── Add components ────────────────────────────────────────────
    b.add("fetch",    SimpleFetch(pc_reset=0))
    b.add("imem",     InstructionMemory(program))
    b.add("decode",   RISCVDecoder())
    b.add("regfile",  StandardRegisterFile(num_regs=32, zero_reg=True))
    b.add("alu_mux",  AluInputMux())
    b.add("alu",      alu)
    b.add("branch",   BranchResolutionUnit())
    b.add("bpred",    branch_predictor)
    b.add("dmem",     dmem)
    b.add("wb",       WritebackUnit())
    if configurable:
        b.add("cyc_ctrl",     CycleBudgetController(costs=cycle_costs))
        b.add("gate_reg_wen", GatedSignal(ui_label="Gate RegW"))
        b.add("gate_mem_wen", GatedSignal(ui_label="Gate MemW"))
        b.add("gate_branch",  GatedSignal(ui_label="Gate Branch"))

    # ── Evaluation order (dataflow order) ─────────────────────────
    order = ["fetch", "imem", "decode"]
    if configurable:
        order.append("cyc_ctrl")
    order += ["regfile", "alu_mux", "alu", "dmem", "wb", "branch"]
    if configurable:
        order += ["gate_reg_wen", "gate_mem_wen", "gate_branch"]
    order.append("bpred")
    b.set_eval_order(order)

    # ── Fetch → Instruction Memory ────────────────────────────────
    b.wire("fetch.pc_out",      "imem.addr")

    # ── Instruction Memory → Decoder ──────────────────────────────
    b.wire("imem.data",         "decode.instr_in")

    # ── Decoder → Register File (read addresses) ──────────────────
    b.wire("decode.rs1",        "regfile.rs1_addr")
    b.wire("decode.rs2",        "regfile.rs2_addr")

    # ── ALU Input Mux ─────────────────────────────────────────────
    b.wire("regfile.rs1_data",  "alu_mux.rs1_data")
    b.wire("regfile.rs2_data",  "alu_mux.rs2_data")
    b.wire("fetch.pc_out",      "alu_mux.pc")
    b.wire("decode.imm",        "alu_mux.imm")
    b.wire("decode.use_pc",     "alu_mux.use_pc")
    b.wire("decode.alu_src",    "alu_mux.alu_src")

    # ── ALU ───────────────────────────────────────────────────────
    b.wire("alu_mux.alu_a",     "alu.a")
    b.wire("alu_mux.alu_b",     "alu.b")
    b.wire("decode.alu_op",     "alu.op")

    # ── Data Memory ───────────────────────────────────────────────
    b.wire("alu.result",        "dmem.addr")
    b.wire("regfile.rs2_data",  "dmem.wdata")

    # ── Writeback Mux ─────────────────────────────────────────────
    b.wire("alu.result",        "wb.alu_in")
    b.wire("dmem.rdata",        "wb.mem_in")
    b.wire("fetch.pc4_out",     "wb.pc4_in")
    b.wire("decode.wb_sel",     "wb.sel")

    # ── Writeback → Register File (write port) ────────────────────
    b.wire("decode.rd",         "regfile.rd_addr")
    b.wire("wb.data_out",       "regfile.rd_data")

    # ── Branch Resolution ─────────────────────────────────────────
    b.wire("fetch.pc_out",      "branch.pc")
    b.wire("fetch.pc4_out",     "branch.pc4")
    b.wire("decode.imm",        "branch.imm")
    b.wire("regfile.rs1_data",  "branch.rs1_data")
    b.wire("decode.branch",     "branch.branch")
    b.wire("decode.branch_cond","branch.branch_cond")
    b.wire("decode.jal",        "branch.jal")
    b.wire("decode.jalr",       "branch.jalr")
    b.wire("alu.zero",          "branch.alu_zero")
    b.wire("alu.result",        "branch.alu_result")
    b.wire("branch.next_pc",    "fetch.next_pc")

    if not configurable:
        # Classic single-cycle: commit + advance every cycle.
        b.wire("decode.mem_write",     "dmem.wen")
        b.wire("decode.reg_write",     "regfile.wen")
        b.wire("branch.branch_taken",  "fetch.branch_taken")
    else:
        # Configurable: hold each instruction for its per-class budget; commit
        # (writes + PC redirect) only on its final cycle, stall the PC until then.
        b.wire("decode.mem_read",   "cyc_ctrl.mem_read")
        b.wire("decode.mem_write",  "cyc_ctrl.mem_write")
        b.wire("decode.branch",     "cyc_ctrl.branch")
        b.wire("decode.jal",        "cyc_ctrl.jal")
        b.wire("decode.jalr",       "cyc_ctrl.jalr")
        b.wire("cyc_ctrl.stall",    "fetch.stall")
        b.wire("decode.mem_write",  "gate_mem_wen.a")
        b.wire("cyc_ctrl.commit",   "gate_mem_wen.b")
        b.wire("gate_mem_wen.out",  "dmem.wen")
        b.wire("decode.reg_write",  "gate_reg_wen.a")
        b.wire("cyc_ctrl.commit",   "gate_reg_wen.b")
        b.wire("gate_reg_wen.out",  "regfile.wen")
        b.wire("branch.branch_taken", "gate_branch.a")
        b.wire("cyc_ctrl.commit",     "gate_branch.b")
        b.wire("gate_branch.out",     "fetch.branch_taken")

    # ── Branch Predictor (informational in single-cycle) ──────────
    b.wire("fetch.pc_out",         "bpred.pc")
    b.wire("decode.branch",        "bpred.is_branch")
    b.wire("decode.branch",        "bpred.update_en")
    b.wire("branch.branch_taken",  "bpred.actual")

    return b.build()
