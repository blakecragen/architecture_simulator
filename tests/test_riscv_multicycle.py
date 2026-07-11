"""
Tests for the RISC-V multi-cycle (FetDecExe) CPU preset.

Multi-cycle timing:
  ALU ops:  3 cycles (Fetch, Decode, Execute+WB)
  Loads:    4 cycles (Fetch, Decode, Execute, Memory+WB)
  Stores:   4 cycles (Fetch, Decode, Execute, Memory)
  Branches: 3 cycles (Fetch, Decode, Execute)

Test program:
    ADDI  x1, x0, 5        → x1 = 5
    ADDI  x2, x0, 3        → x2 = 3
    ADD   x3, x1, x2       → x3 = 8
    SUB   x4, x1, x2       → x4 = 2
    SW    x3, 0(x0)         → mem[0] = 8
    LW    x5, 0(x0)         → x5 = 8
    BEQ   x1, x2, +8       → not taken (5 ≠ 3)
    ADDI  x6, x0, 99       → x6 = 99
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.isa.riscv.presets.multicycle import build
from sim.runner_v2 import run_simulation
from sim.component.topology import generate_topology


PROGRAM = [
    0x00500093,  # ADDI  x1, x0, 5
    0x00300113,  # ADDI  x2, x0, 3
    0x002081B3,  # ADD   x3, x1, x2
    0x40208233,  # SUB   x4, x1, x2
    0x00302023,  # SW    x3, 0(x0)
    0x00002283,  # LW    x5, 0(x0)
    0x00208463,  # BEQ   x1, x2, +8   (not taken: x1=5, x2=3)
    0x06300313,  # ADDI  x6, x0, 99
]


class TestRISCVMultiCycle(unittest.TestCase):

    def setUp(self):
        self.cpu = build(PROGRAM)

    def test_build_returns_cpu(self):
        from sim.component.wire import CPU
        self.assertIsInstance(self.cpu, CPU)

    def test_topology_structure(self):
        topo = generate_topology(self.cpu)
        self.assertIn("nodes", topo)
        self.assertIn("edges", topo)
        node_ids = {n["id"] for n in topo["nodes"]}
        for expected in ("mc_ctrl", "ir", "reg_a", "reg_b", "alu_out", "pc_latch"):
            self.assertIn(expected, node_ids)

    def test_all_components_in_state(self):
        """Every component should appear in the cycle state."""
        states = run_simulation(self.cpu, num_cycles=1)
        expected = {
            "fetch", "imem", "decode", "regfile", "alu_mux", "alu",
            "branch", "bpred", "dmem", "wb",
            "mc_ctrl", "ir", "reg_a", "reg_b", "alu_out", "pc_latch",
            "gate_reg_wen", "gate_mem_wen", "gate_branch",
        }
        self.assertEqual(set(states[0].keys()) - {"_cycle"}, expected)

    def test_controller_phase_cycling(self):
        """For ALU ops, phases should cycle: FETCH(0) -> DECODE(1) -> EXECUTE(2) -> FETCH(0)."""
        states = run_simulation(self.cpu, num_cycles=6)
        phases = [s["mc_ctrl"]["phase"] for s in states]
        # Cycle 0: FETCH, Cycle 1: DECODE, Cycle 2: EXECUTE (completes ADDI x1)
        # Cycle 3: FETCH, Cycle 4: DECODE, Cycle 5: EXECUTE (completes ADDI x2)
        self.assertEqual(phases, [0, 1, 2, 0, 1, 2])

    def test_addi_takes_3_cycles(self):
        """ADDI x1, x0, 5 should complete in 3 cycles. x1=5 after cycle 3."""
        states = run_simulation(self.cpu, num_cycles=3)
        # After cycle 2 (0-indexed), the EXECUTE phase for ADDI x1 fires
        # and gate_reg_wen should let the write through
        regs = states[2]["regfile"]["registers"]
        self.assertEqual(regs[1], 5)  # x1 = 5

    def test_add_takes_3_cycles(self):
        """ADD x3, x1, x2: starts at instr 2, takes 3 cycles. After 9 cycles total."""
        # Instr 0: cycles 0-2, Instr 1: cycles 3-5, Instr 2: cycles 6-8
        states = run_simulation(self.cpu, num_cycles=9)
        regs = states[8]["regfile"]["registers"]
        self.assertEqual(regs[3], 8)  # x3 = 5 + 3

    def test_store_takes_4_cycles(self):
        """SW x3, 0(x0): instr 4, takes 4 cycles. Starts at cycle 12.
        After 16 cycles, mem[0] should be 8."""
        # Instr 0-3: 4 ALU ops × 3 cycles = 12 cycles (0-11)
        # Instr 4 (SW): cycles 12-15 (Fetch, Decode, Execute, Memory)
        states = run_simulation(self.cpu, num_cycles=16)
        mem = states[15]["dmem"]["memory"]
        self.assertEqual(mem[0], 8)  # mem[0] = x3 = 8

    def test_load_takes_4_cycles(self):
        """LW x5, 0(x0): instr 5, takes 4 cycles. Starts at cycle 16.
        After 20 cycles, x5 should be 8."""
        # Instr 0-3: 12 cycles, Instr 4 (SW): 4 cycles = 16
        # Instr 5 (LW): cycles 16-19
        states = run_simulation(self.cpu, num_cycles=20)
        regs = states[19]["regfile"]["registers"]
        self.assertEqual(regs[5], 8)  # x5 = mem[0] = 8

    def test_branch_not_taken_3_cycles(self):
        """BEQ x1, x2 not taken (5 ≠ 3). After the branch,
        the next instruction (ADDI x6, x0, 99) should execute."""
        # Instr 0-3: 12, Instr 4 (SW): 4, Instr 5 (LW): 4 = 20
        # Instr 6 (BEQ not taken): 3 cycles (20-22)
        # Instr 7 (ADDI x6): 3 cycles (23-25)
        states = run_simulation(self.cpu, num_cycles=26)
        regs = states[25]["regfile"]["registers"]
        self.assertEqual(regs[6], 99)

    def test_branch_taken_3_cycles(self):
        """BEQ x0, x0, +8 should be taken (both are 0)."""
        program = [
            0x00500093,  # ADDI x1, x0, 5
            0x00000463,  # BEQ  x0, x0, +8  (taken → skip next)
            0x06300093,  # ADDI x1, x0, 99  (SKIPPED)
            0x00A00113,  # ADDI x2, x0, 10
        ]
        cpu = build(program)
        # Instr 0 (ADDI): 3 cycles (0-2), Instr 1 (BEQ taken): 3 cycles (3-5)
        # After BEQ, PC jumps to instr 3 (ADDI x2, x0, 10): 3 cycles (6-8)
        states = run_simulation(cpu, num_cycles=9)
        regs = states[8]["regfile"]["registers"]
        self.assertEqual(regs[1], 5)   # x1 stays 5 (the 99 was skipped)
        self.assertEqual(regs[2], 10)  # x2 = 10

    def test_sequence_of_instructions(self):
        """Run the full program and verify all register values."""
        # Total: 4×3 + 4 + 4 + 3 + 3 = 26 cycles for all 8 instructions
        states = run_simulation(self.cpu, num_cycles=26)
        regs = states[25]["regfile"]["registers"]
        self.assertEqual(regs[1], 5)   # ADDI x1, x0, 5
        self.assertEqual(regs[2], 3)   # ADDI x2, x0, 3
        self.assertEqual(regs[3], 8)   # ADD  x3, x1, x2
        self.assertEqual(regs[4], 2)   # SUB  x4, x1, x2
        self.assertEqual(regs[5], 8)   # LW   x5, 0(x0) = mem[0] = 8
        self.assertEqual(regs[6], 99)  # ADDI x6, x0, 99

    def test_simulation_runs_without_error(self):
        """Run demo program for 50 cycles without crashing."""
        states = run_simulation(self.cpu, num_cycles=50)
        self.assertEqual(len(states), 50)


if __name__ == "__main__":
    unittest.main()
