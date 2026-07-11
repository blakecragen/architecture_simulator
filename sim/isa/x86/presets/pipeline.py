"""x86-32 5-stage pipeline preset. Uses X86Fetch + ByteInstructionMemory + FlagsRegister."""
from sim.component.wire import CPUBuilder
from sim.components.fetch.x86_fetch import X86Fetch
from sim.components.fetch.pc_len_adder import PcLenAdder
from sim.components.memory.byte_imem import ByteInstructionMemory
from sim.components.memory.dmem import DataMemory
from sim.components.regfile.standard import StandardRegisterFile
from sim.components.alu.standard import StandardALU
from sim.components.alu.input_mux import AluInputMux
from sim.components.alu.flags_register import FlagsRegister
from sim.components.branch.unit import BranchResolutionUnit
from sim.components.branch.predictors.no_predict import NoPrediction
from sim.components.writeback.standard import WritebackUnit
from sim.components.pipeline.registers import IF_ID, ID_EX, EX_MEM, MEM_WB
from sim.components.pipeline.hazard_detector import HazardDetector
from sim.components.pipeline.forwarding_unit import ForwardingUnit
from sim.isa.x86.decoder_component import X86Decoder


def build(program: list[int], branch_predictor=None, dmem=None, alu=None):
    if branch_predictor is None:
        branch_predictor = NoPrediction()
    if dmem is None:
        dmem = DataMemory()
    if alu is None:
        alu = StandardALU()

    b = CPUBuilder()

    b.add("fetch",       X86Fetch(pc_reset=0))
    b.add("imem",        ByteInstructionMemory(program))
    b.add("predecode",   X86Decoder())  # length-only: gives fetch the CURRENT instr length
    b.add("pc4_add",     PcLenAdder())   # fall-through addr from the fresh predecode length
    b.add("if_id",       IF_ID(nop_encoding=0x90))
    b.add("decode",      X86Decoder())
    b.add("regfile",     StandardRegisterFile(num_regs=8, zero_reg=False, write_through=True))
    b.add("hazard_det",  HazardDetector())
    b.add("id_ex",       ID_EX())
    b.add("forwarding",  ForwardingUnit(zero_reg_index=None))  # x86 has no zero reg (EAX=0 is real)
    b.add("alu_mux",     AluInputMux())
    b.add("alu",         alu)
    b.add("flags_reg",   FlagsRegister())
    b.add("ex_mem",      EX_MEM())
    b.add("branch",      BranchResolutionUnit(compare_mode="sub"))
    b.add("dmem",        dmem)
    b.add("mem_wb",      MEM_WB())
    b.add("wb",          WritebackUnit())
    b.add("bpred",       branch_predictor)

    b.set_eval_order([
        "if_id", "id_ex", "ex_mem", "mem_wb", "wb",
        "fetch", "imem", "predecode", "pc4_add",
        "decode", "regfile", "hazard_det",
        "forwarding", "alu_mux", "alu", "flags_reg",
        "branch", "dmem", "bpred",
    ])

    # IF stage
    b.wire("fetch.pc_out",           "imem.addr")
    b.wire("fetch.pc_out",           "if_id.pc_in")
    # pc4 (fall-through) = pc + CURRENT instr length, computed by pc4_add AFTER
    # the predecode produces the length (fetch.pc_plus_len would be stale — see
    # PcLenAdder). This feeds mispredict recovery, so it must be exact.
    b.wire("fetch.pc_out",           "pc4_add.pc")
    b.wire("predecode.instr_len",    "pc4_add.len")
    b.wire("pc4_add.out",            "if_id.pc4_in")
    b.wire("imem.data",              "if_id.instr_in")
    b.wire("hazard_det.stall",       "if_id.stall")

    # Predecode: length of the CURRENT instruction, read combinationally from
    # imem. X86Fetch needs the length to advance the PC, but the real decoder
    # is a stage downstream (it sees the previous instruction), so a fetch-stage
    # length predecode is required for correct variable-length x86 fetch.
    b.wire("imem.data",              "predecode.instr_in")
    b.wire("fetch.pc_out",           "predecode.pc_in")
    b.wire("predecode.instr_len",    "fetch.instr_len")

    # ID stage
    b.wire("if_id.instr_out",        "decode.instr_in")
    b.wire("if_id.pc_out",           "decode.pc_in")
    b.wire("decode.rs1",             "regfile.rs1_addr")
    b.wire("decode.rs2",             "regfile.rs2_addr")

    # Hazard detection
    b.wire("id_ex.mem_read_out",     "hazard_det.id_ex_mem_read")
    b.wire("id_ex.rd_out",           "hazard_det.id_ex_rd")
    b.wire("decode.rs1",             "hazard_det.if_id_rs1")
    b.wire("decode.rs2",             "hazard_det.if_id_rs2")

    # ID/EX register
    b.wire("if_id.pc_out",           "id_ex.pc_in")
    b.wire("if_id.pc4_out",          "id_ex.pc4_in")
    b.wire("regfile.rs1_data",       "id_ex.rs1_data_in")
    b.wire("regfile.rs2_data",       "id_ex.rs2_data_in")
    b.wire("decode.imm",             "id_ex.imm_in")
    b.wire("decode.rs1",             "id_ex.rs1_addr_in")
    b.wire("decode.rs2",             "id_ex.rs2_addr_in")
    b.wire("decode.rd",              "id_ex.rd_in")
    b.wire("decode.alu_op",          "id_ex.alu_op_in")
    b.wire("decode.alu_src",         "id_ex.alu_src_in")
    b.wire("decode.use_pc",          "id_ex.use_pc_in")
    b.wire("decode.mem_read",        "id_ex.mem_read_in")
    b.wire("decode.mem_write",       "id_ex.mem_write_in")
    b.wire("decode.reg_write",       "id_ex.reg_write_in")
    b.wire("decode.branch",          "id_ex.branch_in")
    b.wire("decode.branch_cond",     "id_ex.branch_cond_in")
    b.wire("decode.jal",             "id_ex.jal_in")
    b.wire("decode.jalr",            "id_ex.jalr_in")
    b.wire("decode.wb_sel",          "id_ex.wb_sel_in")
    b.wire("decode.write_flags",      "id_ex.write_flags_in")
    b.wire("hazard_det.stall",       "id_ex.stall")

    # EX stage
    b.wire("id_ex.rs1_addr_out",     "forwarding.id_ex_rs1")
    b.wire("id_ex.rs2_addr_out",     "forwarding.id_ex_rs2")
    b.wire("ex_mem.rd_out",          "forwarding.ex_mem_rd")
    b.wire("ex_mem.reg_write_out",   "forwarding.ex_mem_reg_write")
    b.wire("ex_mem.alu_result_out",  "forwarding.ex_mem_alu_result")
    b.wire("mem_wb.rd_out",          "forwarding.mem_wb_rd")
    b.wire("mem_wb.reg_write_out",   "forwarding.mem_wb_reg_write")
    b.wire("wb.data_out",            "forwarding.mem_wb_data")
    b.wire("id_ex.rs1_data_out",     "forwarding.rs1_data_in")
    b.wire("id_ex.rs2_data_out",     "forwarding.rs2_data_in")
    b.wire("forwarding.rs1_data_out","alu_mux.rs1_data")
    b.wire("forwarding.rs2_data_out","alu_mux.rs2_data")
    b.wire("id_ex.pc_out",           "alu_mux.pc")
    b.wire("id_ex.imm_out",          "alu_mux.imm")
    b.wire("id_ex.use_pc_out",       "alu_mux.use_pc")
    b.wire("id_ex.alu_src_out",      "alu_mux.alu_src")
    b.wire("alu_mux.alu_a",          "alu.a")
    b.wire("alu_mux.alu_b",          "alu.b")
    b.wire("id_ex.alu_op_out",       "alu.op")

    # Flags register (latched for the EX-stage instruction via id_ex)
    b.wire("alu.zero",               "flags_reg.alu_zero_in")
    b.wire("alu.result",             "flags_reg.alu_result_in")
    b.wire("id_ex.write_flags_out",  "flags_reg.write_flags")

    # EX/MEM register
    b.wire("alu.result",             "ex_mem.alu_result_in")
    b.wire("alu.zero",               "ex_mem.alu_zero_in")
    b.wire("forwarding.rs2_data_out","ex_mem.rs2_data_in")
    b.wire("id_ex.rd_out",           "ex_mem.rd_in")
    b.wire("id_ex.pc_out",           "ex_mem.pc_in")
    b.wire("id_ex.pc4_out",          "ex_mem.pc4_in")
    b.wire("id_ex.imm_out",          "ex_mem.imm_in")
    b.wire("forwarding.rs1_data_out","ex_mem.rs1_data_in")
    b.wire("id_ex.mem_read_out",     "ex_mem.mem_read_in")
    b.wire("id_ex.mem_write_out",    "ex_mem.mem_write_in")
    b.wire("id_ex.reg_write_out",    "ex_mem.reg_write_in")
    b.wire("id_ex.branch_out",       "ex_mem.branch_in")
    b.wire("id_ex.branch_cond_out",  "ex_mem.branch_cond_in")
    b.wire("id_ex.jal_out",          "ex_mem.jal_in")
    b.wire("id_ex.jalr_out",         "ex_mem.jalr_in")
    b.wire("id_ex.wb_sel_out",       "ex_mem.wb_sel_in")

    # MEM stage
    b.wire("ex_mem.pc_out",          "branch.pc")
    b.wire("ex_mem.pc4_out",         "branch.pc4")
    b.wire("ex_mem.imm_out",         "branch.imm")
    b.wire("ex_mem.rs1_data_out",    "branch.rs1_data")
    b.wire("ex_mem.branch_out",      "branch.branch")
    b.wire("ex_mem.branch_cond_out", "branch.branch_cond")
    b.wire("ex_mem.jal_out",         "branch.jal")
    b.wire("ex_mem.jalr_out",        "branch.jalr")
    # Pipeline the flags WITH the branch: capture the flags visible at the
    # branch's own EX cycle into EX/MEM and resolve from there, so a younger
    # flag-writing instruction in EX cannot clobber the condition while the
    # branch resolves in MEM.
    b.wire("flags_reg.zero_out",     "ex_mem.flags_zero_in")
    b.wire("flags_reg.result_out",   "ex_mem.flags_result_in")
    b.wire("ex_mem.flags_zero_out",  "branch.alu_zero")
    b.wire("ex_mem.flags_result_out","branch.alu_result")
    b.wire("branch.next_pc",         "fetch.next_pc")
    b.wire("branch.mispredict",      "fetch.branch_taken")
    b.wire("hazard_det.stall",       "fetch.stall")
    b.wire("branch.mispredict",      "if_id.flush")
    b.wire("branch.mispredict",      "id_ex.flush")
    b.wire("branch.mispredict",      "ex_mem.flush")
    b.wire("ex_mem.alu_result_out",  "dmem.addr")
    b.wire("ex_mem.rs2_data_out",    "dmem.wdata")
    b.wire("ex_mem.mem_write_out",   "dmem.wen")

    # MEM/WB register
    b.wire("ex_mem.alu_result_out",  "mem_wb.alu_result_in")
    b.wire("dmem.rdata",             "mem_wb.mem_data_in")
    b.wire("ex_mem.rd_out",          "mem_wb.rd_in")
    b.wire("ex_mem.pc_out",          "mem_wb.pc_in")
    b.wire("ex_mem.pc4_out",         "mem_wb.pc4_in")
    b.wire("ex_mem.reg_write_out",   "mem_wb.reg_write_in")
    b.wire("ex_mem.wb_sel_out",      "mem_wb.wb_sel_in")

    # ── Valid chain (propagate valid bit through pipeline) ────────
    b.wire("if_id.valid",            "id_ex.valid_in")
    b.wire("id_ex.valid",            "ex_mem.valid_in")
    b.wire("ex_mem.valid",           "mem_wb.valid_in")

    # WB stage
    b.wire("mem_wb.alu_result_out",  "wb.alu_in")
    b.wire("mem_wb.mem_data_out",    "wb.mem_in")
    b.wire("mem_wb.pc4_out",         "wb.pc4_in")
    b.wire("mem_wb.wb_sel_out",      "wb.sel")
    b.wire("mem_wb.rd_out",          "regfile.rd_addr")
    b.wire("wb.data_out",            "regfile.rd_data")
    b.wire("mem_wb.reg_write_out",   "regfile.wen")

    # ── Branch predictor (conditional on prediction stage) ──────────
    if branch_predictor.prediction_stage == "if":
        # IF-stage: BTB reads fetch PC, no decoder signals, no predict_flush
        b.wire("fetch.pc_out",           "bpred.pc")
        b.wire("bpred.prediction",       "fetch.predict_taken")
        b.wire("bpred.predict_target",   "fetch.predict_target")
        b.wire("bpred.prediction",               "if_id.predicted_taken_in")
        b.wire("if_id.predicted_taken_out",      "id_ex.predicted_taken_in")
        b.wire("id_ex.predicted_taken_out",      "ex_mem.predicted_taken_in")
        b.wire("ex_mem.predicted_taken_out",     "branch.predicted_taken")
        b.wire("branch.is_control",      "bpred.update_en")
        b.wire("ex_mem.pc_out",          "bpred.update_pc")
        b.wire("branch.branch_taken",    "bpred.actual")
        b.wire("branch.next_pc",         "bpred.update_target")
    else:
        # ID-stage: reads decoder output, uses predict_flush (1-cycle penalty)
        b.wire("if_id.pc_out",           "bpred.pc")
        b.wire("decode.branch",          "bpred.is_branch")
        b.wire("decode.jal",             "bpred.is_jal")
        b.wire("decode.imm",             "bpred.imm")
        b.wire("bpred.prediction",       "fetch.predict_taken")
        b.wire("bpred.predict_target",   "fetch.predict_target")
        b.wire("bpred.prediction",       "if_id.predict_flush")
        b.wire("bpred.prediction",               "id_ex.predicted_taken_in")
        b.wire("id_ex.predicted_taken_out",      "ex_mem.predicted_taken_in")
        b.wire("ex_mem.predicted_taken_out",     "branch.predicted_taken")
        b.wire("ex_mem.branch_out",      "bpred.update_en")
        b.wire("ex_mem.pc_out",          "bpred.update_pc")
        b.wire("branch.branch_taken",    "bpred.actual")
        b.wire("branch.next_pc",         "bpred.update_target")

    return b.build()
