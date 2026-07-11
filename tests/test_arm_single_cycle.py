"""
Tests for the ARM AArch64 single-cycle CPU preset.

All instructions use real A64 machine code encodings.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.isa.arm.presets.single_cycle import build
from sim.runner_v2 import run_simulation
from sim.component.topology import generate_topology


class TestARMSingleCycle(unittest.TestCase):

    def test_build_returns_cpu(self):
        from sim.component.wire import CPU
        cpu = build([0xD503201F])  # NOP
        self.assertIsInstance(cpu, CPU)

    def test_topology_structure(self):
        cpu = build([0xD503201F])
        topo = generate_topology(cpu)
        node_ids = {n["id"] for n in topo["nodes"]}
        self.assertIn("fetch", node_ids)
        self.assertIn("decode", node_ids)
        self.assertIn("alu", node_ids)

    def test_movz(self):
        """MOVZ X1, #10 → X1 = 10."""
        program = [0xD2800141]  # MOVZ X1, #10
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=1)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[1], 10)

    def test_add_reg(self):
        """ADD X3, X1, X2 with X1=10, X2=3 → X3=13."""
        program = [
            0xD2800141,  # MOVZ X1, #10
            0xD2800062,  # MOVZ X2, #3
            0x8B020023,  # ADD  X3, X1, X2
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=3)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[1], 10)
        self.assertEqual(regs[2], 3)
        self.assertEqual(regs[3], 13)

    def test_sub_reg(self):
        """SUB X4, X1, X2 with X1=10, X2=3 → X4=7."""
        program = [
            0xD2800141,  # MOVZ X1, #10
            0xD2800062,  # MOVZ X2, #3
            0xCB020024,  # SUB  X4, X1, X2
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=3)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[4], 7)

    def test_and_orr_eor(self):
        """Logical operations."""
        program = [
            0xD28001E1,  # MOVZ X1, #15   (0b1111)
            0xD2800142,  # MOVZ X2, #10   (0b1010)
            0x8A020023,  # AND  X3, X1, X2  → 10 (0b1010)
            0xAA020024,  # ORR  X4, X1, X2  → 15 (0b1111)
            0xCA020025,  # EOR  X5, X1, X2  → 5  (0b0101)
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=5)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[3], 10)
        self.assertEqual(regs[4], 15)
        self.assertEqual(regs[5], 5)

    def test_add_imm(self):
        """ADD X2, X1, #5 with X1=10 → X2=15."""
        program = [
            0xD2800141,  # MOVZ X1, #10
            0x91001422,  # ADD  X2, X1, #5
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=2)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[2], 15)

    def test_str_ldr(self):
        """STR/LDR with unsigned offset."""
        program = [
            0xD28001A1,  # MOVZ X1, #13
            0xF9000001,  # STR  X1, [X0, #0]  → mem[0] = 13
            0xF9400002,  # LDR  X2, [X0, #0]  → X2 = 13
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=3)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[2], 13)

    def test_b_unconditional(self):
        """B +8 skips one instruction."""
        program = [
            0xD2800141,  # MOVZ X1, #10
            0x14000002,  # B    +8  (skip next)
            0xD28018C1,  # MOVZ X1, #198  (SKIPPED)
            0xD2800062,  # MOVZ X2, #3
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=4)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[1], 10)   # NOT overwritten
        self.assertEqual(regs[2], 3)

    def test_bl_sets_link_register(self):
        """BL saves return address in X30."""
        program = [
            0x94000002,  # BL +8  (X30 = PC+4 = 4, jump to PC=8)
            0xD503201F,  # NOP (SKIPPED)
            0xD2800141,  # MOVZ X1, #10
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=3)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[30], 4)   # link register
        self.assertEqual(regs[1], 10)

    def test_cbz_taken(self):
        """CBZ X0, +8 — X0 is zero so branch taken."""
        program = [
            0xB4000040,  # CBZ X0, +8
            0xD28018C1,  # MOVZ X1, #198 (SKIPPED)
            0xD2800142,  # MOVZ X2, #10
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=3)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[1], 0)    # skipped
        self.assertEqual(regs[2], 10)

    def test_cbz_not_taken(self):
        """CBZ X1, +8 — X1=5, not zero, branch not taken."""
        program = [
            0xD28000A1,  # MOVZ X1, #5
            0xB4000041,  # CBZ X1, +8    (not taken: X1=5)
            0xD2800142,  # MOVZ X2, #10  (executed)
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=3)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[2], 10)

    def test_xzr_stays_zero(self):
        """XZR (X31) is always zero."""
        program = [
            # SUBS XZR, X0, X0 (CMP X0, X0 — writes to XZR which is discarded)
            0xEB00001F,
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=1)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[31], 0)

    def test_x0_is_writable(self):
        """X0 is a normal writable register in ARM (unlike RISC-V)."""
        program = [
            0xD2800140,  # MOVZ X0, #10
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=1)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[0], 10)

    def test_xzr_write_discarded(self):
        """Writing to XZR (X31) is discarded — it always reads as zero."""
        program = [
            0xD2800141,  # MOVZ X1, #10
            0xD280015F,  # MOVZ XZR, #10  (XZR = X31, write discarded)
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=2)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[1], 10)
        self.assertEqual(regs[31], 0)  # XZR must stay zero

    def test_pc_advances(self):
        """PC advances by 4 each cycle."""
        program = [0xD503201F] * 4  # 4 NOPs
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=3)
        for i, state in enumerate(states):
            self.assertEqual(state["fetch"]["pc"], f"0x{i * 4:08x}")


if __name__ == "__main__":
    unittest.main()
