from amaranth import *


class RegisterFile(Elaboratable):
    """
    Parameterized register file.
    Swap num_regs / zero_reg to match any ISA:
      RISC-V  → num_regs=32, zero_reg=True   (x0 hardwired 0)
      ARM     → num_regs=31, zero_reg=False  (no dedicated zero reg)
      x86     → num_regs=16, zero_reg=False
    """

    def __init__(self, num_regs: int = 32, width: int = 32, zero_reg: bool = True,
                 zero_reg_index: int = 0):
        self.num_regs = num_regs
        self.width    = width
        self.zero_reg = zero_reg
        self.zero_reg_index = zero_reg_index

        # Read port 1
        self.rs1_addr = Signal(range(num_regs))
        self.rs1_data = Signal(width)

        # Read port 2
        self.rs2_addr = Signal(range(num_regs))
        self.rs2_data = Signal(width)

        # Write port
        self.rd_addr  = Signal(range(num_regs))
        self.rd_data  = Signal(width)
        self.wen      = Signal()

        # Expose individual registers so the simulation runner can read them
        self.regs = Array([Signal(width, name=f"reg_{i}") for i in range(num_regs)])

    def elaborate(self, platform):
        m = Module()

        # Synchronous write
        with m.If(self.wen):
            if self.zero_reg:
                with m.If(self.rd_addr != self.zero_reg_index):
                    m.d.sync += self.regs[self.rd_addr].eq(self.rd_data)
            else:
                m.d.sync += self.regs[self.rd_addr].eq(self.rd_data)

        # Combinational reads
        m.d.comb += self.rs1_data.eq(self.regs[self.rs1_addr])
        m.d.comb += self.rs2_data.eq(self.regs[self.rs2_addr])

        # Hard-wire zero register to 0
        if self.zero_reg:
            with m.If(self.rs1_addr == self.zero_reg_index):
                m.d.comb += self.rs1_data.eq(0)
            with m.If(self.rs2_addr == self.zero_reg_index):
                m.d.comb += self.rs2_data.eq(0)

        return m
