"""
ARM AArch64 (A64) instruction decoder — real bit-field parsing.

Parses fixed 32-bit A64 instructions into the same control signals as the
RISC-V decoder. The execution model never needs to change.

Supported subset:
  - Data processing (register): ADD, SUB, SUBS, AND, ORR, EOR
  - Data processing (immediate): ADD, SUB, MOVZ
  - Load/Store unsigned offset: LDR, STR (64-bit variant treated as 32-bit)
  - Branch: B, BL, B.cond, CBZ, CBNZ, RET
"""
from sim.component.base import ComponentBase, Port, sign_extend
from sim.core.signals import AluOp, WBSel, BranchCond, ALU_OP_NAMES
from .constants import bits, A64Cond


class ARMDecoder(ComponentBase):
    name = "arm_decoder"
    ui_label = "ARM A64 Decoder"
    ui_category = "decode"
    ports_spec = {
        "instr_in":    Port(32, "in",  "Instruction word"),
        "rd":          Port(5,  "out", "Destination register"),
        "rs1":         Port(5,  "out", "Source register 1 (Rn)"),
        "rs2":         Port(5,  "out", "Source register 2 (Rm)"),
        "imm":         Port(32, "out", "Sign-extended immediate"),
        "alu_op":      Port(4,  "out", "ALU operation"),
        "alu_src":     Port(1,  "out", "0=rs2  1=imm"),
        "use_pc":      Port(1,  "out", "0=rs1  1=PC"),
        "mem_read":    Port(1,  "out", "Memory read enable"),
        "mem_write":   Port(1,  "out", "Memory write enable"),
        "reg_write":   Port(1,  "out", "Register write enable"),
        "branch":      Port(1,  "out", "Is branch instruction"),
        "branch_cond": Port(3,  "out", "Branch condition code"),
        "jal":         Port(1,  "out", "Unconditional jump (B/BL)"),
        "jalr":        Port(1,  "out", "Register jump (RET)"),
        "wb_sel":      Port(2,  "out", "Writeback source select"),
        # ARM flags register (internal, set by SUBS/CMP)
        "sets_flags":  Port(1,  "out", "Instruction sets condition flags"),
    }

    def __init__(self, **kw):
        super().__init__(**kw)
        self._flag_z = 0   # zero flag (from last flag-setting instruction)
        self._flag_n = 0   # negative flag

    def evaluate(self):
        instr = self["instr_in"]

        # Reset all control signals
        self["rd"] = 0
        self["rs1"] = 0
        self["rs2"] = 0
        self["imm"] = 0
        self["alu_op"] = 0
        self["alu_src"] = 0
        self["use_pc"] = 0
        self["mem_read"] = 0
        self["mem_write"] = 0
        self["reg_write"] = 0
        self["branch"] = 0
        self["branch_cond"] = BranchCond.NEVER
        self["jal"] = 0
        self["jalr"] = 0
        self["wb_sel"] = WBSel.ALU
        self["sets_flags"] = 0

        if instr == 0 or instr == 0xD503201F:
            return  # NOP

        # ── Classify by top bits ───────────────────────────────────
        op0 = bits(instr, 31, 25)
        top4 = bits(instr, 31, 28)
        top8 = bits(instr, 31, 24)

        # Data Processing — Register (ADD/SUB/AND/ORR/EOR Xd, Xn, Xm)
        # [31]=sf=1, [30:29]=opc, [28:24]=x1011(shift) or x1010(logical)
        if bits(instr, 28, 24) == 0b01011 and bits(instr, 31, 31) == 1:
            self._decode_dp_reg_arith(instr)
        elif bits(instr, 28, 24) == 0b01010 and bits(instr, 31, 31) == 1:
            self._decode_dp_reg_logical(instr)

        # Data Processing — Immediate (ADD/SUB Xd, Xn, #imm12)
        # [31]=1, [30:29]=opc, [28:23]=100010
        elif bits(instr, 28, 23) == 0b100010 and bits(instr, 31, 31) == 1:
            self._decode_dp_imm_addsub(instr)

        # Move Wide — MOVZ Xd, #imm16
        # [31]=1, [30:29]=10, [28:23]=100101
        elif bits(instr, 28, 23) == 0b100101 and bits(instr, 31, 31) == 1:
            self._decode_movz(instr)

        # Load/Store unsigned offset (LDR/STR)
        # [31:30]=1x, [29:27]=111, [26]=0, [25:24]=01
        elif bits(instr, 29, 27) == 0b111 and bits(instr, 25, 24) == 0b01:
            self._decode_ldst(instr)

        # Unconditional Branch — B imm26
        # [31]=0, [30:26]=00101
        elif bits(instr, 31, 26) == 0b000101:
            self._decode_b(instr)

        # Branch with Link — BL imm26
        # [31]=1, [30:26]=00101
        elif bits(instr, 31, 26) == 0b100101:
            self._decode_bl(instr)

        # Conditional Branch — B.cond imm19
        # [31:24]=01010100
        elif bits(instr, 31, 24) == 0b01010100:
            self._decode_bcond(instr)

        # Compare and Branch — CBZ/CBNZ Xt, imm19
        # [31]=1, [30:25]=011010, [24]=op (0=CBZ, 1=CBNZ)
        elif bits(instr, 31, 25) == 0b1011010:
            self._decode_cbz_cbnz(instr)

        # Return — RET {Xn}
        # [31:10]=1101011_0010_11111_0000_00
        elif bits(instr, 31, 10) == 0b1101011_0010_11111_0000_00:
            self._decode_ret(instr)

    # ── Data Processing Register (arithmetic) ──────────────────────
    def _decode_dp_reg_arith(self, instr):
        opc = bits(instr, 30, 29)
        rd  = bits(instr, 4, 0)
        rn  = bits(instr, 9, 5)
        rm  = bits(instr, 20, 16)
        self["rd"] = rd
        self["rs1"] = rn
        self["rs2"] = rm
        self["alu_src"] = 0
        self["reg_write"] = 1
        self["wb_sel"] = WBSel.ALU

        if opc == 0b00:      # ADD
            self["alu_op"] = AluOp.ADD
        elif opc == 0b10:    # SUB
            self["alu_op"] = AluOp.SUB
        elif opc == 0b11:    # SUBS (sets flags, also used for CMP when Rd=XZR)
            self["alu_op"] = AluOp.SUB
            self["sets_flags"] = 1
            if rd == 31:     # CMP = SUBS XZR, Xn, Xm
                self["reg_write"] = 0

    # ── Data Processing Register (logical) ─────────────────────────
    def _decode_dp_reg_logical(self, instr):
        opc = bits(instr, 30, 29)
        rd  = bits(instr, 4, 0)
        rn  = bits(instr, 9, 5)
        rm  = bits(instr, 20, 16)
        self["rd"] = rd
        self["rs1"] = rn
        self["rs2"] = rm
        self["alu_src"] = 0
        self["reg_write"] = 1
        self["wb_sel"] = WBSel.ALU

        if opc == 0b00:      # AND
            self["alu_op"] = AluOp.AND
        elif opc == 0b01:    # ORR
            self["alu_op"] = AluOp.OR
        elif opc == 0b10:    # EOR
            self["alu_op"] = AluOp.XOR

    # ── Data Processing Immediate (ADD/SUB) ────────────────────────
    def _decode_dp_imm_addsub(self, instr):
        opc   = bits(instr, 30, 29)
        rd    = bits(instr, 4, 0)
        rn    = bits(instr, 9, 5)
        imm12 = bits(instr, 21, 10)
        sh    = bits(instr, 22, 22)
        if sh:
            imm12 <<= 12
        self["rd"] = rd
        self["rs1"] = rn
        self["imm"] = imm12
        self["alu_src"] = 1
        self["reg_write"] = 1
        self["wb_sel"] = WBSel.ALU

        if opc == 0b00:      # ADD
            self["alu_op"] = AluOp.ADD
        elif opc == 0b10:    # SUB
            self["alu_op"] = AluOp.SUB

    # ── MOVZ ───────────────────────────────────────────────────────
    def _decode_movz(self, instr):
        rd    = bits(instr, 4, 0)
        imm16 = bits(instr, 20, 5)
        hw    = bits(instr, 22, 21)
        val   = imm16 << (hw * 16)
        self["rd"] = rd
        self["rs1"] = 31      # XZR = 0
        self["imm"] = val
        self["alu_src"] = 1
        self["alu_op"] = AluOp.ADD   # 0 + imm
        self["reg_write"] = 1
        self["wb_sel"] = WBSel.ALU

    # ── Load / Store unsigned offset ───────────────────────────────
    def _decode_ldst(self, instr):
        is_load = bits(instr, 22, 22)
        imm12   = bits(instr, 21, 10)
        rn      = bits(instr, 9, 5)
        rt      = bits(instr, 4, 0)
        # Scale by 8 for 64-bit variant, but we use 4 (word) for 32-bit sim
        # Size field [31:30]: 11 = 64-bit. We'll scale by 4 for our sim.
        size = bits(instr, 31, 30)
        scale = 1 << size  # 8 for size=3, 4 for size=2
        offset = imm12 * scale

        self["rs1"] = rn
        self["imm"] = offset
        self["alu_src"] = 1
        self["alu_op"] = AluOp.ADD
        if is_load:
            self["rd"] = rt
            self["mem_read"] = 1
            self["reg_write"] = 1
            self["wb_sel"] = WBSel.MEMORY
        else:
            self["rs2"] = rt     # store data source
            self["mem_write"] = 1

    # ── B (unconditional) ──────────────────────────────────────────
    def _decode_b(self, instr):
        imm26 = bits(instr, 25, 0)
        offset = sign_extend(imm26 << 2, 28)
        self["imm"] = offset
        self["jal"] = 1
        # No link register (unlike BL), but we don't write rd
        self["reg_write"] = 0

    # ── BL (branch with link) ──────────────────────────────────────
    def _decode_bl(self, instr):
        imm26 = bits(instr, 25, 0)
        offset = sign_extend(imm26 << 2, 28)
        self["imm"] = offset
        self["rd"] = 30          # X30 = link register
        self["jal"] = 1
        self["reg_write"] = 1
        self["wb_sel"] = WBSel.PC4

    # ── B.cond ─────────────────────────────────────────────────────
    def _decode_bcond(self, instr):
        cond   = bits(instr, 3, 0)
        imm19  = bits(instr, 23, 5)
        offset = sign_extend(imm19 << 2, 21)
        self["imm"] = offset
        self["branch"] = 1
        # Map A64 cond to our BranchCond using ALU SUB:
        # We rely on the flags set by a preceding SUBS/CMP.
        # For B.cond, the branch resolution unit checks alu_zero / alu_result.
        # We set up a SUB comparison via internal flags.
        if cond == A64Cond.EQ:
            self["branch_cond"] = BranchCond.EQ
            self["alu_op"] = AluOp.SUB
        elif cond == A64Cond.NE:
            self["branch_cond"] = BranchCond.NEQ
            self["alu_op"] = AluOp.SUB
        elif cond == A64Cond.LT:
            self["branch_cond"] = BranchCond.LT
            self["alu_op"] = AluOp.SLT
        elif cond == A64Cond.GE:
            self["branch_cond"] = BranchCond.GE
            self["alu_op"] = AluOp.SLT
        elif cond == A64Cond.GT:
            self["branch_cond"] = BranchCond.GT
            self["alu_op"] = AluOp.SLT
        elif cond == A64Cond.LE:
            self["branch_cond"] = BranchCond.LE
            self["alu_op"] = AluOp.SLT
        else:
            self["branch_cond"] = BranchCond.NEVER

    # ── CBZ / CBNZ ─────────────────────────────────────────────────
    def _decode_cbz_cbnz(self, instr):
        op    = bits(instr, 24, 24)   # 0=CBZ, 1=CBNZ
        imm19 = bits(instr, 23, 5)
        rt    = bits(instr, 4, 0)
        offset = sign_extend(imm19 << 2, 21)
        self["imm"] = offset
        self["rs1"] = rt
        self["rs2"] = 31          # compare against XZR (0)
        self["alu_op"] = AluOp.SUB
        self["alu_src"] = 0
        self["branch"] = 1
        self["sets_flags"] = 1  # CBZ/CBNZ uses current ALU result, pass through flags
        if op == 0:   # CBZ: branch if Rt == 0
            self["branch_cond"] = BranchCond.EQ
        else:         # CBNZ: branch if Rt != 0
            self["branch_cond"] = BranchCond.NEQ

    # ── RET ────────────────────────────────────────────────────────
    def _decode_ret(self, instr):
        rn = bits(instr, 9, 5)   # usually X30
        self["rs1"] = rn
        self["imm"] = 0
        self["jalr"] = 1

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
