"""
x86-32 instruction decoder — real variable-length encoding.

Decodes a 64-bit byte stream (8 bytes from ByteInstructionMemory) into
the same control signals as RISC-V/ARM decoders plus instruction length.

x86 flags: A FlagsRegister component latches ALU output when write_flags=1.
Jcc reads the latched flags rather than the current ALU output.

Supported instructions:
  1-byte: NOP(90), RET(C3), PUSH(50+r), POP(58+r)
  2-byte: ADD/SUB/AND/OR/XOR/CMP r32,r32, MOV r32,r32, MOV r32,[r32],
          MOV [r32],r32, JMP rel8, Jcc rel8
  3-byte: ADD/SUB/CMP r32,imm8 (83 ModRM imm8),
          MOV r32,[r32+disp8], MOV [r32+disp8],r32
  5-byte: MOV r32,imm32 (B8+r), CALL rel32 (E8)
"""
from sim.component.base import ComponentBase, Port, sign_extend
from sim.core.signals import AluOp, WBSel, BranchCond, ALU_OP_NAMES
from .constants import (
    modrm_mod, modrm_reg, modrm_rm,
    REG_ESP, OP_NOP, OP_RET,
    OP_ADD_R32, OP_OR_R32, OP_AND_R32, OP_SUB_R32, OP_XOR_R32, OP_CMP_R32,
    OP_MOV_RM_R, OP_MOV_R_RM, OP_IMM_GRP1, OP_JMP_REL8, OP_CALL_REL32,
    GRP1_ADD, GRP1_OR, GRP1_AND, GRP1_SUB, GRP1_XOR, GRP1_CMP,
)


def _byte(stream, offset):
    """Extract byte at offset from a 64-bit LE packed stream."""
    return (stream >> (offset * 8)) & 0xFF


def _modrm_disp_len(mod, rm):
    """Bytes a ModRM addressing mode adds AFTER the ModRM byte (disp/SIB).

    Used to keep the variable-length x86 fetch stream aligned for memory
    operand forms (reachable only from raw byte programs; the assembler never
    emits ALU-with-memory)."""
    if mod == 0b01:
        return 1          # disp8
    if mod == 0b10:
        return 4          # disp32
    if mod == 0b00:
        if rm == 0b101:
            return 4      # disp32 with no base register
        if rm == 0b100:
            return 1      # SIB byte (best-effort; no further disp modelled)
    return 0              # register-direct (mod=11) or [reg]


