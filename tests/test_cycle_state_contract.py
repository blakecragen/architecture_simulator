"""Cycle-state CONTRACT tests.

Philosophy: the backend must carry *all* the truth every cycle — data memory,
registers, the fetched instruction/PC, and a complete, serialisable snapshot of
every component — so the front-end is a pure renderer. These tests pin that
contract so display bugs can't hide a backend that silently failed to update
state.

All five RISC-V models are covered strictly (the historical superscalar
same-group store-drop / cross-lane forwarding gaps have been fixed, so the
former xfail is gone and superscalar is asserted like the others).
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.assembler import assemble
from sim.runner_v2 import run_simulation
from api.app import PRESETS, ISA_CONFIGS

# Models whose architectural state is verified to be correct.
# (RISC-V is the reference ISA used by the strict tests below; all five of its
# models now agree.)
CORRECT_MODELS = ["single_cycle", "multicycle", "pipeline", "ooo", "superscalar"]

# A compute-and-store program: base=40 (0x28 -> words 10,11,12); stores 11/22/33,
# then x4 = 11+22 = 33 and x5 = load(mem[10]) = 11.
RISCV_MEM_PROGRAM = """
    ADDI x20, x0, 40
    ADDI x1, x0, 11
    ADDI x2, x0, 22
    ADDI x3, x0, 33
    SW   x1, 0(x20)
    SW   x2, 4(x20)
    SW   x3, 8(x20)
    ADD  x4, x1, x2
    LW   x5, 0(x20)
    NOP
    NOP
    NOP
    NOP
