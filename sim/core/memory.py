from amaranth import *


class InstructionMemory(Elaboratable):
    """
    Read-only instruction memory.  Loaded from a program list at construction.
    Pure combinational — no write port.
    """

    def __init__(self, program: list):
        # program: list of 32-bit ints, one word per instruction
        self.addr = Signal(32)   # byte address (lower 2 bits ignored)
        self.data = Signal(32)   # instruction word out
        self._program = list(program)

    def elaborate(self, platform):
        m = Module()
        words = Array([Const(w & 0xFFFF_FFFF, 32) for w in self._program])
        m.d.comb += self.data.eq(words[self.addr >> 2])
        return m


class DataMemory(Elaboratable):
    """
    Simple word-addressed data memory.
    Combinational read, synchronous write.
    """

    def __init__(self, size: int = 256):
        # size: number of 32-bit words
        self.addr  = Signal(32)
        self.rdata = Signal(32)
        self.wdata = Signal(32)
        self.wen   = Signal()
        self._size = size

    def elaborate(self, platform):
        m = Module()
        mem = Array([Signal(32, name=f"dmem_{i}") for i in range(self._size)])
        word_addr = self.addr >> 2
        m.d.comb += self.rdata.eq(mem[word_addr])
        with m.If(self.wen):
            m.d.sync += mem[word_addr].eq(self.wdata)
        return m
