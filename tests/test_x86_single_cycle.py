"""
Tests for the x86-32 single-cycle CPU preset.

All instructions use real x86-32 machine code encodings.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.isa.x86.presets.single_cycle import build
from sim.runner_v2 import run_simulation
from sim.component.topology import generate_topology


class TestX86SingleCycle(unittest.TestCase):

    def test_build_returns_cpu(self):
        from sim.component.wire import CPU
        cpu = build([0x90])  # NOP
        self.assertIsInstance(cpu, CPU)

    def test_topology_structure(self):
        cpu = build([0x90])
        topo = generate_topology(cpu)
        node_ids = {n["id"] for n in topo["nodes"]}
        self.assertIn("fetch", node_ids)
        self.assertIn("decode", node_ids)
        self.assertIn("alu", node_ids)

    def test_nop_advances_pc_by_1(self):
        """NOP (0x90) is 1 byte, PC should advance by 1."""
        cpu = build([0x90, 0x90, 0x90])
        states = run_simulation(cpu, num_cycles=3)
        self.assertEqual(states[0]["fetch"]["pc"], "0x00000000")
        self.assertEqual(states[1]["fetch"]["pc"], "0x00000001")
        self.assertEqual(states[2]["fetch"]["pc"], "0x00000002")

    def test_mov_imm32(self):
        """MOV EAX, 42 → EAX = 42."""
        program = [0xB8, 0x2A, 0x00, 0x00, 0x00]  # MOV EAX, 42
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=1)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[0], 42)  # EAX

    def test_mov_imm32_ecx(self):
        """MOV ECX, 100 → ECX = 100."""
        program = [0xB9, 0x64, 0x00, 0x00, 0x00]  # MOV ECX, 100
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=1)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[1], 100)  # ECX

    def test_add_r32(self):
        """ADD EAX, ECX with EAX=10, ECX=3 → EAX=13."""
        program = [
            0xB8, 0x0A, 0x00, 0x00, 0x00,  # MOV EAX, 10
            0xB9, 0x03, 0x00, 0x00, 0x00,  # MOV ECX, 3
            0x01, 0xC8,                      # ADD EAX, ECX  (rm=EAX, reg=ECX)
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=3)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[0], 13)

    def test_sub_r32(self):
        """SUB EAX, ECX with EAX=10, ECX=3 → EAX=7."""
        program = [
            0xB8, 0x0A, 0x00, 0x00, 0x00,  # MOV EAX, 10
            0xB9, 0x03, 0x00, 0x00, 0x00,  # MOV ECX, 3
            0x29, 0xC8,                      # SUB EAX, ECX
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=3)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[0], 7)

    def test_and_or_xor(self):
        """Logical operations."""
        program = [
            0xB8, 0x0F, 0x00, 0x00, 0x00,  # MOV EAX, 15  (0b1111)
            0xB9, 0x0A, 0x00, 0x00, 0x00,  # MOV ECX, 10  (0b1010)
            0x89, 0xC2,                      # MOV EDX, EAX → EDX=15
            0x21, 0xCA,                      # AND EDX, ECX → EDX=10
            0x89, 0xC3,                      # MOV EBX, EAX → EBX=15
            0x09, 0xCB,                      # OR  EBX, ECX → EBX=15
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=6)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[2], 10)   # EDX = AND
        self.assertEqual(regs[3], 15)   # EBX = OR

    def test_mov_reg_reg(self):
        """MOV EDX, EAX copies EAX to EDX."""
        program = [
            0xB8, 0x2A, 0x00, 0x00, 0x00,  # MOV EAX, 42
            0x89, 0xC2,                      # MOV EDX, EAX (89: r/m=EDX, reg=EAX)
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=2)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[2], 42)  # EDX

    def test_add_imm8(self):
        """ADD EAX, 5 via 83 /0."""
        program = [
            0xB8, 0x0A, 0x00, 0x00, 0x00,  # MOV EAX, 10
            0x83, 0xC0, 0x05,                # ADD EAX, 5
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=2)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[0], 15)

    def test_sub_imm8(self):
        """SUB EAX, 3 via 83 /5."""
        program = [
            0xB8, 0x0A, 0x00, 0x00, 0x00,  # MOV EAX, 10
            0x83, 0xE8, 0x03,                # SUB EAX, 3
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=2)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[0], 7)

    def test_jmp_rel8(self):
        """JMP +2 skips 2 bytes (next 2 NOPs)."""
        program = [
            0xEB, 0x02,  # JMP +2 (skip 2 bytes after this instruction)
            0x90,        # NOP (skipped)
            0x90,        # NOP (skipped)
            0xB8, 0x63, 0x00, 0x00, 0x00,  # MOV EAX, 99
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=2)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[0], 99)

    def test_je_taken(self):
        """JE taken when CMP result is zero."""
        program = [
            0xB8, 0x05, 0x00, 0x00, 0x00,  # MOV EAX, 5
            0x83, 0xF8, 0x05,                # CMP EAX, 5
            0x74, 0x01,                      # JE  +1  (taken: 5==5)
            0x90,                            # NOP (skipped)
            0xB9, 0x63, 0x00, 0x00, 0x00,  # MOV ECX, 99
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=4)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[1], 99)

    def test_je_not_taken(self):
        """JE not taken when values differ."""
        program = [
            0xB8, 0x05, 0x00, 0x00, 0x00,  # MOV EAX, 5
            0x83, 0xF8, 0x03,                # CMP EAX, 3
            0x74, 0x05,                      # JE  +5  (not taken: 5!=3)
            0xB9, 0x63, 0x00, 0x00, 0x00,  # MOV ECX, 99 (executed)
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=4)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[1], 99)

    def test_variable_length_pc_advance(self):
        """PC advances by correct instruction length for mixed-size instructions."""
        program = [
            0xB8, 0x01, 0x00, 0x00, 0x00,  # MOV EAX, 1  (5 bytes: PC 0→5)
            0x90,                            # NOP         (1 byte:  PC 5→6)
            0x83, 0xC0, 0x02,                # ADD EAX, 2  (3 bytes: PC 6→9)
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=3)
        self.assertEqual(states[0]["fetch"]["pc"], "0x00000000")
        self.assertEqual(states[1]["fetch"]["pc"], "0x00000005")
        self.assertEqual(states[2]["fetch"]["pc"], "0x00000006")

    def test_all_components_in_state(self):
        """Every component should appear in the cycle state."""
        cpu = build([0x90])
        states = run_simulation(cpu, num_cycles=1)
        expected = {"fetch", "imem", "decode", "regfile", "alu_mux",
                    "alu", "flags_reg", "branch", "bpred", "dmem", "wb"}
        self.assertEqual(set(states[0].keys()) - {"_cycle"}, expected)


if __name__ == "__main__":
    unittest.main()
