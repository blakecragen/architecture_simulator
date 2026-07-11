"""
RISC-V N-wide superscalar pipeline preset.

Extends the 5-stage pipeline with N parallel lanes. Each lane has its own
decoder, ALU mux, ALU, and writeback unit. The register file, data memory,
and branch resolution are shared. Pipeline registers carry N contexts.

Cross-lane hazard detection squashes dependent lanes within a fetch group.
Wide forwarding resolves EX→EX and MEM→EX hazards across all lanes.
"""
from sim.component.wire import CPUBuilder
from sim.components.superscalar.superscalar_fetch import SuperscalarFetch
from sim.components.superscalar.wide_imem import WideInstructionMemory
from sim.components.superscalar.wide_regfile import WideRegisterFile
from sim.components.superscalar.cross_lane_hazard import CrossLaneHazardDetector
from sim.components.superscalar.wide_forwarding import WideForwardingUnit
from sim.components.superscalar.wide_pipeline_regs import (
    WideIF_ID, WideID_EX, WideEX_MEM, WideMEM_WB,
)
from sim.components.alu.standard import StandardALU
from sim.components.alu.input_mux import AluInputMux
from sim.components.branch.unit import BranchResolutionUnit
from sim.components.branch.predictors.no_predict import NoPrediction
from sim.components.memory.dmem import MultiPortDataMemory
from sim.components.writeback.standard import WritebackUnit
from sim.isa.riscv.decoder_component import RISCVDecoder


