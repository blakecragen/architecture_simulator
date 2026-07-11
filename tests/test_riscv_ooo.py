"""
Tests for the RISC-V Out-of-Order CPU preset.

The OoO model adds latency (dispatch → execute → commit) compared to
single-cycle, so programs need extra NOP padding and more cycles to
allow all instructions to commit through the ROB.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.isa.riscv.presets.ooo import build
from sim.runner_v2 import run_simulation
from sim.component.topology import generate_topology


class TestRISCVOoO(unittest.TestCase):

    def test_build_returns_cpu(self):
        """build() should return a CPU instance."""
        from sim.component.wire import CPU
        cpu = build([0x00000013])  # NOP
        self.assertIsInstance(cpu, CPU)

    def test_topology_has_ooo_components(self):
        """Topology graph should include ROB, RS, and RAT nodes."""
        cpu = build([0x00000013])
        topo = generate_topology(cpu)
        ids = {n["id"] for n in topo["nodes"]}
        self.assertIn("rob", ids)
        self.assertIn("rs", ids)
        self.assertIn("rat", ids)

    def test_topology_has_standard_components(self):
        """OoO preset should still include all standard components."""
        cpu = build([0x00000013])
        topo = generate_topology(cpu)
        ids = {n["id"] for n in topo["nodes"]}
        for name in ("fetch", "imem", "decode", "regfile",
                      "alu_mux", "alu", "branch", "bpred", "dmem", "wb"):
            self.assertIn(name, ids)

    def test_topology_edges(self):
        """OoO preset should have wires connecting OoO components."""
        cpu = build([0x00000013])
        topo = generate_topology(cpu)
        edge_strs = {f"{e['from']}->{e['to']}" for e in topo["edges"]}
        # ROB dispatch_tag should feed RAT and RS
        self.assertIn("rob.dispatch_tag->rat.alloc_tag", edge_strs)
        self.assertIn("rob.dispatch_tag->rs.issue_rob_tag", edge_strs)
        # CDB broadcast
        self.assertIn("rs.exec_valid->rob.complete_en", edge_strs)

    def test_basic_execution(self):
        """ADDI x1, x0, 5 should eventually commit through the ROB."""
        program = [
            0x00500093,  # ADDI x1, x0, 5
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=10)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[1], 5)

    def test_two_independent_addis(self):
        """Two independent ADDI instructions should both commit."""
        program = [
            0x00500093,  # ADDI x1, x0, 5
            0x00300113,  # ADDI x2, x0, 3
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=12)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[1], 5)
        self.assertEqual(regs[2], 3)

    def test_dependency_resolution(self):
        """Back-to-back dependent instructions: ADD x3, x1, x2."""
        program = [
            0x00500093,  # ADDI x1, x0, 5
            0x00300113,  # ADDI x2, x0, 3
            0x002081B3,  # ADD  x3, x1, x2
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=15)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[1], 5)
        self.assertEqual(regs[2], 3)
        self.assertEqual(regs[3], 8)

    def test_zero_register_stays_zero(self):
        """x0 must remain 0 even through OoO dispatch/commit."""
        program = [
            0x00500013,  # ADDI x0, x0, 5 (writes to x0 -- ignored)
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=8)
        regs = states[-1]["regfile"]["registers"]
        self.assertEqual(regs[0], 0)

    def test_all_components_in_state(self):
        """Every component should appear in the cycle state dictionary."""
        cpu = build([0x00000013])
        states = run_simulation(cpu, num_cycles=1)
        expected = {
            "fetch", "imem", "decode", "rat", "regfile", "rob", "rs",
            "alu_mux", "alu", "branch_alu", "branch", "bpred", "dmem", "wb",
            "store_commit", "dispatch_gate", "pc_src", "cdb_val",
        }
        self.assertEqual(set(states[0].keys()) - {"_cycle"}, expected)

    def test_rob_state_tracked(self):
        """ROB should show entries in its state after dispatch."""
        program = [
            0x00500093,  # ADDI x1, x0, 5
            0x00000013,  # NOP
        ]
        cpu = build(program)
        states = run_simulation(cpu, num_cycles=3)
        # The ROB state should have entry tracking info
        rob_state = states[0]["rob"]
        self.assertIn("entries", rob_state)
        self.assertIn("head", rob_state)
        self.assertIn("tail", rob_state)


if __name__ == "__main__":
    unittest.main()