class X86Decoder(ComponentBase):
    name = "x86_decoder"
    ui_label = "x86 Decoder"
    ui_category = "decode"
    ports_spec = {
        "instr_in":    Port(64, "in",  "8-byte instruction stream (LE)"),
        "pc_in":       Port(32, "in",  "Current PC (for relative branches)"),
        "rd":          Port(5,  "out", "Destination register"),
        "rs1":         Port(5,  "out", "Source register 1"),
        "rs2":         Port(5,  "out", "Source register 2"),
        "imm":         Port(32, "out", "Immediate value"),
        "alu_op":      Port(4,  "out", "ALU operation"),
        "alu_src":     Port(1,  "out", "0=rs2  1=imm"),
        "use_pc":      Port(1,  "out", "0=rs1  1=PC"),
        "mem_read":    Port(1,  "out", "Memory read enable"),
        "mem_write":   Port(1,  "out", "Memory write enable"),
        "reg_write":   Port(1,  "out", "Register write enable"),
        "branch":      Port(1,  "out", "Is branch instruction"),
        "branch_cond": Port(3,  "out", "Branch condition code"),
        "jal":         Port(1,  "out", "Unconditional jump"),
        "jalr":        Port(1,  "out", "Register-indirect jump (RET)"),
        "wb_sel":      Port(2,  "out", "Writeback source select"),
        "instr_len":   Port(4,  "out", "Instruction length in bytes"),
        "write_flags": Port(1,  "out", "This instruction updates EFLAGS"),
    }

    def _reset_signals(self):
        for p in ("rd", "rs1", "rs2", "imm", "alu_op", "alu_src", "use_pc",
                   "mem_read", "mem_write", "reg_write", "branch", "branch_cond",
                   "jal", "jalr", "write_flags"):
            self[p] = 0
        self["wb_sel"] = WBSel.ALU
        self["instr_len"] = 1

    def evaluate(self):
        stream = self["instr_in"]
        pc = self["pc_in"]
        b0 = _byte(stream, 0)
        self._reset_signals()

        # ── NOP (0x90) ───────────────────────────────────────────
        if b0 == OP_NOP:
            return

        # ── RET (0xC3) ───────────────────────────────────────────
        if b0 == OP_RET:
            self["instr_len"] = 1
            self["rs1"] = REG_ESP
            self["imm"] = 0
            self["alu_op"] = AluOp.ADD
            self["alu_src"] = 1
            self["mem_read"] = 1
            self["jalr"] = 1
            return

        # ── PUSH r32 (0x50+r) ────────────────────────────────────
        if 0x50 <= b0 <= 0x57:
            r = b0 - 0x50
            self["instr_len"] = 1
            self["rs1"] = REG_ESP
            self["rs2"] = r
            self["imm"] = (-4) & 0xFFFF_FFFF
            self["alu_op"] = AluOp.ADD
            self["alu_src"] = 1
            self["mem_write"] = 1
            self["rd"] = REG_ESP
            self["reg_write"] = 1
            self["wb_sel"] = WBSel.ALU
            return

        # ── POP r32 (0x58+r) ─────────────────────────────────────
        if 0x58 <= b0 <= 0x5F:
            r = b0 - 0x58
            self["instr_len"] = 1
            self["rs1"] = REG_ESP
            self["imm"] = 0
            self["alu_op"] = AluOp.ADD
            self["alu_src"] = 1
            self["mem_read"] = 1
            self["rd"] = r
            self["reg_write"] = 1
            self["wb_sel"] = WBSel.MEMORY
            return

        # ── MOV r32, imm32 (0xB8+r) ─────────────────────────────
        if 0xB8 <= b0 <= 0xBF:
            r = b0 - 0xB8
            imm32 = (_byte(stream, 1) | (_byte(stream, 2) << 8) |
                     (_byte(stream, 3) << 16) | (_byte(stream, 4) << 24))
            self["instr_len"] = 5
            self["rd"] = r
            self["imm"] = imm32
            self["alu_op"] = AluOp.PASS
            self["alu_src"] = 1
            self["reg_write"] = 1
            return

        # ── CALL rel32 (0xE8) ────────────────────────────────────
        # NOTE: modelled as a plain jump (jal). This simplified datapath does
        # not push a return address or adjust ESP, so CALL/RET subroutine
        # linkage is not supported (RET would pop a stale [ESP]). No example
        # program uses CALL/RET.
        if b0 == OP_CALL_REL32:
            rel32 = (_byte(stream, 1) | (_byte(stream, 2) << 8) |
                     (_byte(stream, 3) << 16) | (_byte(stream, 4) << 24))
            offset = sign_extend(rel32, 32)
            self["instr_len"] = 5
            target = (pc + 5 + offset) & 0xFFFF_FFFF
            self["imm"] = target - pc
            self["jal"] = 1
            return

        # ── JMP rel32 (0xE9) ─────────────────────────────────────
        if b0 == 0xE9:
            rel32 = (_byte(stream, 1) | (_byte(stream, 2) << 8) |
                     (_byte(stream, 3) << 16) | (_byte(stream, 4) << 24))
            offset = sign_extend(rel32, 32)
            self["instr_len"] = 5
            target = (pc + 5 + offset) & 0xFFFF_FFFF
            self["imm"] = target - pc
            self["jal"] = 1
            return

        # ── Jcc rel32 (0F 80–8F) ─────────────────────────────────
        if b0 == 0x0F and 0x80 <= _byte(stream, 1) <= 0x8F:
            cond = _byte(stream, 1) & 0x0F
            rel32 = (_byte(stream, 2) | (_byte(stream, 3) << 8) |
                     (_byte(stream, 4) << 16) | (_byte(stream, 5) << 24))
            offset = sign_extend(rel32, 32)
            self["instr_len"] = 6
            target = (pc + 6 + offset) & 0xFFFF_FFFF
            self["imm"] = target - pc
            self["branch"] = 1
            # Same condition mapping as Jcc rel8 below.
            if cond == 0x4:     self["branch_cond"] = BranchCond.EQ   # JE
            elif cond == 0x5:   self["branch_cond"] = BranchCond.NEQ  # JNE
            elif cond == 0xC:   self["branch_cond"] = BranchCond.LT   # JL
            elif cond == 0xD:   self["branch_cond"] = BranchCond.GE   # JGE
            elif cond == 0xE:   self["branch_cond"] = BranchCond.LE   # JLE
            elif cond == 0xF:   self["branch_cond"] = BranchCond.GT   # JG
            return

        # ── JMP rel8 (0xEB) ──────────────────────────────────────
        if b0 == OP_JMP_REL8:
            disp8 = sign_extend(_byte(stream, 1), 8)
            self["instr_len"] = 2
            target = (pc + 2 + disp8) & 0xFFFF_FFFF
            self["imm"] = target - pc
            self["jal"] = 1
            return

        # ── Jcc rel8 (0x70–0x7F) ─────────────────────────────────
        if 0x70 <= b0 <= 0x7F:
            cond = b0 & 0x0F
            disp8 = sign_extend(_byte(stream, 1), 8)
            self["instr_len"] = 2
            target = (pc + 2 + disp8) & 0xFFFF_FFFF
            self["imm"] = target - pc
            self["branch"] = 1
            # write_flags stays 0 — Jcc reads latched flags from FlagsRegister
            # Map x86 conditions:
            if cond == 0x4:     self["branch_cond"] = BranchCond.EQ   # JE
            elif cond == 0x5:   self["branch_cond"] = BranchCond.NEQ  # JNE
            elif cond == 0xC:   self["branch_cond"] = BranchCond.LT   # JL
            elif cond == 0xD:   self["branch_cond"] = BranchCond.GE   # JGE
            elif cond == 0xE:   self["branch_cond"] = BranchCond.LE   # JLE
            elif cond == 0xF:   self["branch_cond"] = BranchCond.GT   # JG
            return

        # ── ALU r32, r32 (01/09/21/29/31/39) ─────────────────────
        if b0 in (OP_ADD_R32, OP_OR_R32, OP_AND_R32, OP_SUB_R32,
                  OP_XOR_R32, OP_CMP_R32):
            b1 = _byte(stream, 1)
            mod = modrm_mod(b1)
            reg = modrm_reg(b1)
            rm = modrm_rm(b1)
            if mod == 0b11:
                self["instr_len"] = 2
                self["rs1"] = rm
                self["rs2"] = reg
                self["alu_src"] = 0
                self["write_flags"] = 1
                alu_op, is_cmp = self._opcode_to_alu(b0)
                self["alu_op"] = alu_op
                if is_cmp:
                    self["reg_write"] = 0
                else:
                    self["rd"] = rm
                    self["reg_write"] = 1
            else:
                # Memory ModRM form (read-modify-write to memory) is not
                # modelled by the single-pass datapath, but compute the correct
                # length so the variable-length fetch stream stays aligned.
                self["instr_len"] = 2 + _modrm_disp_len(mod, rm)
            return

        # ── MOV r/m32, r32 (0x89) or MOV r32, r/m32 (0x8B) ──────
        if b0 == OP_MOV_RM_R or b0 == OP_MOV_R_RM:
            self._decode_mov_rm(stream, b0)
            return

        # ── Group 1: 0x83 ModRM imm8 ─────────────────────────────
        if b0 == OP_IMM_GRP1:
            self._decode_grp1_imm8(stream)
            return

    def _decode_mov_rm(self, stream, opcode):
        b1 = _byte(stream, 1)
        mod = modrm_mod(b1)
        reg = modrm_reg(b1)
        rm = modrm_rm(b1)

        if mod == 0b11:
            self["instr_len"] = 2
            if opcode == OP_MOV_RM_R:
                self["rs1"] = reg
                self["rd"] = rm
            else:
                self["rs1"] = rm
                self["rd"] = reg
            self["imm"] = 0
            self["alu_op"] = AluOp.ADD
            self["alu_src"] = 1
            self["reg_write"] = 1
        elif mod == 0b00:
            self["instr_len"] = 2
            if opcode == OP_MOV_R_RM:
                self["rs1"] = rm
                self["rd"] = reg
                self["imm"] = 0
                self["alu_op"] = AluOp.ADD
                self["alu_src"] = 1
                self["mem_read"] = 1
                self["reg_write"] = 1
                self["wb_sel"] = WBSel.MEMORY
            else:
                self["rs1"] = rm
                self["rs2"] = reg
                self["imm"] = 0
                self["alu_op"] = AluOp.ADD
                self["alu_src"] = 1
                self["mem_write"] = 1
        elif mod == 0b01:
            disp8 = sign_extend(_byte(stream, 2), 8)
            self["instr_len"] = 3
            if opcode == OP_MOV_R_RM:
                self["rs1"] = rm
                self["rd"] = reg
                self["imm"] = disp8
                self["alu_op"] = AluOp.ADD
                self["alu_src"] = 1
                self["mem_read"] = 1
                self["reg_write"] = 1
                self["wb_sel"] = WBSel.MEMORY
            else:
                self["rs1"] = rm
                self["rs2"] = reg
                self["imm"] = disp8
                self["alu_op"] = AluOp.ADD
                self["alu_src"] = 1
                self["mem_write"] = 1

    def _decode_grp1_imm8(self, stream):
        b1 = _byte(stream, 1)
        mod = modrm_mod(b1)
        ext = modrm_reg(b1)
        rm = modrm_rm(b1)
        imm8 = sign_extend(_byte(stream, 2), 8)
        self["instr_len"] = 3
        if mod != 0b11:
            # Memory operand: opcode + ModRM + disp + imm8. Keep the fetch
            # stream aligned (the datapath does not model memory-dest Group 1).
            self["instr_len"] = 3 + _modrm_disp_len(mod, rm)
            return

        self["rs1"] = rm
        self["imm"] = imm8
        self["alu_src"] = 1
        self["write_flags"] = 1

        if ext == GRP1_ADD:
            self["alu_op"] = AluOp.ADD
            self["rd"] = rm
            self["reg_write"] = 1
        elif ext == GRP1_SUB:
            self["alu_op"] = AluOp.SUB
            self["rd"] = rm
            self["reg_write"] = 1
        elif ext == GRP1_AND:
            self["alu_op"] = AluOp.AND
            self["rd"] = rm
            self["reg_write"] = 1
        elif ext == GRP1_OR:
            self["alu_op"] = AluOp.OR
            self["rd"] = rm
            self["reg_write"] = 1
        elif ext == GRP1_XOR:
            self["alu_op"] = AluOp.XOR
            self["rd"] = rm
            self["reg_write"] = 1
        elif ext == GRP1_CMP:
            self["alu_op"] = AluOp.SUB
            self["reg_write"] = 0

    def _opcode_to_alu(self, opcode):
        if opcode == OP_ADD_R32:  return AluOp.ADD, False
        if opcode == OP_SUB_R32:  return AluOp.SUB, False
        if opcode == OP_AND_R32:  return AluOp.AND, False
        if opcode == OP_OR_R32:   return AluOp.OR,  False
        if opcode == OP_XOR_R32:  return AluOp.XOR, False
        if opcode == OP_CMP_R32:  return AluOp.SUB, True
        return AluOp.ADD, False

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
            "instr_len": self["instr_len"],
        }
