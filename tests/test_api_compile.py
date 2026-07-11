"""
API tests for the /compile route.

Verifies the happy path returns the documented contract
({isa, backend, asm, stages:{source,tokens,ast,asm}, source_map, program}) and
that hostile/untrusted source is rejected with a JSON {error} 400 — NEVER a raw
500 or an HTML traceback (the same never-500 contract /assemble and /simulate
uphold).
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.app import app

VALID_C = "int main() { int a = 5; int b = 7; return a + b; }"


class CompileAPITest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()

    def _assert_400_json(self, resp):
        """A rejected request must be HTTP 400 with a JSON {error} body."""
        self.assertEqual(resp.status_code, 400, resp.data[:200])
        data = json.loads(resp.data)  # must parse as JSON, not an HTML 500 page
        self.assertIn("error", data)

    # ── happy path ────────────────────────────────────────────────
    def test_compile_happy_path(self):
        resp = self.client.post("/compile", json={"source": VALID_C, "isa": "riscv"})
        self.assertEqual(resp.status_code, 200, resp.data[:200])
        data = json.loads(resp.data)
        for key in ("isa", "backend", "asm", "stages", "source_map", "program"):
            self.assertIn(key, data)
        for key in ("source", "tokens", "ast", "asm"):
            self.assertIn(key, data["stages"])
        self.assertEqual(data["isa"], "riscv")
        self.assertEqual(data["backend"], "python")
        self.assertTrue(data["asm"].strip())
        self.assertIsInstance(data["program"], list)
        self.assertGreater(len(data["program"]), 0)

    def test_compile_arm_and_x86(self):
        for isa in ("arm", "x86"):
            resp = self.client.post("/compile", json={"source": VALID_C, "isa": isa})
            self.assertEqual(resp.status_code, 200, f"{isa}: {resp.data[:200]}")
            self.assertEqual(json.loads(resp.data)["isa"], isa)

    # ── hostile input -> 400, never 500 ──────────────────────────
    def test_non_dict_body_400(self):
        resp = self.client.post("/compile", data="{not valid json",
                                 content_type="application/json")
        self._assert_400_json(resp)

    def test_missing_source_400(self):
        self._assert_400_json(self.client.post("/compile", json={"isa": "riscv"}))

    def test_non_string_source_400(self):
        self._assert_400_json(self.client.post("/compile", json={"source": 123}))

    def test_empty_source_400(self):
        self._assert_400_json(self.client.post("/compile", json={"source": "   "}))

    def test_compile_error_400_not_500(self):
        resp = self.client.post(
            "/compile", json={"source": "int main(){ struct X y; }", "isa": "riscv"})
        self._assert_400_json(resp)

    def test_unknown_isa_400(self):
        self._assert_400_json(
            self.client.post("/compile", json={"source": VALID_C, "isa": "zzz"}))

    # ── the compiled program flows through the existing run path ─
    def test_compiled_program_runs_via_simulate(self):
        compiled = json.loads(self.client.post(
            "/compile", json={"source": VALID_C, "isa": "riscv"}).data)
        resp = self.client.post("/simulate", json={
            "preset": "riscv/single_cycle",
            "input_mode": "asm",
            "asm_text": compiled["asm"],
            "cycles": 400,
        })
        self.assertEqual(resp.status_code, 200, resp.data[:200])
        data = json.loads(resp.data)
        self.assertIn("cycles", data)
        self.assertGreater(len(data["cycles"]), 1)


class CExamplesAPITest(unittest.TestCase):
    """GET /compiler/examples (catalog) and /compiler/examples/<name> (fetch).

    Every catalog entry must load, compile for every ISA its Targets header
    names, and carry name/label/file/description/targets. Hostile names are
    rejected without leaking source (same containment contract as /examples).
    """

    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()

    def _catalog(self):
        resp = self.client.get("/compiler/examples")
        self.assertEqual(resp.status_code, 200)
        return json.loads(resp.data)["items"]

    def test_catalog_shape_and_known_samples(self):
        items = self._catalog()
        self.assertGreaterEqual(len(items), 11)
        names = {it["name"] for it in items}
        for expected in ("sum_to_n", "fib_iter", "gcd", "array_sum",
                         "bubble_sort", "fib_recursive", "collatz",
                         "logic_ops", "nested_loops"):
            self.assertIn(expected, names)
        for it in items:
            for key in ("name", "label", "file", "description", "targets"):
                self.assertIn(key, it, f"{it.get('name')}: missing '{key}'")
            self.assertTrue(it["file"].endswith(".c"))
            self.assertTrue(it["targets"], f"{it['name']}: empty Targets header")
            self.assertTrue(set(it["targets"]) <= {"riscv", "arm", "x86"},
                            f"{it['name']}: bad targets {it['targets']}")

    def test_every_catalog_entry_loads_and_compiles_for_its_targets(self):
        for it in self._catalog():
            resp = self.client.get(f"/compiler/examples/{it['name']}")
            self.assertEqual(resp.status_code, 200, it["name"])
            content = json.loads(resp.data)["content"]
            self.assertTrue(content.strip(), it["name"])
            for isa in it["targets"]:
                with self.subTest(sample=it["name"], isa=isa):
                    resp = self.client.post(
                        "/compile", json={"source": content, "isa": isa})
                    self.assertEqual(resp.status_code, 200,
                                     f"{it['name']} on {isa}: {resp.data[:200]}")

    def test_bad_example_names_rejected(self):
        # Regex gate -> 400; unknown-but-well-formed -> 404. Never leaks source.
        for bad, status in (("Bad-Name", 400), ("collatz.c", 400),
                            ("no_such_example", 404)):
            resp = self.client.get(f"/compiler/examples/{bad}")
            self.assertEqual(resp.status_code, status, bad)
            self.assertIn("error", json.loads(resp.data))
            self.assertNotIn(b"int main", resp.data)


class CompareAPITest(unittest.TestCase):
    """POST /compare: cycles-to-completion grid. Core-C compares across all
    ISAs x models; asm compares models within one ISA. Cells either carry a
    parity-checked cycle count or an explanatory error — never a raw 500."""

    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()

    def _post(self, **body):
        resp = self.client.post("/compare", json=body)
        return resp.status_code, json.loads(resp.data)

    def test_core_c_grid(self):
        src = open(os.path.join(os.path.dirname(__file__), "..",
                                "programs", "c", "fib_iter.c")).read()
        status, data = self._post(source=src)
        self.assertEqual(status, 200)
        self.assertEqual(sorted(data["isas"]), ["arm", "riscv", "x86"])
        cells = {(r["isa"], r["model"]): r for r in data["results"]}
        self.assertEqual(len(cells), 3 * len(data["models"]))
        for isa in ("riscv", "arm", "x86"):
            # fib_iter targets all ISAs; the in-order models must complete
            # with a real settle-point count, and more phases => more cycles.
            sc = cells[(isa, "single_cycle")]
            mc = cells[(isa, "multicycle")]
            pl = cells[(isa, "pipeline")]
            for cell in (sc, mc, pl):
                self.assertTrue(cell.get("completed"), cell)
                self.assertGreater(cell["cycles"], 0, cell)
            self.assertGreater(mc["cycles"], sc["cycles"], isa)
            self.assertGreater(pl["cycles"], sc["cycles"], isa)
        # Every cell either has a count or explains itself.
        for r in data["results"]:
            self.assertTrue(("cycles" in r) or ("error" in r), r)
        # x86/superscalar is excluded with a reason, never a number.
        self.assertIn("error", cells[("x86", "superscalar")])

    def test_parity_guard_blocks_divergent_models(self):
        # Compiled code with function calls diverges on riscv/ooo (known
        # scope limit): the guard must replace the number with an error so
        # comparisons never show cycles for a wrong result.
        src = open(os.path.join(os.path.dirname(__file__), "..",
                                "programs", "c", "fib_iter.c")).read()
        _, data = self._post(source=src, models=["single_cycle", "ooo"])
        cells = {(r["isa"], r["model"]): r for r in data["results"]}
        r = cells[("riscv", "ooo")]
        if "error" in r:
            self.assertIn("diverges", r["error"])
        else:
            # If OoO call linkage is ever fixed, parity passes — also fine.
            self.assertTrue(r.get("completed"))

    def test_asm_mode_single_isa(self):
        status, data = self._post(asm_text="ADDI x1, x0, 5\nNOP\n",
                                  isa="riscv",
                                  models=["single_cycle", "pipeline"])
        self.assertEqual(status, 200)
        self.assertEqual(data["isas"], ["riscv"])
        for r in data["results"]:
            self.assertTrue(r.get("completed"), r)

    def test_configurable_column_honors_cycle_costs(self):
        # The editable "Custom" column runs the configurable model with the
        # per-class cycle_costs. all-1s == single-cycle; {3,4,4,3} == the
        # FetDecExe (multicycle) count; a load-heavy config lands in between.
        src = open(os.path.join(os.path.dirname(__file__), "..",
                                "programs", "c", "fib_iter.c")).read()

        def cfg_cycles(costs):
            _, data = self._post(source=src, cycle_costs=costs,
                                 models=["single_cycle", "configurable", "multicycle"])
            cells = {(r["isa"], r["model"]): r for r in data["results"]}
            return (cells[("riscv", "single_cycle")],
                    cells[("riscv", "configurable")],
                    cells[("riscv", "multicycle")], data)

        sc, cfg1, mc, data = cfg_cycles({"alu": 1, "load": 1, "store": 1, "branch": 1})
        self.assertEqual(cfg1["cycles"], sc["cycles"])          # all-1 == single
        self.assertEqual(data["cycle_costs"]["load"], 1)        # echoed back
        self.assertIn("clock_period", cfg1)                     # time model attached
        self.assertIn("total_time", cfg1)

        _, cfg_fdx, mc2, _ = cfg_cycles({"alu": 3, "load": 4, "store": 4, "branch": 3})
        self.assertEqual(cfg_fdx["cycles"], mc2["cycles"])      # {3,4,4,3} == FetDecExe

        _, cfg_load, _, _ = cfg_cycles({"alu": 1, "load": 2, "store": 1, "branch": 1})
        self.assertGreater(cfg_load["cycles"], sc["cycles"])    # slower loads cost cycles

    def test_configurable_costs_bad_input_400(self):
        status, data = self._post(source="int main(){return 1;}",
                                  cycle_costs="nope")
        self.assertEqual(status, 400)
        self.assertIn("error", data)

    def test_bad_inputs_400(self):
        for body in ({},                                   # neither input
                     {"source": "int main(){return 1;}",
                      "asm_text": "NOP"},                  # both inputs
                     {"source": "x", "models": ["warp"]},  # unknown model
                     {"asm_text": "NOP", "isa": "mips"}):  # unknown isa
            status, data = self._post(**body)
            self.assertEqual(status, 400, body)
            self.assertIn("error", data)


if __name__ == "__main__":
    unittest.main()
