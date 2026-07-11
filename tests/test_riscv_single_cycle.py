"""
Tests for the RISC-V single-cycle CPU preset.

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

from sim.isa.riscv.presets.single_cycle import build
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


class TestRISCVSingleCycle(unittest.TestCase):

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
        self.assertIn("fetch", node_ids)
        self.assertIn("decode", node_ids)
        self.assertIn("alu", node_ids)
        self.assertIn("regfile", node_ids)
        self.assertIn("dmem", node_ids)
        self.assertTrue(len(topo["edges"]) > 10)

    def test_addi_instructions(self):
        """After 2 cycles: x1=5, x2=3."""
        states = run_simulation(self.cpu, num_cycles=2)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[1], 5)  # x1
        self.assertEqual(regs[2], 3)  # x2

    def test_add_sub(self):
        """After 4 cycles: x3=8, x4=2."""
        states = run_simulation(self.cpu, num_cycles=4)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[3], 8)  # x3 = 5 + 3
        self.assertEqual(regs[4], 2)  # x4 = 5 - 3

    def test_store_and_load(self):
        """After 6 cycles: x5=8 (loaded from mem[0] which had x3=8)."""
        states = run_simulation(self.cpu, num_cycles=6)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[5], 8)  # x5 = mem[0] = x3 = 8

    def test_branch_not_taken(self):
        """BEQ x1, x2 not taken (5 ≠ 3), x6 = 99 after 8 cycles."""
        states = run_simulation(self.cpu, num_cycles=8)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[6], 99)

    def test_branch_taken(self):
        """BEQ x0, x0, +8 should be taken (both are 0)."""
        program = [
            0x00500093,  # ADDI x1, x0, 5
            0x00000463,  # BEQ  x0, x0, +8  (taken → skip next)
            0x06300093,  # ADDI x1, x0, 99  (SKIPPED)
            0x00A00113,  # ADDI x2, x0, 10
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=4)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[1], 5)   # x1 stays 5 (the 99 was skipped)
        self.assertEqual(regs[2], 10)  # x2 = 10

    def test_jal(self):
        """JAL x1, +8 should jump and save return address."""
        program = [
            0x008000EF,  # JAL  x1, +8  (jump to PC+8=8, x1 = PC+4=4)
            0x00A00113,  # ADDI x2, x0, 10  (SKIPPED)
            0x01400193,  # ADDI x3, x0, 20
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=3)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[1], 4)   # x1 = return addr = 4
        self.assertEqual(regs[2], 0)   # x2 = 0 (skipped)
        self.assertEqual(regs[3], 20)  # x3 = 20

    def test_lui(self):
        """LUI x1, 0x12345 → x1 = 0x12345000."""
        program = [
            0x12345037 | (1 << 7),  # LUI x1, 0x12345
        ]
        # Correct encoding: LUI rd=1, imm=0x12345
        # [31:12]=0x12345, [11:7]=00001, [6:0]=0110111
        program = [0x123450B7]  # LUI x1, 0x12345
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=1)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[1], 0x12345000)

    def test_zero_register_stays_zero(self):
        """x0 must always be 0 regardless of writes."""
        program = [
            0x00500013,  # ADDI x0, x0, 5  (writes to x0 — should be ignored)
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=1)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[0], 0)

    def test_pc_advances(self):
        """PC should advance by 4 each cycle for non-branch instructions."""
        states = run_simulation(self.cpu, num_cycles=3)
        for i, state in enumerate(states):
            expected_pc = hex(i * 4)
            self.assertEqual(state["fetch"]["pc"], f"0x{i * 4:08x}")

    def test_cycle_count(self):
        states = run_simulation(self.cpu, num_cycles=10)
        self.assertEqual(len(states), 10)

    def test_all_components_in_state(self):
        """Every component should appear in the cycle state."""
        states = run_simulation(self.cpu, num_cycles=1)
        expected = {"fetch", "imem", "decode", "regfile", "alu_mux",
                    "alu", "branch", "bpred", "dmem", "wb"}
        self.assertEqual(set(states[0].keys()) - {"_cycle"}, expected)


if __name__ == "__main__":
    unittest.main()
