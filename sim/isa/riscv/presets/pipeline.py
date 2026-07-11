"""
RISC-V 5-stage pipeline preset.

Stages: IF → ID → EX → MEM → WB
Pipeline registers between each stage.
Hazard detection (load-use stall) and data forwarding (EX→EX, MEM→EX).
Branch resolution in EX stage with flush on misprediction.
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
from sim.components.pipeline.registers import IF_ID, ID_EX, EX_MEM, MEM_WB
from sim.components.pipeline.hazard_detector import HazardDetector
from sim.components.pipeline.forwarding_unit import ForwardingUnit
from sim.isa.riscv.decoder_component import RISCVDecoder


def build(program: list[int], branch_predictor=None, dmem=None, alu=None):
    if branch_predictor is None:
        branch_predictor = NoPrediction()
    if dmem is None:
        dmem = DataMemory()
    if alu is None:
        alu = StandardALU()

    b = CPUBuilder()

    # ── Components ────────────────────────────────────────────────
    b.add("fetch",       SimpleFetch(pc_reset=0))
    b.add("imem",        InstructionMemory(program))
    b.add("if_id",       IF_ID(nop_encoding=0x00000013))
    b.add("decode",      RISCVDecoder())
    b.add("regfile",     StandardRegisterFile(num_regs=32, zero_reg=True, write_through=True))
    b.add("hazard_det",  HazardDetector())
    b.add("id_ex",       ID_EX())
    b.add("forwarding",  ForwardingUnit())
    b.add("alu_mux",     AluInputMux())
    b.add("alu",         alu)
    b.add("ex_mem",      EX_MEM())
    b.add("branch",      BranchResolutionUnit())
    b.add("dmem",        dmem)
    b.add("mem_wb",      MEM_WB())
    b.add("wb",          WritebackUnit())
    b.add("bpred",       branch_predictor)

    # ── Evaluation order ──────────────────────────────────────────
    # Pipeline registers evaluate first (output latched state), then
    # stages consume those outputs in dataflow order.
    b.set_eval_order([
        "if_id", "id_ex", "ex_mem", "mem_wb", "wb",
        "fetch", "imem",
        "decode", "regfile", "hazard_det",
        "forwarding", "alu_mux", "alu",
        "branch", "dmem", "bpred",
    ])

    # ── IF stage ──────────────────────────────────────────────────
    b.wire("fetch.pc_out",          "imem.addr")

    # ── IF/ID register ────────────────────────────────────────────
    b.wire("fetch.pc_out",          "if_id.pc_in")
    b.wire("fetch.pc4_out",         "if_id.pc4_in")
    b.wire("imem.data",             "if_id.instr_in")
    b.wire("hazard_det.stall",      "if_id.stall")

    # ── ID stage ──────────────────────────────────────────────────
    b.wire("if_id.instr_out",       "decode.instr_in")
    b.wire("decode.rs1",            "regfile.rs1_addr")
    b.wire("decode.rs2",            "regfile.rs2_addr")

    # ── Hazard detection ──────────────────────────────────────────
    b.wire("id_ex.mem_read_out",    "hazard_det.id_ex_mem_read")
    b.wire("id_ex.rd_out",          "hazard_det.id_ex_rd")
    b.wire("decode.rs1",            "hazard_det.if_id_rs1")
    b.wire("decode.rs2",            "hazard_det.if_id_rs2")

    # ── ID/EX register ────────────────────────────────────────────
    b.wire("if_id.pc_out",          "id_ex.pc_in")
    b.wire("if_id.pc4_out",         "id_ex.pc4_in")
    b.wire("regfile.rs1_data",      "id_ex.rs1_data_in")
    b.wire("regfile.rs2_data",      "id_ex.rs2_data_in")
    b.wire("decode.imm",            "id_ex.imm_in")
    b.wire("decode.rs1",            "id_ex.rs1_addr_in")
    b.wire("decode.rs2",            "id_ex.rs2_addr_in")
    b.wire("decode.rd",             "id_ex.rd_in")
    b.wire("decode.alu_op",         "id_ex.alu_op_in")
    b.wire("decode.alu_src",        "id_ex.alu_src_in")
    b.wire("decode.use_pc",         "id_ex.use_pc_in")
    b.wire("decode.mem_read",       "id_ex.mem_read_in")
    b.wire("decode.mem_write",      "id_ex.mem_write_in")
    b.wire("decode.reg_write",      "id_ex.reg_write_in")
    b.wire("decode.branch",         "id_ex.branch_in")
    b.wire("decode.branch_cond",    "id_ex.branch_cond_in")
    b.wire("decode.jal",            "id_ex.jal_in")
    b.wire("decode.jalr",           "id_ex.jalr_in")
    b.wire("decode.wb_sel",         "id_ex.wb_sel_in")
    b.wire("hazard_det.stall",      "id_ex.stall")

    # ── EX stage: Forwarding ──────────────────────────────────────
    b.wire("id_ex.rs1_addr_out",    "forwarding.id_ex_rs1")
    b.wire("id_ex.rs2_addr_out",    "forwarding.id_ex_rs2")
    b.wire("ex_mem.rd_out",         "forwarding.ex_mem_rd")
    b.wire("ex_mem.reg_write_out",  "forwarding.ex_mem_reg_write")
    b.wire("ex_mem.alu_result_out", "forwarding.ex_mem_alu_result")
    b.wire("mem_wb.rd_out",         "forwarding.mem_wb_rd")
    b.wire("mem_wb.reg_write_out",  "forwarding.mem_wb_reg_write")
    b.wire("wb.data_out",           "forwarding.mem_wb_data")
    b.wire("id_ex.rs1_data_out",    "forwarding.rs1_data_in")
    b.wire("id_ex.rs2_data_out",    "forwarding.rs2_data_in")

    # ── EX stage: ALU ─────────────────────────────────────────────
    b.wire("forwarding.rs1_data_out","alu_mux.rs1_data")
    b.wire("forwarding.rs2_data_out","alu_mux.rs2_data")
    b.wire("id_ex.pc_out",          "alu_mux.pc")
    b.wire("id_ex.imm_out",         "alu_mux.imm")
    b.wire("id_ex.use_pc_out",      "alu_mux.use_pc")
    b.wire("id_ex.alu_src_out",     "alu_mux.alu_src")
    b.wire("alu_mux.alu_a",         "alu.a")
    b.wire("alu_mux.alu_b",         "alu.b")
    b.wire("id_ex.alu_op_out",      "alu.op")

    # ── EX/MEM register ──────────────────────────────────────────
    b.wire("alu.result",            "ex_mem.alu_result_in")
    b.wire("alu.zero",              "ex_mem.alu_zero_in")
    b.wire("forwarding.rs2_data_out","ex_mem.rs2_data_in")
    b.wire("id_ex.rd_out",          "ex_mem.rd_in")
    b.wire("id_ex.pc_out",          "ex_mem.pc_in")
    b.wire("id_ex.pc4_out",         "ex_mem.pc4_in")
    b.wire("id_ex.imm_out",         "ex_mem.imm_in")
    b.wire("forwarding.rs1_data_out","ex_mem.rs1_data_in")
    b.wire("id_ex.mem_read_out",    "ex_mem.mem_read_in")
    b.wire("id_ex.mem_write_out",   "ex_mem.mem_write_in")
    b.wire("id_ex.reg_write_out",   "ex_mem.reg_write_in")
    b.wire("id_ex.branch_out",      "ex_mem.branch_in")
    b.wire("id_ex.branch_cond_out", "ex_mem.branch_cond_in")
    b.wire("id_ex.jal_out",         "ex_mem.jal_in")
    b.wire("id_ex.jalr_out",        "ex_mem.jalr_in")
    b.wire("id_ex.wb_sel_out",      "ex_mem.wb_sel_in")

    # ── MEM stage: Branch resolution ──────────────────────────────
    b.wire("ex_mem.pc_out",         "branch.pc")
    b.wire("ex_mem.pc4_out",        "branch.pc4")
    b.wire("ex_mem.imm_out",        "branch.imm")
    b.wire("ex_mem.rs1_data_out",   "branch.rs1_data")
    b.wire("ex_mem.branch_out",     "branch.branch")
    b.wire("ex_mem.branch_cond_out","branch.branch_cond")
    b.wire("ex_mem.jal_out",        "branch.jal")
    b.wire("ex_mem.jalr_out",       "branch.jalr")
    b.wire("ex_mem.alu_zero_out",   "branch.alu_zero")
    b.wire("ex_mem.alu_result_out", "branch.alu_result")

    # Branch → Fetch + flush (misprediction only)
    b.wire("branch.next_pc",        "fetch.next_pc")
    b.wire("branch.mispredict",     "fetch.branch_taken")
    b.wire("hazard_det.stall",      "fetch.stall")
    b.wire("branch.mispredict",     "if_id.flush")
    b.wire("branch.mispredict",     "id_ex.flush")
    b.wire("branch.mispredict",     "ex_mem.flush")

    # ── MEM stage: Data memory ────────────────────────────────────
    b.wire("ex_mem.alu_result_out", "dmem.addr")
    b.wire("ex_mem.rs2_data_out",   "dmem.wdata")
    b.wire("ex_mem.mem_write_out",  "dmem.wen")

    # ── MEM/WB register ──────────────────────────────────────────
    b.wire("ex_mem.alu_result_out", "mem_wb.alu_result_in")
    b.wire("dmem.rdata",            "mem_wb.mem_data_in")
    b.wire("ex_mem.rd_out",         "mem_wb.rd_in")
    b.wire("ex_mem.pc_out",          "mem_wb.pc_in")
    b.wire("ex_mem.pc4_out",        "mem_wb.pc4_in")
    b.wire("ex_mem.reg_write_out",  "mem_wb.reg_write_in")
    b.wire("ex_mem.wb_sel_out",     "mem_wb.wb_sel_in")

    # ── Valid chain (propagate valid bit through pipeline) ────────
    b.wire("if_id.valid",           "id_ex.valid_in")
    b.wire("id_ex.valid",           "ex_mem.valid_in")
    b.wire("ex_mem.valid",          "mem_wb.valid_in")

    # ── WB stage ──────────────────────────────────────────────────
    b.wire("mem_wb.alu_result_out", "wb.alu_in")
    b.wire("mem_wb.mem_data_out",   "wb.mem_in")
    b.wire("mem_wb.pc4_out",        "wb.pc4_in")
    b.wire("mem_wb.wb_sel_out",     "wb.sel")

    # Writeback → Register file
    b.wire("mem_wb.rd_out",         "regfile.rd_addr")
    b.wire("wb.data_out",           "regfile.rd_data")
    b.wire("mem_wb.reg_write_out",  "regfile.wen")

    # ── Branch predictor (conditional on prediction stage) ──────────
    if branch_predictor.prediction_stage == "if":
        # IF-stage: BTB reads fetch PC, no decoder signals, no predict_flush
        b.wire("fetch.pc_out",          "bpred.pc")
        b.wire("bpred.prediction",      "fetch.predict_taken")
        b.wire("bpred.predict_target",  "fetch.predict_target")
        b.wire("bpred.prediction",              "if_id.predicted_taken_in")
        b.wire("if_id.predicted_taken_out",     "id_ex.predicted_taken_in")
        b.wire("id_ex.predicted_taken_out",     "ex_mem.predicted_taken_in")
        b.wire("ex_mem.predicted_taken_out",    "branch.predicted_taken")
        b.wire("branch.is_control",     "bpred.update_en")
        b.wire("ex_mem.pc_out",         "bpred.update_pc")
        b.wire("branch.branch_taken",   "bpred.actual")
        b.wire("branch.next_pc",        "bpred.update_target")
    else:
        # ID-stage: reads decoder output, uses predict_flush (1-cycle penalty)
        b.wire("if_id.pc_out",          "bpred.pc")
        b.wire("decode.branch",         "bpred.is_branch")
        b.wire("decode.jal",            "bpred.is_jal")
        b.wire("decode.imm",            "bpred.imm")
        b.wire("bpred.prediction",      "fetch.predict_taken")
        b.wire("bpred.predict_target",  "fetch.predict_target")
        b.wire("bpred.prediction",      "if_id.predict_flush")
        b.wire("bpred.prediction",              "id_ex.predicted_taken_in")
        b.wire("id_ex.predicted_taken_out",     "ex_mem.predicted_taken_in")
        b.wire("ex_mem.predicted_taken_out",    "branch.predicted_taken")
        b.wire("ex_mem.branch_out",     "bpred.update_en")
        b.wire("ex_mem.pc_out",         "bpred.update_pc")
        b.wire("branch.branch_taken",   "bpred.actual")
        b.wire("branch.next_pc",        "bpred.update_target")

    return b.build()
