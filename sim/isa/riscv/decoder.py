from amaranth import *
from .constants import Opcode, Funct3, Funct7
from ...core.alu import AluOp
from ...core.signals import WBSel, BranchCond


class RISCVDecoder(Elaboratable):
    """
    RISC-V RV32I instruction decoder.
    Pure combinational — maps a 32-bit instruction word → control signals.

    ┌─────────────────────────────────────────────────────────────────┐
    │  THIS IS THE PRIMARY HOT-SWAP POINT BETWEEN ISAs.              │
    │  ARM / x86 decoders expose identical output signals but parse  │
    │  different instruction encodings.  The execution model (single │
    │  cycle, pipeline, OoO) never needs to change.                  │
    └─────────────────────────────────────────────────────────────────┘

    Output signal contract (must be honoured by every ISA decoder):
      rd, rs1, rs2        — register addresses
      imm                 — selected & sign-extended immediate
      alu_op              — AluOp constant
      alu_src             — 0=rs2  1=imm
      use_pc              — 0=rs1  1=PC  (AUIPC)
      mem_read/mem_write  — data memory enable
      reg_write           — register file write enable
      branch              — is a branch instruction
      branch_cond         — BranchCond constant
      jal / jalr          — jump type flags
      wb_sel              — WBSel constant
    """

    def __init__(self):
        # ── Input ──────────────────────────────────────────
        self.instr      = Signal(32)

        # ── Decoded fields (useful for pipeline stages / UI) ─
        self.opcode     = Signal(7)
        self.rd         = Signal(5)
        self.rs1        = Signal(5)
        self.rs2        = Signal(5)
        self.funct3     = Signal(3)
        self.funct7     = Signal(7)
        self.imm        = Signal(32)   # pre-selected, sign-extended immediate

        # ── Control signals (ISA-agnostic interface) ────────
        self.alu_op     = Signal(4)
        self.alu_src    = Signal()     # 0=rs2  1=imm
        self.use_pc     = Signal()     # 0=rs1  1=PC  (AUIPC)
        self.mem_read   = Signal()
        self.mem_write  = Signal()
        self.reg_write  = Signal()
        self.branch     = Signal()
        self.branch_cond = Signal(3)   # BranchCond
        self.jal        = Signal()
        self.jalr       = Signal()
        self.wb_sel     = Signal(2)    # WBSel

    def elaborate(self, platform):
        m = Module()

        instr = self.instr

        # ── Raw field extraction ────────────────────────────
        m.d.comb += [
            self.opcode.eq(instr[0:7]),
            self.rd    .eq(instr[7:12]),
            self.funct3.eq(instr[12:15]),
            self.rs1   .eq(instr[15:20]),
            self.rs2   .eq(instr[20:25]),
            self.funct7.eq(instr[25:32]),
        ]

        # ── Immediate formats ───────────────────────────────
        imm_i = Signal(32)
        imm_s = Signal(32)
        imm_b = Signal(32)
        imm_u = Signal(32)
        imm_j = Signal(32)

        m.d.comb += imm_i.eq(instr[20:32].as_signed())
        m.d.comb += imm_s.eq(Cat(instr[7:12], instr[25:32]).as_signed())
        m.d.comb += imm_b.eq(
            Cat(Const(0, 1), instr[8:12], instr[25:31], instr[7], instr[31]).as_signed()
        )
        m.d.comb += imm_u.eq(Cat(Const(0, 12), instr[12:32]))
        m.d.comb += imm_j.eq(
            Cat(Const(0, 1), instr[21:31], instr[20], instr[12:20], instr[31]).as_signed()
        )

        # Select which immediate this instruction uses
        with m.Switch(self.opcode):
            with m.Case(Opcode.I_ALU, Opcode.LOAD, Opcode.JALR):
                m.d.comb += self.imm.eq(imm_i)
            with m.Case(Opcode.STORE):
                m.d.comb += self.imm.eq(imm_s)
            with m.Case(Opcode.BRANCH):
                m.d.comb += self.imm.eq(imm_b)
            with m.Case(Opcode.LUI, Opcode.AUIPC):
                m.d.comb += self.imm.eq(imm_u)
            with m.Case(Opcode.JAL):
                m.d.comb += self.imm.eq(imm_j)
            with m.Default():
                m.d.comb += self.imm.eq(0)

        # ── Control signal generation ───────────────────────
        with m.Switch(self.opcode):

            with m.Case(Opcode.R_TYPE):
                m.d.comb += [
                    self.reg_write.eq(1),
                    self.alu_src  .eq(0),
                    self.wb_sel   .eq(WBSel.ALU),
                ]
                with m.Switch(self.funct3):
                    with m.Case(Funct3.ADD_SUB):
                        with m.If(self.funct7 == Funct7.ALT):
                            m.d.comb += self.alu_op.eq(AluOp.SUB)
                        with m.Else():
                            m.d.comb += self.alu_op.eq(AluOp.ADD)
                    with m.Case(Funct3.AND):     m.d.comb += self.alu_op.eq(AluOp.AND)
                    with m.Case(Funct3.OR):      m.d.comb += self.alu_op.eq(AluOp.OR)
                    with m.Case(Funct3.XOR):     m.d.comb += self.alu_op.eq(AluOp.XOR)
                    with m.Case(Funct3.SLT):     m.d.comb += self.alu_op.eq(AluOp.SLT)
                    with m.Case(Funct3.SLTU):    m.d.comb += self.alu_op.eq(AluOp.SLTU)
                    with m.Case(Funct3.SLL):     m.d.comb += self.alu_op.eq(AluOp.SLL)
                    with m.Case(Funct3.SRL_SRA):
                        with m.If(self.funct7 == Funct7.ALT):
                            m.d.comb += self.alu_op.eq(AluOp.SRA)
                        with m.Else():
                            m.d.comb += self.alu_op.eq(AluOp.SRL)

            with m.Case(Opcode.I_ALU):
                m.d.comb += [
                    self.reg_write.eq(1),
                    self.alu_src  .eq(1),
                    self.wb_sel   .eq(WBSel.ALU),
                ]
                with m.Switch(self.funct3):
                    with m.Case(Funct3.ADD_SUB): m.d.comb += self.alu_op.eq(AluOp.ADD)
                    with m.Case(Funct3.AND):     m.d.comb += self.alu_op.eq(AluOp.AND)
                    with m.Case(Funct3.OR):      m.d.comb += self.alu_op.eq(AluOp.OR)
                    with m.Case(Funct3.XOR):     m.d.comb += self.alu_op.eq(AluOp.XOR)
                    with m.Case(Funct3.SLT):     m.d.comb += self.alu_op.eq(AluOp.SLT)
                    with m.Case(Funct3.SLTU):    m.d.comb += self.alu_op.eq(AluOp.SLTU)
                    with m.Case(Funct3.SLL):     m.d.comb += self.alu_op.eq(AluOp.SLL)
                    with m.Case(Funct3.SRL_SRA):
                        with m.If(self.funct7 == Funct7.ALT):
                            m.d.comb += self.alu_op.eq(AluOp.SRA)
                        with m.Else():
                            m.d.comb += self.alu_op.eq(AluOp.SRL)

            with m.Case(Opcode.LOAD):
                m.d.comb += [
                    self.reg_write.eq(1),
                    self.alu_src  .eq(1),
                    self.alu_op   .eq(AluOp.ADD),
                    self.mem_read .eq(1),
                    self.wb_sel   .eq(WBSel.MEMORY),
                ]

            with m.Case(Opcode.STORE):
                m.d.comb += [
                    self.alu_src  .eq(1),
                    self.alu_op   .eq(AluOp.ADD),
                    self.mem_write.eq(1),
                ]

            with m.Case(Opcode.BRANCH):
                m.d.comb += [
                    self.branch  .eq(1),
                    self.alu_src .eq(0),
                ]
                with m.Switch(self.funct3):
                    with m.Case(Funct3.BEQ):
                        m.d.comb += [self.alu_op.eq(AluOp.SUB),  self.branch_cond.eq(BranchCond.EQ)]
                    with m.Case(Funct3.BNE):
                        m.d.comb += [self.alu_op.eq(AluOp.SUB),  self.branch_cond.eq(BranchCond.NEQ)]
                    with m.Case(Funct3.BLT):
                        m.d.comb += [self.alu_op.eq(AluOp.SLT),  self.branch_cond.eq(BranchCond.LT)]
                    with m.Case(Funct3.BGE):
                        m.d.comb += [self.alu_op.eq(AluOp.SLT),  self.branch_cond.eq(BranchCond.GE)]
                    with m.Case(Funct3.BLTU):
                        m.d.comb += [self.alu_op.eq(AluOp.SLTU), self.branch_cond.eq(BranchCond.LT)]
                    with m.Case(Funct3.BGEU):
                        m.d.comb += [self.alu_op.eq(AluOp.SLTU), self.branch_cond.eq(BranchCond.GE)]

            with m.Case(Opcode.JAL):
                m.d.comb += [
                    self.reg_write.eq(1),
                    self.jal      .eq(1),
                    self.wb_sel   .eq(WBSel.PC4),
                ]

            with m.Case(Opcode.JALR):
                m.d.comb += [
                    self.reg_write.eq(1),
                    self.jalr     .eq(1),
                    self.alu_src  .eq(1),
                    self.alu_op   .eq(AluOp.ADD),
                    self.wb_sel   .eq(WBSel.PC4),
                ]

            with m.Case(Opcode.LUI):
                m.d.comb += [
                    self.reg_write.eq(1),
                    self.alu_src  .eq(1),
                    self.alu_op   .eq(AluOp.PASS),
                    self.wb_sel   .eq(WBSel.ALU),
                ]

            with m.Case(Opcode.AUIPC):
                m.d.comb += [
                    self.reg_write.eq(1),
                    self.use_pc   .eq(1),
                    self.alu_src  .eq(1),
                    self.alu_op   .eq(AluOp.ADD),
                    self.wb_sel   .eq(WBSel.ALU),
                ]

        return m
