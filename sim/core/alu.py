from amaranth import *


class AluOp:
    """
    ISA-agnostic ALU operation codes.
    ISA decoders translate their native opcodes → these values.
    Adding a new ISA never requires touching ALU internals.
    """
    ADD  = 0
    SUB  = 1
    AND  = 2
    OR   = 3
    XOR  = 4
    SLT  = 5   # signed less-than  → result = (a < b) ? 1 : 0
    SLTU = 6   # unsigned less-than
    SLL  = 7   # shift left  logical
    SRL  = 8   # shift right logical
    SRA  = 9   # shift right arithmetic
    PASS = 10  # pass B unchanged  (used for LUI)


class ALU(Elaboratable):
    """
    Shared 32-bit ALU.  Purely combinational.
    All ISAs reuse this module — only the decoder differs.
    """

    def __init__(self):
        self.a      = Signal(32)
        self.b      = Signal(32)
        self.op     = Signal(4)
        self.result = Signal(32)
        self.zero   = Signal()    # result == 0 (branch condition)

    def elaborate(self, platform):
        m = Module()
        shamt = self.b[:5]   # shift amount = lower 5 bits of B

        with m.Switch(self.op):
            with m.Case(AluOp.ADD):  m.d.comb += self.result.eq(self.a + self.b)
            with m.Case(AluOp.SUB):  m.d.comb += self.result.eq(self.a - self.b)
            with m.Case(AluOp.AND):  m.d.comb += self.result.eq(self.a & self.b)
            with m.Case(AluOp.OR):   m.d.comb += self.result.eq(self.a | self.b)
            with m.Case(AluOp.XOR):  m.d.comb += self.result.eq(self.a ^ self.b)
            with m.Case(AluOp.SLT):
                m.d.comb += self.result.eq(self.a.as_signed() < self.b.as_signed())
            with m.Case(AluOp.SLTU):
                m.d.comb += self.result.eq(self.a < self.b)
            with m.Case(AluOp.SLL):  m.d.comb += self.result.eq(self.a << shamt)
            with m.Case(AluOp.SRL):  m.d.comb += self.result.eq(self.a >> shamt)
            with m.Case(AluOp.SRA):
                m.d.comb += self.result.eq(self.a.as_signed() >> shamt)
            with m.Case(AluOp.PASS): m.d.comb += self.result.eq(self.b)
            with m.Default():        m.d.comb += self.result.eq(0)

        m.d.comb += self.zero.eq(self.result == 0)
        return m