def build(program: list[int], num_lanes: int = 2, branch_predictor=None,
          dmem=None):
    if branch_predictor is None:
        branch_predictor = NoPrediction()
    if dmem is None:
        dmem = MultiPortDataMemory(num_lanes=num_lanes)

    NOP = 0x00000013
    b = CPUBuilder()

    # ── Shared components ──────────────────────────────────────────
    b.add("fetch",      SuperscalarFetch(num_lanes=num_lanes, pc_reset=0))
    b.add("imem",       WideInstructionMemory(program, num_lanes=num_lanes))
    b.add("if_id",      WideIF_ID(num_lanes=num_lanes, nop_encoding=NOP))
    b.add("regfile",    WideRegisterFile(num_regs=32, zero_reg=True, num_lanes=num_lanes))
    b.add("hazard_det", CrossLaneHazardDetector(num_lanes=num_lanes))
    b.add("id_ex",      WideID_EX(num_lanes=num_lanes))
    b.add("forwarding", WideForwardingUnit(num_lanes=num_lanes))
    b.add("ex_mem",     WideEX_MEM(num_lanes=num_lanes))
    b.add("dmem",       dmem)
    b.add("mem_wb",     WideMEM_WB(num_lanes=num_lanes))
    b.add("branch",     BranchResolutionUnit())
    b.add("bpred",      branch_predictor)

    # ── Per-lane components ────────────────────────────────────────
    for i in range(num_lanes):
        b.add(f"decode_{i}",  RISCVDecoder())
        b.add(f"alu_mux_{i}", AluInputMux())
        b.add(f"alu_{i}",     StandardALU())
        b.add(f"wb_{i}",      WritebackUnit())

    # ── Evaluation order ───────────────────────────────────────────
    # Pipeline registers first, then stages in dataflow order
    eval_order = ["if_id", "id_ex", "ex_mem", "mem_wb"]

    # WB stage (all lanes)
    for i in range(num_lanes):
        eval_order.append(f"wb_{i}")

    # IF stage
    eval_order.extend(["fetch", "imem"])

    # ID stage (all lanes)
    for i in range(num_lanes):
        eval_order.append(f"decode_{i}")
    eval_order.extend(["regfile", "hazard_det"])

    # EX stage
    eval_order.append("forwarding")
    for i in range(num_lanes):
        eval_order.extend([f"alu_mux_{i}", f"alu_{i}"])

    # MEM stage
    eval_order.extend(["branch", "dmem", "bpred"])

    b.set_eval_order(eval_order)

    # ── IF stage wiring ────────────────────────────────────────────
    b.wire("fetch.pc_out", "imem.addr")

    # ── IF/ID register wiring ──────────────────────────────────────
    for i in range(num_lanes):
        b.wire(f"fetch.pc_lane_{i}", f"if_id.pc_in_{i}")
        # PC+4 for each lane = lane PC + 4
        b.wire(f"fetch.pc4_lane_{i}", f"if_id.pc4_in_{i}")
        b.wire(f"imem.data_{i}",     f"if_id.instr_in_{i}")
        # All lanes initially valid (hazard detector may squash)
        b.wire(f"hazard_det.lane_valid_{i}", f"if_id.lane_valid_in_{i}")

    b.wire("hazard_det.stall", "if_id.stall")
    b.wire("hazard_det.partial_squash", "if_id.partial_squash")

    # ── ID stage wiring ───────────────────────────────────────────
    for i in range(num_lanes):
        b.wire(f"if_id.instr_out_{i}", f"decode_{i}.instr_in")
        b.wire(f"decode_{i}.rs1", f"regfile.rs1_addr_{i}")
        b.wire(f"decode_{i}.rs2", f"regfile.rs2_addr_{i}")

    # ── Hazard detection wiring ────────────────────────────────────
    for i in range(num_lanes):
        b.wire(f"decode_{i}.rd",        f"hazard_det.rd_{i}")
        b.wire(f"decode_{i}.rs1",       f"hazard_det.rs1_{i}")
        b.wire(f"decode_{i}.rs2",       f"hazard_det.rs2_{i}")
        b.wire(f"decode_{i}.reg_write", f"hazard_det.reg_write_{i}")
        b.wire(f"decode_{i}.mem_read",  f"hazard_det.mem_read_{i}")
        b.wire(f"decode_{i}.mem_write", f"hazard_det.mem_write_{i}")
        b.wire(f"decode_{i}.branch",    f"hazard_det.branch_{i}")
        b.wire(f"decode_{i}.jal",       f"hazard_det.jal_{i}")
        b.wire(f"decode_{i}.jalr",      f"hazard_det.jalr_{i}")
        b.wire(f"decode_{i}.alu_src",   f"hazard_det.alu_src_{i}")
        b.wire(f"id_ex.mem_read_out_{i}", f"hazard_det.id_ex_mem_read_{i}")
        b.wire(f"id_ex.rd_out_{i}",      f"hazard_det.id_ex_rd_{i}")

    # ── ID/EX register wiring ─────────────────────────────────────
    b.wire("hazard_det.stall", "id_ex.stall")
    for i in range(num_lanes):
        b.wire(f"if_id.pc_out_{i}",      f"id_ex.pc_in_{i}")
        b.wire(f"if_id.pc4_out_{i}",     f"id_ex.pc4_in_{i}")
        b.wire(f"regfile.rs1_data_{i}",  f"id_ex.rs1_data_in_{i}")
        b.wire(f"regfile.rs2_data_{i}",  f"id_ex.rs2_data_in_{i}")
        b.wire(f"decode_{i}.imm",        f"id_ex.imm_in_{i}")
        b.wire(f"decode_{i}.rs1",        f"id_ex.rs1_addr_in_{i}")
        b.wire(f"decode_{i}.rs2",        f"id_ex.rs2_addr_in_{i}")
        b.wire(f"decode_{i}.rd",         f"id_ex.rd_in_{i}")
        b.wire(f"decode_{i}.alu_op",     f"id_ex.alu_op_in_{i}")
        b.wire(f"decode_{i}.alu_src",    f"id_ex.alu_src_in_{i}")
        b.wire(f"decode_{i}.use_pc",     f"id_ex.use_pc_in_{i}")
        b.wire(f"decode_{i}.mem_read",   f"id_ex.mem_read_in_{i}")
        b.wire(f"decode_{i}.mem_write",  f"id_ex.mem_write_in_{i}")
        b.wire(f"decode_{i}.reg_write",  f"id_ex.reg_write_in_{i}")
        b.wire(f"decode_{i}.branch",     f"id_ex.branch_in_{i}")
        b.wire(f"decode_{i}.branch_cond", f"id_ex.branch_cond_in_{i}")
        b.wire(f"decode_{i}.jal",        f"id_ex.jal_in_{i}")
        b.wire(f"decode_{i}.jalr",       f"id_ex.jalr_in_{i}")
        b.wire(f"decode_{i}.wb_sel",     f"id_ex.wb_sel_in_{i}")
        b.wire(f"hazard_det.lane_valid_{i}", f"id_ex.lane_valid_in_{i}")

    # ── EX stage: Forwarding ──────────────────────────────────────
    for i in range(num_lanes):
        b.wire(f"id_ex.rs1_addr_out_{i}",  f"forwarding.id_ex_rs1_{i}")
        b.wire(f"id_ex.rs2_addr_out_{i}",  f"forwarding.id_ex_rs2_{i}")
        b.wire(f"id_ex.rs1_data_out_{i}",  f"forwarding.rs1_data_in_{i}")
        b.wire(f"id_ex.rs2_data_out_{i}",  f"forwarding.rs2_data_in_{i}")
        b.wire(f"ex_mem.rd_out_{i}",       f"forwarding.ex_mem_rd_{i}")
        b.wire(f"ex_mem.reg_write_out_{i}",f"forwarding.ex_mem_reg_write_{i}")
        b.wire(f"ex_mem.alu_result_out_{i}",f"forwarding.ex_mem_alu_result_{i}")
        b.wire(f"mem_wb.rd_out_{i}",       f"forwarding.mem_wb_rd_{i}")
        b.wire(f"mem_wb.reg_write_out_{i}",f"forwarding.mem_wb_reg_write_{i}")
        b.wire(f"wb_{i}.data_out",         f"forwarding.mem_wb_data_{i}")

    # ── EX stage: ALU per lane ────────────────────────────────────
    for i in range(num_lanes):
        b.wire(f"forwarding.rs1_data_out_{i}", f"alu_mux_{i}.rs1_data")
        b.wire(f"forwarding.rs2_data_out_{i}", f"alu_mux_{i}.rs2_data")
        b.wire(f"id_ex.pc_out_{i}",           f"alu_mux_{i}.pc")
        b.wire(f"id_ex.imm_out_{i}",          f"alu_mux_{i}.imm")
        b.wire(f"id_ex.use_pc_out_{i}",       f"alu_mux_{i}.use_pc")
        b.wire(f"id_ex.alu_src_out_{i}",      f"alu_mux_{i}.alu_src")
        b.wire(f"alu_mux_{i}.alu_a",          f"alu_{i}.a")
        b.wire(f"alu_mux_{i}.alu_b",          f"alu_{i}.b")
        b.wire(f"id_ex.alu_op_out_{i}",       f"alu_{i}.op")

    # ── EX/MEM register wiring ────────────────────────────────────
    for i in range(num_lanes):
        b.wire(f"alu_{i}.result",                f"ex_mem.alu_result_in_{i}")
        b.wire(f"alu_{i}.zero",                  f"ex_mem.alu_zero_in_{i}")
        b.wire(f"forwarding.rs2_data_out_{i}",   f"ex_mem.rs2_data_in_{i}")
        b.wire(f"id_ex.rd_out_{i}",              f"ex_mem.rd_in_{i}")
        b.wire(f"id_ex.pc_out_{i}",              f"ex_mem.pc_in_{i}")
        b.wire(f"id_ex.pc4_out_{i}",             f"ex_mem.pc4_in_{i}")
        b.wire(f"id_ex.imm_out_{i}",             f"ex_mem.imm_in_{i}")
        b.wire(f"forwarding.rs1_data_out_{i}",   f"ex_mem.rs1_data_in_{i}")
        b.wire(f"id_ex.mem_read_out_{i}",        f"ex_mem.mem_read_in_{i}")
        b.wire(f"id_ex.mem_write_out_{i}",       f"ex_mem.mem_write_in_{i}")
        b.wire(f"id_ex.reg_write_out_{i}",       f"ex_mem.reg_write_in_{i}")
        b.wire(f"id_ex.branch_out_{i}",          f"ex_mem.branch_in_{i}")
        b.wire(f"id_ex.branch_cond_out_{i}",     f"ex_mem.branch_cond_in_{i}")
        b.wire(f"id_ex.jal_out_{i}",             f"ex_mem.jal_in_{i}")
        b.wire(f"id_ex.jalr_out_{i}",            f"ex_mem.jalr_in_{i}")
        b.wire(f"id_ex.wb_sel_out_{i}",          f"ex_mem.wb_sel_in_{i}")

    # ── MEM stage: Branch resolution (from lane 0 only — simplified) ──
    b.wire("ex_mem.pc_out_0",          "branch.pc")
    b.wire("ex_mem.pc4_out_0",         "branch.pc4")
    b.wire("ex_mem.imm_out_0",         "branch.imm")
    b.wire("ex_mem.rs1_data_out_0",    "branch.rs1_data")
    b.wire("ex_mem.branch_out_0",      "branch.branch")
    b.wire("ex_mem.branch_cond_out_0", "branch.branch_cond")
    b.wire("ex_mem.jal_out_0",         "branch.jal")
    b.wire("ex_mem.jalr_out_0",        "branch.jalr")
    b.wire("ex_mem.alu_zero_out_0",    "branch.alu_zero")
    b.wire("ex_mem.alu_result_out_0",  "branch.alu_result")

    # Branch → Fetch + flush (misprediction only)
    b.wire("branch.next_pc",       "fetch.next_pc")
    b.wire("branch.mispredict",    "fetch.branch_taken")
    b.wire("hazard_det.stall",     "fetch.stall")
    b.wire("hazard_det.partial_squash", "fetch.partial_squash")
    b.wire("hazard_det.squash_from", "fetch.squash_from")
    b.wire("branch.mispredict",    "if_id.flush")
    b.wire("branch.mispredict",    "id_ex.flush")
    b.wire("branch.mispredict",    "ex_mem.flush")

    # ── MEM stage: Data memory (multi-port — every lane has its own port) ──
    for i in range(num_lanes):
        b.wire(f"ex_mem.alu_result_out_{i}",  f"dmem.addr_{i}")
        b.wire(f"ex_mem.rs2_data_out_{i}",    f"dmem.wdata_{i}")
        b.wire(f"ex_mem.mem_read_out_{i}",    f"dmem.mem_read_{i}")
        b.wire(f"ex_mem.mem_write_out_{i}",   f"dmem.mem_write_{i}")

    # ── MEM/WB register wiring ────────────────────────────────────
    for i in range(num_lanes):
        b.wire(f"ex_mem.alu_result_out_{i}", f"mem_wb.alu_result_in_{i}")
        # Each lane reads its own port's data (evaluated after ex_mem drives the
        # addresses this cycle), so a load's value aligns with its control. The
        # multi-port memory forwards older same-group stores into these reads.
        b.wire(f"dmem.rdata_{i}",            f"mem_wb.mem_data_in_{i}")
        b.wire(f"ex_mem.rd_out_{i}",         f"mem_wb.rd_in_{i}")
        b.wire(f"ex_mem.pc_out_{i}",         f"mem_wb.pc_in_{i}")
        b.wire(f"ex_mem.pc4_out_{i}",        f"mem_wb.pc4_in_{i}")
        b.wire(f"ex_mem.reg_write_out_{i}",  f"mem_wb.reg_write_in_{i}")
        b.wire(f"ex_mem.wb_sel_out_{i}",     f"mem_wb.wb_sel_in_{i}")

    # ── Valid chain (propagate valid bit through pipeline) ────────
    for i in range(num_lanes):
        b.wire(f"if_id.valid_{i}",   f"id_ex.valid_in_{i}")
        b.wire(f"id_ex.valid_{i}",   f"ex_mem.valid_in_{i}")
        b.wire(f"ex_mem.valid_{i}",  f"mem_wb.valid_in_{i}")

    # ── WB stage ──────────────────────────────────────────────────
    for i in range(num_lanes):
        b.wire(f"mem_wb.alu_result_out_{i}", f"wb_{i}.alu_in")
        b.wire(f"mem_wb.pc4_out_{i}",       f"wb_{i}.pc4_in")
        b.wire(f"mem_wb.wb_sel_out_{i}",    f"wb_{i}.sel")
        b.wire(f"mem_wb.mem_data_out_{i}",  f"wb_{i}.mem_in")

    # Writeback → Register file
    for i in range(num_lanes):
        b.wire(f"mem_wb.rd_out_{i}",        f"regfile.rd_addr_{i}")
        b.wire(f"wb_{i}.data_out",          f"regfile.rd_data_{i}")
        b.wire(f"mem_wb.reg_write_out_{i}", f"regfile.wen_{i}")

    # ── Branch predictor (conditional on prediction stage, lane 0) ──
    if branch_predictor.prediction_stage == "if":
        # IF-stage: INFORMATIONAL ONLY (train + display, no fetch steering) —
        # the simplified superscalar control path (lane-0-only resolution,
        # cross-lane partial squashes, no squash of the same-group slot after
        # a predicted-taken branch) cannot recover from IF-stage speculation,
        # so steering fetch here corrupts architectural state. Resolution
        # redirects exactly as in the no-prediction path, which is correct.
        # (Same policy as the OoO presets, where bpred is informational.)
        b.wire("fetch.pc_out",          "bpred.pc")
        b.wire("branch.is_control",     "bpred.update_en")
        b.wire("ex_mem.pc_out_0",       "bpred.update_pc")
        b.wire("branch.branch_taken",   "bpred.actual")
        b.wire("branch.next_pc",        "bpred.update_target")
    else:
        # ID-stage: reads decoder output, uses predict_flush (1-cycle penalty)
        b.wire("if_id.pc_out_0",        "bpred.pc")
        b.wire("decode_0.branch",       "bpred.is_branch")
        b.wire("decode_0.jal",          "bpred.is_jal")
        b.wire("decode_0.imm",          "bpred.imm")
        b.wire("bpred.prediction",      "fetch.predict_taken")
        b.wire("bpred.predict_target",  "fetch.predict_target")
        b.wire("bpred.prediction",      "if_id.predict_flush")
        b.wire("bpred.prediction",                  "id_ex.predicted_taken_in_0")
        b.wire("id_ex.predicted_taken_out_0",       "ex_mem.predicted_taken_in_0")
        b.wire("ex_mem.predicted_taken_out_0",      "branch.predicted_taken")
        b.wire("ex_mem.branch_out_0",   "bpred.update_en")
        b.wire("ex_mem.pc_out_0",       "bpred.update_pc")
        b.wire("branch.branch_taken",   "bpred.actual")
        b.wire("branch.next_pc",        "bpred.update_target")

    return b.build()