"""


def _build(preset_key, program, num_lanes=2):
    p = PRESETS[preset_key]
    if p["model"] == "superscalar":
        return p["build"](program, num_lanes=num_lanes)
    return p["build"](program)


def _last_with(states, comp, field):
    for s in reversed(states):
        if comp in s and field in s[comp]:
            return s[comp][field]
    return None


class TestCycleStateCompleteness(unittest.TestCase):
    """Every component emits a complete, JSON-serialisable snapshot every cycle."""

    def test_all_presets_emit_every_component_every_cycle(self):
        for key, p in sorted(PRESETS.items()):
            isa_cfg = ISA_CONFIGS[p["isa"]]
            program = isa_cfg.demo_program()
            cpu = _build(key, program)
            states = run_simulation(cpu, num_cycles=12, include_reset=True)
            expected = set(cpu.components.keys())
            for i, s in enumerate(states):
                with self.subTest(preset=key, cycle=i):
                    self.assertEqual(set(s.keys()) - {"_cycle"}, expected,
                                     f"{key} cycle {i}: state keys != component set")
                    self.assertEqual(s["_cycle"], i, "cycle index must be present + monotonic")
                    # Must be JSON-serialisable so the API can return it verbatim.
                    json.dumps(s)


class TestMemoryReflectsStores(unittest.TestCase):
    """Data memory in the cycle state reflects committed stores."""

    def test_stores_land_in_memory(self):
        prog = assemble("riscv", RISCV_MEM_PROGRAM)
        for model in CORRECT_MODELS:
            cpu = _build(f"riscv/{model}", prog)
            states = run_simulation(cpu, num_cycles=80, include_reset=True)
            mem = _last_with(states, "dmem", "memory")
            with self.subTest(model=model):
                self.assertIsNotNone(mem, "dmem.memory must be present in cycle state")
                self.assertEqual((mem[10], mem[11], mem[12]), (11, 22, 33),
                                 f"{model}: stores not reflected in data memory")

    def test_single_cycle_store_visible_on_commit_cycle(self):
        # mem[word 25] (byte 100) gets 10 on the SW cycle and stays.
        prog = assemble("riscv", """
            ADDI x20, x0, 100
            ADDI x1, x0, 10
            SW   x1, 0(x20)
            NOP
        """)
        cpu = _build("riscv/single_cycle", prog)
        states = run_simulation(cpu, num_cycles=8, include_reset=True)
        wrote = [i for i, s in enumerate(states) if s["dmem"]["memory"][25] == 10]
        self.assertTrue(wrote, "store value never appeared in dmem.memory")
        # Once written it must persist for every later cycle.
        first = wrote[0]
        for s in states[first:]:
            self.assertEqual(s["dmem"]["memory"][25], 10)


class TestRegistersReflectComputation(unittest.TestCase):
    """Register file in the cycle state reflects computed/loaded values."""

    def test_registers_match_across_correct_models(self):
        prog = assemble("riscv", RISCV_MEM_PROGRAM)
        for model in CORRECT_MODELS:
            cpu = _build(f"riscv/{model}", prog)
            states = run_simulation(cpu, num_cycles=80, include_reset=True)
            regs = _last_with(states, "regfile", "registers")
            with self.subTest(model=model):
                self.assertIsNotNone(regs)
                self.assertEqual(regs[1], 11)
                self.assertEqual(regs[4], 33, f"{model}: x4 = x1 + x2 should be 33")
                self.assertEqual(regs[5], 11, f"{model}: x5 = load(mem[base]) should be 11")


class TestInstructionTracking(unittest.TestCase):
    """The fetched PC / instruction is tracked correctly each cycle."""

    def test_pc_and_instruction_advance(self):
        # Straight-line program (no branches): PC steps by 4, imem.data == program[pc/4].
        prog = assemble("riscv", """
            ADDI x1, x0, 1
            ADDI x2, x0, 2
            ADDI x3, x0, 3
            ADDI x4, x0, 4
        """)
        cpu = _build("riscv/single_cycle", prog)
        states = run_simulation(cpu, num_cycles=len(prog), include_reset=True)
        # Reset cycle is index 0; instructions execute from cycle 1 on.
        for i, instr in enumerate(prog):
            s = states[i + 1]
            pc = int(s["fetch"]["pc"], 16)
            self.assertEqual(pc, i * 4, f"PC at cycle {i+1} should be {i*4:#x}")
            self.assertEqual(int(s["imem"]["data"], 16), instr,
                             "fetched instruction must match the program at PC")


class TestCrossModelArchState(unittest.TestCase):
    """Final architectural state (registers + memory) agrees across the four
    correct models — a strong net against any one model silently diverging."""

    def _final(self, model, prog):
        cpu = _build(f"riscv/{model}", prog)
        states = run_simulation(cpu, num_cycles=90, include_reset=True)
        regs = _last_with(states, "regfile", "registers")
        mem = _last_with(states, "dmem", "memory")
        return regs, mem[:16]

    def test_all_correct_models_agree(self):
        prog = assemble("riscv", RISCV_MEM_PROGRAM)
        ref_regs, ref_mem = self._final("single_cycle", prog)
        for model in CORRECT_MODELS[1:]:
            regs, mem = self._final(model, prog)
            with self.subTest(model=model):
                self.assertEqual(regs, ref_regs, f"{model} registers differ from single_cycle")
                self.assertEqual(mem, ref_mem, f"{model} memory differs from single_cycle")


class TestSuperscalarMemoryAndForwarding(unittest.TestCase):
    """Superscalar (RISC-V) now serialises same-group memory ops, forwards
    across lanes, and writes back loads — verified at several lane widths.
    (x86/superscalar is excluded: it reuses the RISC-V decoder on a byte
    stream and is illustrative-only — see the matrix tests for that gap.)"""

    def test_stores_and_forwarding_at_multiple_widths(self):
        prog = assemble("riscv", RISCV_MEM_PROGRAM)
        for num_lanes in (1, 2, 3, 4):
            cpu = _build("riscv/superscalar", prog, num_lanes=num_lanes)
            states = run_simulation(cpu, num_cycles=120, include_reset=True)
            mem = _last_with(states, "dmem", "memory")
            regs = _last_with(states, "regfile", "registers")
            with self.subTest(num_lanes=num_lanes):
                self.assertEqual((mem[10], mem[11], mem[12]), (11, 22, 33),
                                 "same-group stores must all reach memory")
                self.assertEqual(regs[4], 33, "cross-lane forwarding: x4 = x1 + x2")
                self.assertEqual(regs[5], 11, "load must write back: x5 = mem[base]")


if __name__ == "__main__":
    unittest.main()
