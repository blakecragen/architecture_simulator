"""
Tests for the RISC-V 5-stage pipeline CPU preset.

Pipeline adds latency: results appear N cycles later than single-cycle.
Stage pipeline: IF(1) → ID(2) → EX(3) → MEM(4) → WB(5)
An instruction committed in WB writes the register file on rising_edge of cycle 5+.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.isa.riscv.presets.pipeline import build
from sim.runner_v2 import run_simulation
from sim.component.topology import generate_topology


class TestRISCVPipeline(unittest.TestCase):

    def test_build_returns_cpu(self):
        from sim.component.wire import CPU
        cpu = build([0x00000013])  # NOP
        self.assertIsInstance(cpu, CPU)

    def test_topology_has_pipeline_registers(self):
        cpu = build([0x00000013])
        topo = generate_topology(cpu)
        node_ids = {n["id"] for n in topo["nodes"]}
        self.assertIn("if_id", node_ids)
        self.assertIn("id_ex", node_ids)
        self.assertIn("ex_mem", node_ids)
        self.assertIn("mem_wb", node_ids)
        self.assertIn("hazard_det", node_ids)
        self.assertIn("forwarding", node_ids)

    def test_addi_pipeline_latency(self):
        """ADDI x1, x0, 5 — result visible in regfile after pipeline fills."""
        program = [
            0x00500093,  # ADDI x1, x0, 5
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
        ]
        cpu = build(program)
        # Pipeline: cycle 1=IF, 2=ID, 3=EX, 4=MEM, 5=WB (writes on rising_edge)
        # Register should be updated after cycle 5
        states = run_simulation(cpu, num_cycles=6)
        regs = states[5]["regfile"]["registers"]
        self.assertEqual(regs[1], 5)

    def test_data_forwarding(self):
        """Back-to-back ADDIs should work via forwarding."""
        program = [
            0x00500093,  # ADDI x1, x0, 5    → x1 = 5
            0x00300113,  # ADDI x2, x0, 3    → x2 = 3
            0x002081B3,  # ADD  x3, x1, x2   → x3 = 8 (forwarded)
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=8)
        regs = states[7]["regfile"]["registers"]
        self.assertEqual(regs[1], 5)
        self.assertEqual(regs[2], 3)
        self.assertEqual(regs[3], 8)

    def test_load_use_stall(self):
        """LW followed by immediate use of loaded value needs a stall + forwarding."""
        program = [
            0x00500093,  # ADDI x1, x0, 5
            0x00102023,  # SW   x1, 0(x0)     → mem[0] = 5
            0x00000013,  # NOP  (avoid hazard with SW)
            0x00002103,  # LW   x2, 0(x0)     → x2 = 5
            0x00000013,  # NOP  (load-use bubble)
            0x002081B3,  # ADD  x3, x1, x2    → x3 = 10 (needs x2 from load)
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=14)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[1], 5)
        self.assertEqual(regs[2], 5)
        self.assertEqual(regs[3], 10)

    def test_all_components_in_state(self):
        """Pipeline CPU should have all expected components."""
        cpu = build([0x00000013])
        states = run_simulation(cpu, num_cycles=1)
        expected = {
            "fetch", "imem", "if_id", "decode", "regfile", "hazard_det",
            "id_ex", "forwarding", "alu_mux", "alu", "ex_mem",
            "branch", "dmem", "mem_wb", "wb", "bpred",
        }
        self.assertEqual(set(states[0].keys()) - {"_cycle"}, expected)

    def test_branch_flush(self):
        """JAL should flush instructions in the pipeline after the jump."""
        program = [
            0x00500093,  # ADDI x1, x0, 5     (executes)
            0x00C000EF,  # JAL  x1, +12        (jump to PC=16 after pipeline)
            0x06300093,  # ADDI x1, x0, 99     (should be flushed)
            0x06300093,  # ADDI x1, x0, 99     (should be flushed)
            0x00A00113,  # ADDI x2, x0, 10     (target: PC=16)
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=12)
        regs = states[-1]["regfile"]["registers"]
        # x2 should be 10 (the branch target ran).
        self.assertEqual(regs[2], 10)
        # The two bogus "ADDI x1, x0, 99" after the JAL MUST be flushed: a broken
        # flush would let them commit and clobber x1 with 99. Assert they did NOT
        # run, and that x1 holds the JAL link value (PC+4 = 4+4 = 8) instead.
        self.assertNotEqual(regs[1], 99)
        self.assertEqual(regs[1], 8)


if __name__ == "__main__":
    unittest.main()
