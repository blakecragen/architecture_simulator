"""Regression tests for the three bugs found by the 2026-07 correctness audit.

Each pins a distinct, adversarially-verified defect so it can't silently return:

  1. Superscalar phantom-rs2 false hazard — the RISC-V decoder puts I-type
     immediate bits on the rs2 port; the cross-lane hazard detector treated them
     as a real register read, falsely squashing independent lanes when an
     immediate's low 5 bits equalled an earlier lane's destination register, so
     dependency-free work got SLOWER with more lanes. Fixed by gating rs2 with a
     "reads rs2 register" signal (cross_lane_hazard.py).
  2. x86 pipeline + branch predictor wrong result — a taken-predicted-but-not-
     taken branch recovered to pc + PREVIOUS instruction length (stale
     pc_plus_len), landing mid-instruction on variable-length x86 and skipping
     the fall-through. Fixed with a PcLenAdder fed by the fresh predecode length.
  3. Multicycle run_to_completion false settle — the settle heuristic
     (regfile+mem quiet for a window) fired mid-software-multiply and returned a
     wrong result flagged "completed". Fixed by sizing STABLE_WINDOW above the
     longest live quiet gap (runner_v2.py).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.harness import build_cpu, assemble, simulate, PRESETS, PREDICTORS
from sim.compiler import compile_c
from sim.runner_v2 import run_simulation, _arch_signature
from api.app import app


def _completion(states):
    final = _arch_signature(states[-1])
    last = 0
    for i, s in enumerate(states):
        if _arch_signature(s) != final:
            last = i
    return last + 1


class TestSuperscalarPhantomRs2(unittest.TestCase):
    """Independent ALU work must scale monotonically with lane width even when
    immediates collide with destination register numbers (bug #1)."""

    def _independent_colliding(self, n=8):
        # ADDI xK, x0, <imm> where imm's low 5 bits equal an earlier dest reg —
        # provably independent (every op reads x0), but the phantom rs2 == imm
        # low bits used to trip a false intra-group RAW squash.
        dest = list(range(1, n + 1))
        lines = [f"ADDI x{dest[k]}, x0, {dest[k-1] if k > 0 else 5}" for k in range(n)]
        return dest, assemble("riscv", "\n".join(lines))

    def test_wider_is_never_slower_on_independent_alu(self):
        dest, prog = self._independent_colliding()
        cycles = []
        for lanes in (1, 2, 3, 4, 6, 8):
            cpu = build_cpu("riscv/superscalar", prog, num_lanes=lanes)
            states = run_simulation(cpu, num_cycles=400, include_reset=True)
            regs = states[-1]["regfile"]["registers"]
            # results correct at every width
            for k in range(len(dest)):
                self.assertEqual(regs[dest[k]], dest[k-1] if k > 0 else 5)
            cycles.append(_completion(states))
        for a, b in zip(cycles, cycles[1:]):
            self.assertLessEqual(b, a,
                                 f"superscalar got SLOWER with more lanes on "
                                 f"independent work: {cycles}")
        # and width must actually help (not flat) on this parallel workload
        self.assertLess(cycles[-1], cycles[0], f"no width speedup: {cycles}")


class TestX86PipelinePredictorDeterminism(unittest.TestCase):
    """A branch predictor may change cycle count but NEVER the final result on
    the fully-modelled x86 pipeline (bug #2)."""

    JE_PROG = "MOV EAX, 5\nCMP EAX, 0\nJE skip\nMOV EBX, 7\nskip:\nMOV ECX, 9\n"

    def test_all_predictors_match_single_cycle_on_je_fallthrough(self):
        gt = simulate("x86", "single_cycle", asm=self.JE_PROG, cycles=80)
        self.assertEqual(gt.reg(3), 7)  # EBX = 7 (fall-through taken)
        for pred in (None, *PREDICTORS):
            r = simulate("x86", "pipeline", asm=self.JE_PROG, cycles=80,
                         branch_predictor=pred)
            self.assertEqual(r.reg(3), gt.reg(3),
                             f"x86 pipeline predictor {pred} changed EBX "
                             f"({r.reg(3)} != {gt.reg(3)})")

    def test_predictors_preserve_results_on_example_programs(self):
        root = os.path.join(os.path.dirname(__file__), "..")
        for rel in ("programs/x86/branch_prediction/if_else.asm",
                    "programs/x86/algorithms/factorial.asm",
                    "programs/x86/algorithms/gcd.asm"):
            path = os.path.join(root, rel)
            if not os.path.exists(path):
                continue
            text = open(path).read()
            ref = tuple(simulate("x86", "single_cycle", asm=text, cycles=2000).registers)
            for pred in ("always_taken", "bimodal", "gshare", "btb"):
                if pred not in PREDICTORS:
                    continue
                got = tuple(simulate("x86", "pipeline", asm=text, cycles=2000,
                                     branch_predictor=pred).registers)
                with self.subTest(program=rel, predictor=pred):
                    self.assertEqual(got, ref,
                                     f"{rel}: x86 pipeline+{pred} differs from single_cycle")


class TestMulticycleCompletionSettle(unittest.TestCase):
    """run_to_completion (until_stable) must not falsely settle mid-computation
    on a multicycle software-multiply and return a wrong result (bug #3)."""

    _RET_REG = {"riscv": 10, "arm": 0, "x86": 0}  # a0 / X0 / EAX

    def test_factorial_iter_multicycle_completes_correctly(self):
        src = open(os.path.join(os.path.dirname(__file__), "..",
                                "programs", "c", "factorial_iter.c")).read()
        for isa in ("riscv", "arm", "x86"):
            prog = assemble(isa, compile_c(src, isa).asm)
            cpu = build_cpu(f"{isa}/multicycle", prog)
            states = run_simulation(cpu, num_cycles=10000, include_reset=True,
                                    until_stable=True)
            regs = states[-1]["regfile"]["registers"]
            with self.subTest(isa=isa):
                self.assertEqual(regs[self._RET_REG[isa]], 120,
                                 f"{isa}/multicycle run_to_completion settled on "
                                 f"the wrong value (expected 120)")

    def test_run_to_completion_api_reports_correct_final_value(self):
        # The user-facing path: POST /simulate run_to_completion.
        client = app.test_client()
        asm = compile_c(open(os.path.join(os.path.dirname(__file__), "..",
                             "programs", "c", "factorial_iter.c")).read(), "riscv").asm
        resp = client.post("/simulate", json={
            "preset": "riscv/multicycle", "input_mode": "asm",
            "asm_text": asm, "run_to_completion": True}).get_json()
        self.assertTrue(resp.get("completed"))
        a0 = resp["cycles"][-1]["regfile"]["registers"][10]
        self.assertEqual(a0, 120, "run_to_completion reported a wrong 'completed' result")


if __name__ == "__main__":
    unittest.main()
