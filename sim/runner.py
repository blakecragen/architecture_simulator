"""
Simulation runner.

Drives a CPU elaboratable for N clock cycles and returns
a list of per-cycle state snapshots as plain Python dicts,
ready to be serialised as JSON by the Flask app.
"""
from __future__ import annotations

from amaranth.sim import Simulator, Settle


def run_simulation(cpu, num_cycles: int = 50, clock_freq: float = 1e6) -> list:
    """
    Run *cpu* for *num_cycles* ticks.  Returns a list of state dicts.

    Each dict contains:
      cycle      — int
      pc / pc_hex
      instr / instr_hex
      alu_out
      stall      — 1 if the execution model is stalling (pipeline / OoO)
      registers  — list of 32-bit ints, one per architectural register
    """
    states: list = []
    reg_count = cpu._regfile.num_regs

    sim = Simulator(cpu)
    sim.add_clock(1.0 / clock_freq)

    def process():
        for cycle in range(num_cycles):
            yield          # rising edge — synchronous signals update
            yield Settle() # settle combinational logic

            pc      = yield cpu.pc
            instr   = yield cpu.instr
            alu_out = yield cpu.alu_out
            stall   = yield cpu.stall

            regs = []
            for i in range(reg_count):
                val = yield cpu._regfile.regs[i]
                regs.append(int(val))

            states.append({
                "cycle"    : cycle,
                "pc"       : int(pc),
                "pc_hex"   : f"0x{pc:08x}",
                "instr"    : int(instr),
                "instr_hex": f"0x{instr:08x}",
                "alu_out"  : int(alu_out),
                "stall"    : bool(stall),
                "registers": regs,
            })

    sim.add_sync_process(process)
    sim.run()
    return states
