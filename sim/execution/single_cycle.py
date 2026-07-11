from amaranth import *
from ..core.memory import InstructionMemory, DataMemory
from ..core.signals import WBSel, BranchCond
from .base import ExecutionModelBase


class SingleCycleCPU(Elaboratable):
    """
    Single-cycle datapath.

    Every instruction completes in exactly one clock cycle:
      Fetch → Decode → Execute → Memory → Writeback

    No pipeline registers. No hazard detection.
    This is the simplest execution model and the reference baseline.

    ┌──────────────────────────────────────────────────────────────┐
    │  HOT-SWAP POINTS                                             │
    │  isa=RISCV()  →  isa=ARM()  →  isa=X86()                   │
    │    swaps: decoder, register file config, PC reset            │
    │    unchanged: ALU, memory, this datapath wiring              │
    │                                                              │
    │  Replace SingleCycleCPU with PipelinedCPU or OoOCPU to      │
    │  change the execution model while keeping the same ISA.      │
    └──────────────────────────────────────────────────────────────┘
    """

    def __init__(self, isa, program: list):
        self._isa  = isa
        self._prog = program

        # Create submodules here (not in elaborate) so the runner
        # can reference them before/after simulation.
        self._imem    = InstructionMemory(program)
        self._dmem    = DataMemory()
        self._decoder = isa.create_decoder()
        self._regfile = isa.create_register_file()
        self._alu     = isa.create_alu()

        # Signals exposed for simulation readback and the UI
        self.pc      = Signal(32, reset=isa.pc_reset())
        self.instr   = Signal(32)
        self.alu_out = Signal(32)
        self.stall   = Signal()    # always 0 in single-cycle; present for API compat

    def elaborate(self, platform):
        m = Module()

        m.submodules.imem    = self._imem
        m.submodules.dmem    = self._dmem
        m.submodules.decoder = self._decoder
        m.submodules.regfile = self._regfile
        m.submodules.alu     = self._alu

        dec = self._decoder
        reg = self._regfile
        alu = self._alu

        pc4 = Signal(32)

        # ── FETCH ────────────────────────────────────────────────
        m.d.comb += [
            self._imem.addr.eq(self.pc),
            self.instr     .eq(self._imem.data),
            dec.instr      .eq(self._imem.data),
            pc4            .eq(self.pc + 4),
        ]

        # ── REGISTER READ ────────────────────────────────────────
        m.d.comb += [
            reg.rs1_addr.eq(dec.rs1),
            reg.rs2_addr.eq(dec.rs2),
        ]

        # ── ALU INPUT MUX ────────────────────────────────────────
        alu_a = Signal(32)
        with m.If(dec.use_pc):
            m.d.comb += alu_a.eq(self.pc)    # AUIPC
        with m.Else():
            m.d.comb += alu_a.eq(reg.rs1_data)

        alu_b = Signal(32)
        with m.If(dec.alu_src):
            m.d.comb += alu_b.eq(dec.imm)   # immediate
        with m.Else():
            m.d.comb += alu_b.eq(reg.rs2_data)

        m.d.comb += [
            alu.a.eq(alu_a),
            alu.b.eq(alu_b),
            alu.op.eq(dec.alu_op),
            self.alu_out.eq(alu.result),
        ]

        # ── DATA MEMORY ──────────────────────────────────────────
        m.d.comb += [
            self._dmem.addr .eq(alu.result),
            self._dmem.wdata.eq(reg.rs2_data),
            self._dmem.wen  .eq(dec.mem_write),
        ]

        # ── WRITEBACK MUX ────────────────────────────────────────
        wb_data = Signal(32)
        with m.Switch(dec.wb_sel):
            with m.Case(WBSel.ALU):    m.d.comb += wb_data.eq(alu.result)
            with m.Case(WBSel.MEMORY): m.d.comb += wb_data.eq(self._dmem.rdata)
            with m.Case(WBSel.PC4):    m.d.comb += wb_data.eq(pc4)

        m.d.comb += [
            reg.rd_addr.eq(dec.rd),
            reg.rd_data.eq(wb_data),
            reg.wen    .eq(dec.reg_write),
        ]

        # ── BRANCH / PC UPDATE ───────────────────────────────────
        branch_taken = Signal()
        with m.Switch(dec.branch_cond):
            with m.Case(BranchCond.EQ):  m.d.comb += branch_taken.eq(alu.zero)
            with m.Case(BranchCond.NEQ): m.d.comb += branch_taken.eq(~alu.zero)
            with m.Case(BranchCond.LT):  m.d.comb += branch_taken.eq(alu.result[0])
            with m.Case(BranchCond.GE):  m.d.comb += branch_taken.eq(~alu.result[0])
            with m.Default():            m.d.comb += branch_taken.eq(0)

        next_pc = Signal(32)
        with m.If(dec.jal):
            m.d.comb += next_pc.eq(self.pc + dec.imm)
        with m.Elif(dec.jalr):
            # JALR: (rs1 + imm_i) with LSB cleared
            m.d.comb += next_pc.eq((reg.rs1_data + dec.imm) & 0xFFFF_FFFE)
        with m.Elif(dec.branch & branch_taken):
            m.d.comb += next_pc.eq(self.pc + dec.imm)
        with m.Else():
            m.d.comb += next_pc.eq(pc4)

        m.d.sync += self.pc.eq(next_pc)

        return m


class SingleCycle(ExecutionModelBase):
    name = "single_cycle"

    def create_cpu(self, isa, program: list):
        return SingleCycleCPU(isa, program)
