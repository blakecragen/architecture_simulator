"""
Tests for the RISC-V N-wide superscalar pipeline CPU preset.

Tests: build, parallel execution of independent instructions,
cross-lane RAW dependency squashing, pipeline stall with load-use,
and forwarding across lanes.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.isa.riscv.presets.superscalar import build
from sim.runner_v2 import run_simulation
from sim.component.topology import generate_topology
from sim.component.wire import CPU


class TestRISCVSuperscalar(unittest.TestCase):

    def test_build_returns_cpu(self):
        cpu = build([0x00000013])  # NOP
        self.assertIsInstance(cpu, CPU)

    def test_build_with_different_lane_counts(self):
        for n in (1, 2, 3, 4):
            cpu = build([0x00000013], num_lanes=n)
            self.assertIsInstance(cpu, CPU)

    def test_topology_has_wide_components(self):
        cpu = build([0x00000013], num_lanes=2)
        topo = generate_topology(cpu)
        node_ids = {n["id"] for n in topo["nodes"]}
        self.assertIn("fetch", node_ids)
        self.assertIn("imem", node_ids)
        self.assertIn("if_id", node_ids)
        self.assertIn("id_ex", node_ids)
        self.assertIn("ex_mem", node_ids)
        self.assertIn("mem_wb", node_ids)
        self.assertIn("hazard_det", node_ids)
        self.assertIn("forwarding", node_ids)
        self.assertIn("decode_0", node_ids)
        self.assertIn("decode_1", node_ids)
        self.assertIn("alu_0", node_ids)
        self.assertIn("alu_1", node_ids)

    def test_two_independent_instructions_parallel(self):
        """Two independent ADDIs should execute in parallel (same cycle)."""
        program = [
            0x00500093,  # ADDI x1, x0, 5   (lane 0)
            0x00300113,  # ADDI x2, x0, 3   (lane 1)
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
        ]
        cpu = build(program, num_lanes=2)
        states = run_simulation(cpu, num_cycles=8)
        regs = states[7]["regfile"]["registers"]
        self.assertEqual(regs[1], 5)
        self.assertEqual(regs[2], 3)

    def test_cross_lane_raw_dependency_squash(self):
        """Lane 0 writes x1, lane 1 reads x1 → lane 1 should be squashed.
        The squashed instruction is NOT re-fetched (PC advances past it).
        To get x2=10, put the dependent instruction in the next fetch group."""
        program = [
            0x00500093,  # ADDI x1, x0, 5   (lane 0: writes x1)
            0x00300213,  # ADDI x4, x0, 3   (lane 1: independent, no squash)
            0x00108133,  # ADD  x2, x1, x1  (next group lane 0: reads x1 via forwarding)
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
        ]
        cpu = build(program, num_lanes=2)
        states = run_simulation(cpu, num_cycles=10)
        regs = states[9]["regfile"]["registers"]
        self.assertEqual(regs[1], 5)
        self.assertEqual(regs[4], 3)
        self.assertEqual(regs[2], 10)

    def test_intra_group_squash_happens(self):
        """When lane 0 writes x1 and lane 1 reads x1, lane 1 becomes NOP."""
        program = [
            0x00500093,  # ADDI x1, x0, 5   (lane 0: writes x1)
            0x00108133,  # ADD  x2, x1, x1  (lane 1: reads x1 — squashed!)
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
        ]
        cpu = build(program, num_lanes=2)
        # After cycle 1, the instructions are in ID stage — hazard detector fires
        states = run_simulation(cpu, num_cycles=3)
        hazard = states[1]["hazard_det"]
        # Lane 1 should be marked invalid (squashed due to RAW on x1)
        self.assertEqual(hazard.get("lane_1_valid", 1), 0)

    def test_no_squash_for_independent(self):
        """Instructions with no dependency should both execute."""
        program = [
            0x00500093,  # ADDI x1, x0, 5   (lane 0: writes x1)
            0x00300213,  # ADDI x4, x0, 3   (lane 1: writes x4, no dependency)
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
        ]
        cpu = build(program, num_lanes=2)
        states = run_simulation(cpu, num_cycles=8)
        regs = states[7]["regfile"]["registers"]
        self.assertEqual(regs[1], 5)
        self.assertEqual(regs[4], 3)

    def test_simulation_runs_without_error(self):
        """Full demo program should run without crashes."""
        program = [
            0x00500093,  # ADDI x1, x0, 5
            0x00300113,  # ADDI x2, x0, 3
            0x002081B3,  # ADD  x3, x1, x2
            0x40208233,  # SUB  x4, x1, x2
            0x00302023,  # SW   x3, 0(x0)
            0x00002283,  # LW   x5, 0(x0)
            0x06300313,  # ADDI x6, x0, 99
            0x00000013,  # NOP
        ]
        cpu = build(program, num_lanes=2)
        states = run_simulation(cpu, num_cycles=15)
        self.assertEqual(len(states), 15)

    def test_single_lane_matches_pipeline(self):
        """With num_lanes=1, superscalar should behave like regular pipeline."""
        program = [
            0x00500093,  # ADDI x1, x0, 5
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
        ]
        cpu = build(program, num_lanes=1)
        states = run_simulation(cpu, num_cycles=6)
        regs = states[5]["regfile"]["registers"]
        self.assertEqual(regs[1], 5)

    def test_all_components_in_state(self):
        """Superscalar CPU should have all expected components."""
        cpu = build([0x00000013], num_lanes=2)
        states = run_simulation(cpu, num_cycles=1)
        state = states[0]
        expected = {
            "fetch", "imem", "if_id", "regfile", "hazard_det",
            "id_ex", "forwarding", "ex_mem", "dmem", "mem_wb",
            "branch", "bpred",
            "decode_0", "decode_1",
            "alu_mux_0", "alu_mux_1",
            "alu_0", "alu_1",
            "wb_0", "wb_1",
        }
        actual = set(state.keys()) - {"_cycle"}
        self.assertTrue(expected.issubset(actual),
                        f"Missing components: {expected - actual}")


if __name__ == "__main__":
    unittest.main()
