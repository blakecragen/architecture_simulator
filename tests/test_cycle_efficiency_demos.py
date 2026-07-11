"""Cycle-efficiency demo programs: correctness + pinned cross-model cycle counts.

These programs (programs/riscv/cycle_efficiency/*.asm) are crafted to make the
execution models diverge in instructive ways. This test is two things at once:

  1. A CORRECTNESS net: every model must compute the SAME final architectural
     state (registers + full data memory) for each program.
  2. A CYCLE-COUNTING guardrail: the exact cycles-to-complete per model are
     pinned, and the qualitative orderings that the programs are meant to teach
     are asserted. If a future change silently alters cycle accounting, this
     flags it for review.

"cycles-to-complete" = 1 + the index of the last cycle whose architectural
signature (registers + full memory, incl. the sparse high map) changes.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.harness import build_cpu, assemble
from sim.runner_v2 import run_simulation, _arch_signature

PROG_DIR = os.path.join(os.path.dirname(__file__), "..",
                        "programs", "riscv", "cycle_efficiency")

BUDGET = 1500  # generous; every demo settles well within this


def _load(name):
    with open(os.path.join(PROG_DIR, name)) as f:
        return assemble("riscv", f.read())


def _completion(states):
    final = _arch_signature(states[-1])
    last = 0
    for i, s in enumerate(states):
        if _arch_signature(s) != final:
            last = i
    return last + 1


def _final(cpu, states):
    regs = None
    for s in reversed(states):
        rf = s.get("regfile")
        if rf and "registers" in rf:
            regs = tuple(rf["registers"])
            break
    mem = tuple((i, v) for i, v in enumerate(cpu.components["dmem"]._mem) if v)
    return regs, mem


def _run(model, prog, **kw):
    cpu = build_cpu(f"riscv/{model}", prog, **kw)
    states = run_simulation(cpu, num_cycles=BUDGET, include_reset=True)
    return cpu, states


# Pinned cycles-to-complete. Keys: model or (superscalar, lanes). Update
# deliberately (with a comment) if an intentional microarch change moves them.
PINNED = {
    "ilp_parallel.asm": {
        "single_cycle": 16, "multicycle": 48, "pipeline": 20, "ooo": 18,
        ("superscalar", 2): 12, ("superscalar", 4): 8,
    },
    "dependency_chain.asm": {
        "single_cycle": 16, "multicycle": 48, "pipeline": 20, "ooo": 18,
        ("superscalar", 2): 35, ("superscalar", 4): 35,
    },
    "mem_parallel.asm": {
        "single_cycle": 16, "multicycle": 56, "pipeline": 19, "ooo": 18,
        ("superscalar", 2): 11, ("superscalar", 4): 7,
    },
    "branch_loop.asm": {
        "single_cycle": 34, "multicycle": 103, "pipeline": 64, "ooo": 56,
        ("superscalar", 2): 55, ("superscalar", 4): 64,
    },
}

# Expected final architectural results (the oracle).
EXPECTED_REGS = {
    "ilp_parallel.asm": {1: 100, 2: 200, **{r: r for r in range(3, 17)}},
    "dependency_chain.asm": {1: 32768},
    "mem_parallel.asm": {r: r * 3 for r in range(1, 9)},
    "branch_loop.asm": {1: 45},
}
EXPECTED_MEM = {  # word_index -> value
    "mem_parallel.asm": {i: (i + 1) * 3 for i in range(8)},
    "branch_loop.asm": {0: 45},
}


def _cfg(model_key):
    if isinstance(model_key, tuple):
        return model_key[0], {"num_lanes": model_key[1]}
    return model_key, {}


class TestCycleEfficiencyDemos(unittest.TestCase):

    def test_all_models_agree_on_final_state(self):
        """Every model computes the SAME registers + memory for each demo."""
        for fname in PINNED:
            prog = _load(fname)
            ref = None
            for model_key in PINNED[fname]:
                model, kw = _cfg(model_key)
                cpu, states = _run(model, prog, **kw)
                got = _final(cpu, states)
                with self.subTest(program=fname, model=model_key):
                    if ref is None:
                        ref = got
                    else:
                        self.assertEqual(got, ref,
                                         f"{fname}: {model_key} diverges from single_cycle")

    def test_expected_results(self):
        """single_cycle (the oracle) produces the documented values."""
        for fname, regs in EXPECTED_REGS.items():
            prog = _load(fname)
            cpu, states = _run("single_cycle", prog)
            got_regs, _ = _final(cpu, states)
            for idx, val in regs.items():
                with self.subTest(program=fname, reg=idx):
                    self.assertEqual(got_regs[idx], val)
            mem = cpu.components["dmem"]._mem
            for word, val in EXPECTED_MEM.get(fname, {}).items():
                with self.subTest(program=fname, mem_word=word):
                    self.assertEqual(mem[word], val)

    def test_pinned_cycle_counts(self):
        """Cycles-to-complete match the values documented in the .asm headers."""
        for fname, table in PINNED.items():
            prog = _load(fname)
            for model_key, expected in table.items():
                model, kw = _cfg(model_key)
                _, states = _run(model, prog, **kw)
                with self.subTest(program=fname, model=model_key):
                    self.assertEqual(_completion(states), expected,
                                     f"{fname}/{model_key}: cycle count moved")

    def test_teaching_orderings(self):
        """The qualitative points the demos exist to make, as invariants."""
        def cyc(fname, model_key):
            model, kw = _cfg(model_key)
            _, states = _run(model, _load(fname), **kw)
            return _completion(states)

        # ILP: width pays off, and multicycle costs more than single-cycle.
        self.assertLess(cyc("ilp_parallel.asm", ("superscalar", 4)),
                        cyc("ilp_parallel.asm", ("superscalar", 2)))
        self.assertLess(cyc("ilp_parallel.asm", ("superscalar", 2)),
                        cyc("ilp_parallel.asm", "single_cycle"))
        self.assertGreater(cyc("ilp_parallel.asm", "multicycle"),
                           cyc("ilp_parallel.asm", "single_cycle"))

        # DEP: no ILP -> extra lanes give ZERO benefit.
        self.assertEqual(cyc("dependency_chain.asm", ("superscalar", 4)),
                         cyc("dependency_chain.asm", ("superscalar", 2)))

        # MEM (the multi-port fix): independent stores scale with width, and
        # 4 lanes is never slower than 2 (the bug the fix removed).
        self.assertLess(cyc("mem_parallel.asm", ("superscalar", 4)),
                        cyc("mem_parallel.asm", ("superscalar", 2)))
        self.assertLess(cyc("mem_parallel.asm", ("superscalar", 2)),
                        cyc("mem_parallel.asm", "single_cycle"))

        # LOOP: the pipeline pays a branch penalty single-cycle never sees.
        self.assertGreater(cyc("branch_loop.asm", "pipeline"),
                           cyc("branch_loop.asm", "single_cycle"))

    def test_branch_prediction_speeds_up_loop(self):
        """A predictor cuts the pipeline's loop cycles (result unchanged)."""
        prog = _load("branch_loop.asm")
        _, base = _run("pipeline", prog)
        cpu_p = build_cpu("riscv/pipeline", prog, branch_predictor="bimodal")
        pred = run_simulation(cpu_p, num_cycles=BUDGET, include_reset=True)
        self.assertLess(_completion(pred), _completion(base))
        self.assertEqual(cpu_p.components["regfile"].get_state()["registers"][1], 45)


if __name__ == "__main__":
    unittest.main()
