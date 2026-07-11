"""The Configurable execution model (per-instruction-class cycle budgets).

Reuses the single-cycle datapath but holds each instruction for a configurable
number of cycles, committing once on its final cycle. Pins:
  * it AGREES with the single-cycle oracle on results for any cost config (that's
    the whole design — only the cycle COUNT changes);
  * all-1s reproduces single-cycle's cycle count exactly, and the FetDecExe
    profile {3,4,4,3} reproduces the multicycle model's cycle count;
  * higher per-class budgets cost more cycles;
  * the time model (clock period = busiest cycle; time = cycles x period) makes
    single-cycle the fewest-cycles / slowest-clock design.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.harness import PRESETS, MODELS, build_cpu, assemble, simulate
from sim.runner_v2 import run_simulation, _arch_signature
from sim.components.multicycle.budget_controller import (
    clock_period, estimate_time, FETDECEXE_COSTS, DEFAULT_COSTS)
from api.app import app

# A program touching all four classes: ALU, store, load, branch (a summing loop).
ASM = """
    ADDI x1, x0, 0
    ADDI x2, x0, 0
    ADDI x3, x0, 5
    ADDI x20, x0, 40
loop:
    ADD  x1, x1, x2
    SW   x1, 0(x20)
    LW   x4, 0(x20)
    ADDI x2, x2, 1
    BLT  x2, x3, loop
    ADD  x1, x1, x4
"""


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


def _run(isa, model, prog, cycle_costs=None, budget=4000):
    cpu = build_cpu(f"{isa}/{model}", prog, cycle_costs=cycle_costs)
    states = run_simulation(cpu, num_cycles=budget, include_reset=True)
    return cpu, states


class TestRegistry(unittest.TestCase):
    def test_configurable_present_for_all_isas(self):
        self.assertIn("configurable", MODELS)
        for isa in ("riscv", "arm", "x86"):
            self.assertIn(f"{isa}/configurable", PRESETS)


class TestOracleAgreement(unittest.TestCase):
    """Configurable must compute the SAME result as single-cycle for any config."""

    # Core-C so it assembles correctly on every ISA (touches ALU, loads/stores
    # via the array, and branches via the loop).
    C_SRC = ("int main(){int a[4]; int i; int s=0;"
             "for(i=0;i<4;i++) a[i]=i*2;"
             "for(i=0;i<4;i++) s+=a[i]; return s;}")   # -> 12

    COSTS = [
        {"alu": 1, "load": 1, "store": 1, "branch": 1},
        dict(FETDECEXE_COSTS),
        {"alu": 1, "load": 8, "store": 3, "branch": 2},
        {"alu": 5, "load": 5, "store": 5, "branch": 5},
    ]

    def test_results_match_single_cycle(self):
        from sim.compiler import compile_c
        for isa in ("riscv", "arm", "x86"):
            prog = assemble(isa, compile_c(self.C_SRC, isa).asm)
            sc_cpu, sc_st = _run(isa, "single_cycle", prog, budget=6000)
            oracle = _final(sc_cpu, sc_st)
            for costs in self.COSTS:
                cpu, st = _run(isa, "configurable", prog, cycle_costs=costs, budget=12000)
                with self.subTest(isa=isa, costs=costs):
                    self.assertEqual(_final(cpu, st), oracle,
                                     f"{isa} configurable {costs} diverged from single_cycle")


class TestCycleScaling(unittest.TestCase):
    def test_all_ones_matches_single_cycle_count(self):
        prog = assemble("riscv", ASM)
        _, sc = _run("riscv", "single_cycle", prog)
        _, cf = _run("riscv", "configurable", prog,
                     cycle_costs={"alu": 1, "load": 1, "store": 1, "branch": 1})
        self.assertEqual(_completion(cf), _completion(sc))

    def test_fetdecexe_profile_matches_multicycle_count(self):
        prog = assemble("riscv", ASM)
        _, mc = _run("riscv", "multicycle", prog)
        _, cf = _run("riscv", "configurable", prog, cycle_costs=FETDECEXE_COSTS)
        self.assertEqual(_completion(cf), _completion(mc))

    def test_higher_budget_costs_more_cycles(self):
        prog = assemble("riscv", ASM)
        _, lo = _run("riscv", "configurable", prog,
                     cycle_costs={"alu": 1, "load": 1, "store": 1, "branch": 1})
        _, hi = _run("riscv", "configurable", prog,
                     cycle_costs={"alu": 4, "load": 4, "store": 4, "branch": 4})
        self.assertLess(_completion(lo), _completion(hi))


class TestTimeModel(unittest.TestCase):
    def test_single_cycle_has_the_longest_clock(self):
        # all-1s (single-cycle) period is the max over classes of full work.
        single = clock_period({"alu": 1, "load": 1, "store": 1, "branch": 1})
        fde = clock_period(FETDECEXE_COSTS)
        self.assertGreater(single, fde)

    def test_more_cycles_can_mean_less_time(self):
        # The teaching payoff: FetDecExe uses more cycles than single-cycle but a
        # short enough clock that total time is competitive/lower.
        prog = assemble("riscv", ASM)
        _, sc = _run("riscv", "configurable", prog,
                     cycle_costs={"alu": 1, "load": 1, "store": 1, "branch": 1})
        _, fde = _run("riscv", "configurable", prog, cycle_costs=FETDECEXE_COSTS)
        sc_cyc, fde_cyc = _completion(sc), _completion(fde)
        self.assertGreater(fde_cyc, sc_cyc)  # more cycles
        sc_time = estimate_time(sc_cyc, {"alu": 1, "load": 1, "store": 1, "branch": 1})
        fde_time = estimate_time(fde_cyc, FETDECEXE_COSTS)
        self.assertLessEqual(fde_time, sc_time)  # but not more time


class TestAPI(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_simulate_returns_time_model(self):
        resp = self.client.post("/simulate", json={
            "preset": "riscv/configurable", "input_mode": "asm",
            "asm_text": "ADDI x1,x0,5\nADDI x2,x1,3\nSW x2,0(x0)\n",
            "run_to_completion": True,
            "cycle_costs": {"alu": 3, "load": 4, "store": 4, "branch": 3}}).get_json()
        tm = resp["time_model"]
        self.assertEqual(tm["costs"], {"alu": 3, "load": 4, "store": 4, "branch": 3})
        self.assertGreater(tm["cycles"], 0)
        self.assertAlmostEqual(tm["total_time"], tm["cycles"] * tm["clock_period"])

    def test_cycle_costs_are_clamped(self):
        resp = self.client.post("/simulate", json={
            "preset": "riscv/configurable", "input_mode": "asm",
            "asm_text": "ADDI x1,x0,5\n", "cycles": 50,
            "cycle_costs": {"alu": 9999, "load": -3}}).get_json()
        costs = resp["time_model"]["costs"]
        self.assertEqual(costs["alu"], 64)                 # clamped high
        self.assertEqual(costs["load"], 1)                 # clamped low
        self.assertEqual(costs["store"], DEFAULT_COSTS["store"])  # default when omitted

    def test_bad_cycle_costs_rejected_not_500(self):
        resp = self.client.post("/simulate", json={
            "preset": "riscv/configurable", "input_mode": "asm",
            "asm_text": "ADDI x1,x0,5\n", "cycle_costs": "not-an-object"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())


if __name__ == "__main__":
    unittest.main()
