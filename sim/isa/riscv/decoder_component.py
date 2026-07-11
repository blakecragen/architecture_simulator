"""
RISC-V RV32I instruction decoder — pure Python ComponentBase implementation.

This is the primary hot-swap point between ISAs. ARM / x86 decoders expose
identical output ports but parse different instruction encodings. The execution
model (single cycle, pipeline, OoO) never needs to change.
"""
from sim.component.base import ComponentBase, Port, sign_extend
from sim.core.signals import AluOp, WBSel, BranchCond, ALU_OP_NAMES
from .constants import Opcode, Funct3, Funct7


class RISCVDecoder(ComponentBase):
    name = "riscv_decoder"
    ui_label = "RISC-V Decoder"
    ui_category = "decode"
    ports_spec = {
        "instr_in":    Port(32, "in",  "Instruction word"),
        "opcode":      Port(7,  "out", "Opcode field"),
        "rd":          Port(5,  "out", "Destination register"),
        "rs1":         Port(5,  "out", "Source register 1"),
        "rs2":         Port(5,  "out", "Source register 2"),
        "funct3":      Port(3,  "out", "funct3 field"),
        "funct7":      Port(7,  "out", "funct7 field"),
        "imm":         Port(32, "out", "Sign-extended immediate"),
        "alu_op":      Port(4,  "out", "ALU operation"),
        "alu_src":     Port(1,  "out", "0=rs2  1=imm"),
        "use_pc":      Port(1,  "out", "0=rs1  1=PC"),
        "mem_read":    Port(1,  "out", "Memory read enable"),
        "mem_write":   Port(1,  "out", "Memory write enable"),
        "reg_write":   Port(1,  "out", "Register write enable"),
        "branch":      Port(1,  "out", "Is branch instruction"),
        "branch_cond": Port(3,  "out", "Branch condition code"),
        "jal":         Port(1,  "out", "JAL instruction"),
        "jalr":        Port(1,  "out", "JALR instruction"),
        "wb_sel":      Port(2,  "out", "Writeback source select"),
    }

    def evaluate(self):
        instr = self["instr_in"]

        # ── Raw field extraction ──────────────────────────────────
        opcode = instr & 0x7F
        rd     = (instr >> 7) & 0x1F
        funct3 = (instr >> 12) & 0x7
        rs1    = (instr >> 15) & 0x1F
        rs2    = (instr >> 20) & 0x1F
        funct7 = (instr >> 25) & 0x7F

        self["opcode"] = opcode
        self["rd"]     = rd
        self["funct3"] = funct3
        self["rs1"]    = rs1
        self["rs2"]    = rs2
        self["funct7"] = funct7

        # ── Immediate decoding ────────────────────────────────────
        imm_i = sign_extend((instr >> 20) & 0xFFF, 12)
        imm_s = sign_extend(((instr >> 7) & 0x1F) | (((instr >> 25) & 0x7F) << 5), 12)
        imm_b = sign_extend(
            (((instr >> 8) & 0xF) << 1)
            | (((instr >> 25) & 0x3F) << 5)
            | (((instr >> 7) & 1) << 11)
            | (((instr >> 31) & 1) << 12),
            13,
        )
        imm_u = instr & 0xFFFFF000
        imm_j = sign_extend(
            (((instr >> 21) & 0x3FF) << 1)
            | (((instr >> 20) & 1) << 11)
            | (((instr >> 12) & 0xFF) << 12)
            | (((instr >> 31) & 1) << 20),
            21,
        )

        # Select immediate by opcode
        if opcode in (Opcode.I_ALU, Opcode.LOAD, Opcode.JALR):
            imm = imm_i
        elif opcode == Opcode.STORE:
            imm = imm_s
        elif opcode == Opcode.BRANCH:
            imm = imm_b
        elif opcode in (Opcode.LUI, Opcode.AUIPC):
            imm = imm_u
        elif opcode == Opcode.JAL:
            imm = imm_j
        else:
            imm = 0

        self["imm"] = imm

        # ── Reset control signals ─────────────────────────────────
        self["alu_op"]      = 0
        self["alu_src"]     = 0
        self["use_pc"]      = 0
        self["mem_read"]    = 0
        self["mem_write"]   = 0
        self["reg_write"]   = 0
        self["branch"]      = 0
        self["branch_cond"] = BranchCond.NEVER
        self["jal"]         = 0
        self["jalr"]        = 0
        self["wb_sel"]      = WBSel.ALU

        # ── Control signal generation ─────────────────────────────
        if opcode == Opcode.R_TYPE:
            self["reg_write"] = 1
            self["alu_src"]   = 0
            self["wb_sel"]    = WBSel.ALU
            self._decode_r_alu(funct3, funct7)

        elif opcode == Opcode.I_ALU:
            self["reg_write"] = 1
            self["alu_src"]   = 1
            self["wb_sel"]    = WBSel.ALU
            self._decode_i_alu(funct3, funct7)

        elif opcode == Opcode.LOAD:
            self["reg_write"] = 1
            self["alu_src"]   = 1
            self["alu_op"]    = AluOp.ADD
            self["mem_read"]  = 1
            self["wb_sel"]    = WBSel.MEMORY

        elif opcode == Opcode.STORE:
            self["alu_src"]   = 1
            self["alu_op"]    = AluOp.ADD
            self["mem_write"] = 1

        elif opcode == Opcode.BRANCH:
            self["branch"] = 1
            self["alu_src"] = 0
            self._decode_branch(funct3)

        elif opcode == Opcode.JAL:
            self["reg_write"] = 1
            self["jal"]       = 1
            self["wb_sel"]    = WBSel.PC4

        elif opcode == Opcode.JALR:
            self["reg_write"] = 1
            self["jalr"]      = 1
            self["alu_src"]   = 1
            self["alu_op"]    = AluOp.ADD
            self["wb_sel"]    = WBSel.PC4

        elif opcode == Opcode.LUI:
            self["reg_write"] = 1
            self["alu_src"]   = 1
            self["alu_op"]    = AluOp.PASS
            self["wb_sel"]    = WBSel.ALU

        elif opcode == Opcode.AUIPC:
            self["reg_write"] = 1
            self["use_pc"]    = 1
            self["alu_src"]   = 1
            self["alu_op"]    = AluOp.ADD
            self["wb_sel"]    = WBSel.ALU

    # ── helpers ───────────────────────────────────────────────────

    def _decode_r_alu(self, funct3, funct7):
        if funct3 == Funct3.ADD_SUB:
            self["alu_op"] = AluOp.SUB if funct7 == Funct7.ALT else AluOp.ADD
        elif funct3 == Funct3.AND:     self["alu_op"] = AluOp.AND
        elif funct3 == Funct3.OR:      self["alu_op"] = AluOp.OR
        elif funct3 == Funct3.XOR:     self["alu_op"] = AluOp.XOR
        elif funct3 == Funct3.SLT:     self["alu_op"] = AluOp.SLT
        elif funct3 == Funct3.SLTU:    self["alu_op"] = AluOp.SLTU
        elif funct3 == Funct3.SLL:     self["alu_op"] = AluOp.SLL
        elif funct3 == Funct3.SRL_SRA:
            self["alu_op"] = AluOp.SRA if funct7 == Funct7.ALT else AluOp.SRL

    def _decode_i_alu(self, funct3, funct7):
        if funct3 == Funct3.ADD_SUB:   self["alu_op"] = AluOp.ADD
        elif funct3 == Funct3.AND:     self["alu_op"] = AluOp.AND
        elif funct3 == Funct3.OR:      self["alu_op"] = AluOp.OR
        elif funct3 == Funct3.XOR:     self["alu_op"] = AluOp.XOR
        elif funct3 == Funct3.SLT:     self["alu_op"] = AluOp.SLT
        elif funct3 == Funct3.SLTU:    self["alu_op"] = AluOp.SLTU
        elif funct3 == Funct3.SLL:     self["alu_op"] = AluOp.SLL
        elif funct3 == Funct3.SRL_SRA:
            self["alu_op"] = AluOp.SRA if funct7 == Funct7.ALT else AluOp.SRL

    def _decode_branch(self, funct3):
        if funct3 == Funct3.BEQ:
            self["alu_op"] = AluOp.SUB; self["branch_cond"] = BranchCond.EQ
        elif funct3 == Funct3.BNE:
            self["alu_op"] = AluOp.SUB; self["branch_cond"] = BranchCond.NEQ
        elif funct3 == Funct3.BLT:
            self["alu_op"] = AluOp.SLT; self["branch_cond"] = BranchCond.LT
        elif funct3 == Funct3.BGE:
            self["alu_op"] = AluOp.SLT; self["branch_cond"] = BranchCond.GE
        elif funct3 == Funct3.BLTU:
            self["alu_op"] = AluOp.SLTU; self["branch_cond"] = BranchCond.LT
        elif funct3 == Funct3.BGEU:
            self["alu_op"] = AluOp.SLTU; self["branch_cond"] = BranchCond.GE

    def get_state(self):
        return {
            "rd":       self["rd"],
            "rs1":      self["rs1"],
            "rs2":      self["rs2"],
            "imm":      self["imm"],
            "alu_op":   ALU_OP_NAMES.get(self["alu_op"], str(self["alu_op"])),
            "alu_src":  self["alu_src"],
            "mem_read": self["mem_read"],
            "mem_write": self["mem_write"],
            "reg_write": self["reg_write"],
            "branch":   self["branch"],
            "jal":      self["jal"],
            "jalr":     self["jalr"],
        }
