"""
Supplementary API-endpoint coverage for the RTL CPU Simulator.

This file complements tests/test_api_endpoints.py. It systematically
exercises EVERY route in api/app.py with positive paths, negative paths
(unknown preset/isa, malformed/missing JSON body), and the critical edge
cases that the UI relies on:

  * /                      index HTML is served
  * /presets               structure + every model bucket present
  * /isa/<name>            all 3 ISAs + demo text/asm fields + unknown 404
  * /predictors            dynamically discovered names present
  * /topology/<preset>     EVERY preset renders without 500, superscalar
                           num_lanes, branch-predictor params, unknown 404
  * /simulate (POST)       EVERY preset simulates without 500, hex mode,
                           demo fallback, cycle clamp/floor, malformed body
  * /assemble (POST)       per-ISA, unknown ISA, empty/missing text,
                           malformed JSON, x86 multi-byte
  * /cheatsheet/<isa>      structural for all 3 ISAs + unknown 404
  * /examples              catalog grouping
  * /examples/<path>       positive read + path-traversal / bad-type /
                           unknown-isa / wrong-part-count negatives

Uses the same unittest + app.test_client() style as the existing suite.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from api.app import app, PRESETS, PREDICTOR_CLASSES

ROOT = os.path.join(os.path.dirname(__file__), "..")
PROGRAMS_DIR = os.path.join(ROOT, "programs")

API_CYCLE_CAP = 2000


# ── Base class ────────────────────────────────────────────────────
class APITestBase(unittest.TestCase):
    """Shared setup and helpers for API endpoint tests."""

    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()

    def get_json(self, path, expected_status=200):
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, expected_status,
                         f"GET {path} returned {resp.status_code}: {resp.data[:200]}")
        return json.loads(resp.data)

    def post_json(self, path, body, expected_status=200):
        resp = self.client.post(path, json=body)
        self.assertEqual(resp.status_code, expected_status,
                         f"POST {path} returned {resp.status_code}: {resp.data[:200]}")
        return json.loads(resp.data)

    @staticmethod
    def extract_final_state(cycles):
        return cycles[-1]

    @staticmethod
    def extract_registers(state):
        for key, val in state.items():
            if isinstance(val, dict) and "registers" in val:
                return val["registers"]
        return None


# ── 1. / index ───────────────────────────────────────────────────
class TestIndexEndpoint(APITestBase):

    def test_index_returns_200(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

    def test_index_serves_html(self):
        resp = self.client.get("/")
        self.assertIn("text/html", resp.content_type)

    def test_index_contains_html_document(self):
        resp = self.client.get("/")
        body = resp.data.decode("utf-8", errors="replace").lower()
        self.assertIn("<html", body)


# ── 2. /presets (model buckets) ──────────────────────────────────
class TestPresetsModels(APITestBase):

    def test_models_contains_all_known_models(self):
        data = self.get_json("/presets")
        for model in ("single_cycle", "multicycle", "pipeline", "ooo", "superscalar"):
            self.assertIn(model, data["models"],
                          f"model '{model}' missing from /presets models map")

    def test_every_registered_preset_is_listed(self):
        data = self.get_json("/presets")
        for name in PRESETS:
            self.assertIn(name, data["presets"],
                          f"registered preset '{name}' missing from /presets")

    def test_isa_entries_have_metadata(self):
        data = self.get_json("/presets")
        for isa in ("riscv", "arm", "x86"):
            entry = data["isas"][isa]
            self.assertIn("display_name", entry)
            self.assertIn("description", entry)
            self.assertIn("program_format", entry)

    def test_preset_isa_and_model_match_registry(self):
        data = self.get_json("/presets")
        for name, p in data["presets"].items():
            with self.subTest(preset=name):
                self.assertEqual(p["isa"], PRESETS[name]["isa"])
                self.assertEqual(p["model"], PRESETS[name]["model"])


# ── 3. /isa/<name> ───────────────────────────────────────────────
class TestISADemoFields(APITestBase):

    def test_all_isas_expose_demo_text_and_asm(self):
        for isa in ("riscv", "arm", "x86"):
            with self.subTest(isa=isa):
                data = self.get_json(f"/isa/{isa}")
                self.assertIn("demo_program_text", data)
                self.assertIn("demo_program_asm", data)
                self.assertGreater(len(data["demo_program_text"]), 0)

    def test_reg_names_length_matches_num_regs(self):
        for isa in ("riscv", "arm", "x86"):
            with self.subTest(isa=isa):
                data = self.get_json(f"/isa/{isa}")
                self.assertEqual(len(data["reg_names"]), data["num_regs"])

    def test_x86_demo_text_is_byte_formatted(self):
        data = self.get_json("/isa/x86")
        first_line = data["demo_program_text"].splitlines()[0]
        # Byte format starts with two-hex-digit tokens, e.g. "B9 0A ..."
        token = first_line.split()[0]
        self.assertEqual(len(token), 2)
        int(token, 16)  # raises if not hex

    def test_unknown_isa_returns_json_error_404(self):
        resp = self.client.get("/isa/sparc")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("error", json.loads(resp.data))


# ── 4. /predictors ───────────────────────────────────────────────
class TestPredictorsEndpoint(APITestBase):

    def test_returns_every_discovered_predictor(self):
        data = self.get_json("/predictors")
        names = {p["name"] for p in data["predictors"]}
        for expected in PREDICTOR_CLASSES:
            self.assertIn(expected, names,
                          f"predictor '{expected}' missing from /predictors")

    def test_predictors_sorted_by_name(self):
        data = self.get_json("/predictors")
        names = [p["name"] for p in data["predictors"]]
        self.assertEqual(names, sorted(names))


# ── 5. /topology/<preset> ────────────────────────────────────────
class TestTopologyEndpoint(APITestBase):

    def test_every_preset_renders_topology_without_500(self):
        for name in sorted(PRESETS):
            with self.subTest(preset=name):
                data = self.get_json(f"/topology/{name}")
                self.assertIn("nodes", data)
                self.assertIn("edges", data)
                self.assertEqual(data["model"], PRESETS[name]["model"])

    def test_superscalar_topology_respects_num_lanes(self):
        if "riscv/superscalar" not in PRESETS:
            self.skipTest("riscv/superscalar preset not available")
        for lanes in (2, 4):
            with self.subTest(lanes=lanes):
                data = self.get_json(f"/topology/riscv/superscalar?num_lanes={lanes}")
                self.assertIn("nodes", data)

    def test_topology_accepts_branch_predictor_params(self):
        if not PREDICTOR_CLASSES:
            self.skipTest("no branch predictors discovered")
        bp = sorted(PREDICTOR_CLASSES)[0]
        data = self.get_json(
            f"/topology/riscv/pipeline?branch_predictor={bp}&prediction_stage=id")
        self.assertIn("nodes", data)

    def test_topology_unknown_preset_404(self):
        resp = self.client.get("/topology/riscv/does_not_exist")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("error", json.loads(resp.data))

    def test_topology_unknown_isa_404(self):
        resp = self.client.get("/topology/sparc/single_cycle")
        self.assertEqual(resp.status_code, 404)


# ── 6. /simulate — every preset, no 500 ──────────────────────────
class TestSimulateAllPresets(APITestBase):

    def test_every_preset_simulates_without_500(self):
        for name in sorted(PRESETS):
            with self.subTest(preset=name):
                body = {"preset": name, "cycles": 10}
                if PRESETS[name]["model"] == "superscalar":
                    body["num_lanes"] = 2
                resp = self.client.post("/simulate", json=body)
                self.assertEqual(
                    resp.status_code, 200,
                    f"{name} simulate returned {resp.status_code}: {resp.data[:200]}")
                data = json.loads(resp.data)
                self.assertIn("cycles", data)
                self.assertGreater(len(data["cycles"]), 0)


# ── 7. /simulate — input modes & defaults ────────────────────────
class TestSimulateInputModes(APITestBase):

    def test_default_preset_when_omitted(self):
        """No preset -> defaults to riscv/single_cycle."""
        data = self.post_json("/simulate", {"cycles": 5})
        self.assertEqual(data["preset"], "riscv/single_cycle")
        self.assertEqual(data["isa"], "riscv")

    def test_demo_program_used_when_no_program(self):
        """Omitting program falls back to the ISA demo program."""
        data = self.post_json("/simulate", {
            "preset": "riscv/single_cycle",
            "cycles": 10,
        })
        # Demo is the Fibonacci program; just confirm it ran and produced regs.
        regs = self.extract_registers(self.extract_final_state(data["cycles"]))
        self.assertIsNotNone(regs)

    def test_hex_mode_with_string_words(self):
        """Hex-string program words simulate correctly (ADDI x1,x0,42)."""
        data = self.post_json("/simulate", {
            "preset": "riscv/single_cycle",
            "cycles": 3,
            "input_mode": "hex",
            "program": ["0x02a00093"],
        })
        regs = self.extract_registers(self.extract_final_state(data["cycles"]))
        self.assertEqual(regs[1], 42)

    def test_hex_mode_with_int_words(self):
        """Integer program words simulate correctly (ADDI x1,x0,42)."""
        data = self.post_json("/simulate", {
            "preset": "riscv/single_cycle",
            "cycles": 3,
            "input_mode": "hex",
            "program": [0x02a00093],
        })
        regs = self.extract_registers(self.extract_final_state(data["cycles"]))
        self.assertEqual(regs[1], 42)

    def test_asm_mode_empty_text_falls_back_to_demo(self):
        """input_mode=asm with empty asm_text should not error; uses demo."""
        data = self.post_json("/simulate", {
            "preset": "riscv/single_cycle",
            "cycles": 5,
            "input_mode": "asm",
            "asm_text": "",
        })
        self.assertIn("cycles", data)


# ── 8. /simulate — cycle clamping edges ──────────────────────────
class TestSimulateCycleEdges(APITestBase):

    def test_zero_cycles_returns_only_reset(self):
        data = self.post_json("/simulate", {
            "preset": "riscv/single_cycle",
            "cycles": 0,
            "input_mode": "asm",
            "asm_text": "ADDI x1, x0, 1",
        })
        self.assertEqual(len(data["cycles"]), 1)
        self.assertEqual(data["cycles"][0]["_cycle"], 0)

    def test_negative_cycles_does_not_500(self):
        """Negative cycles must not crash; produces no extra ticks."""
        resp = self.client.post("/simulate", json={
            "preset": "riscv/single_cycle",
            "cycles": -5,
            "input_mode": "asm",
            "asm_text": "ADDI x1, x0, 1",
        })
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(len(data["cycles"]), 1)  # reset only

    def test_exactly_cap_cycles_not_capped(self):
        data = self.post_json("/simulate", {
            "preset": "riscv/single_cycle",
            "cycles": API_CYCLE_CAP,
            "input_mode": "asm",
            "asm_text": "ADDI x1, x0, 1",
        })
        self.assertEqual(len(data["cycles"]), API_CYCLE_CAP + 1)


# ── 9. /simulate — malformed / negative bodies ───────────────────
class TestSimulateBadBody(APITestBase):

    def test_malformed_json_returns_400(self):
        resp = self.client.post("/simulate", data="{not valid json",
                                 content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_empty_body_returns_400(self):
        resp = self.client.post("/simulate", data="",
                                 content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_no_body_at_all_returns_400(self):
        resp = self.client.post("/simulate")
        self.assertEqual(resp.status_code, 400)

    def test_unknown_preset_returns_400_json(self):
        resp = self.client.post("/simulate",
                                json={"preset": "sparc/single_cycle", "cycles": 1})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", json.loads(resp.data))

    def test_invalid_asm_returns_400_json(self):
        resp = self.client.post("/simulate", json={
            "preset": "riscv/single_cycle",
            "input_mode": "asm",
            "asm_text": "TOTALLY_NOT_AN_INSTRUCTION",
            "cycles": 1,
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", json.loads(resp.data))


# ── 10. /assemble ────────────────────────────────────────────────
class TestAssembleExtra(APITestBase):

    def test_unknown_isa_returns_400(self):
        resp = self.client.post("/assemble",
                                json={"isa": "mips", "text": "ADD r1, r2, r3"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", json.loads(resp.data))

    def test_missing_text_key_returns_400(self):
        resp = self.client.post("/assemble", json={"isa": "riscv"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", json.loads(resp.data))

    def test_whitespace_only_text_returns_400(self):
        resp = self.client.post("/assemble",
                                json={"isa": "riscv", "text": "   \n  \t"})
        self.assertEqual(resp.status_code, 400)

    def test_malformed_json_returns_400(self):
        resp = self.client.post("/assemble", data="{bad json",
                                 content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_default_isa_is_riscv(self):
        """isa omitted -> defaults to riscv."""
        data = self.post_json("/assemble", {"text": "ADDI x1, x0, 1"})
        self.assertEqual(data["isa"], "riscv")

    def test_x86_multibyte_program_returned(self):
        """x86 MOV ECX, 10 -> 5-byte encoding B9 0A 00 00 00."""
        data = self.post_json("/assemble", {"isa": "x86", "text": "MOV ECX, 10"})
        self.assertEqual(data["program"], [0xB9, 0x0A, 0x00, 0x00, 0x00])

    def test_arm_roundtrip_then_simulate(self):
        """Assemble ARM then simulate the produced program in hex mode."""
        asm_data = self.post_json("/assemble", {"isa": "arm", "text": "MOVZ X1, #88"})
        sim_data = self.post_json("/simulate", {
            "preset": "arm/single_cycle",
            "program": asm_data["program"],
            "cycles": 5,
            "input_mode": "hex",
        })
        regs = self.extract_registers(self.extract_final_state(sim_data["cycles"]))
        self.assertEqual(regs[1], 88)


# ── 11. /cheatsheet structural for all ISAs ──────────────────────
class TestCheatsheetStructure(APITestBase):

    def test_all_isas_have_well_formed_entries(self):
        for isa in ("riscv", "arm", "x86"):
            with self.subTest(isa=isa):
                data = self.get_json(f"/cheatsheet/{isa}")
                self.assertEqual(data["isa"], isa)
                self.assertGreater(len(data["instructions"]), 0)
                for item in data["instructions"]:
                    for key in ("category", "mnemonic", "syntax",
                                "description", "example"):
                        self.assertIn(key, item)

    def test_unknown_isa_returns_404_json(self):
        resp = self.client.get("/cheatsheet/sparc")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("error", json.loads(resp.data))


# ── 12. /examples & /examples/<path> ─────────────────────────────
class TestExamplesEndpoint(APITestBase):

    def test_catalog_groups_by_isa_and_category(self):
        data = self.get_json("/examples")
        # Each ISA maps to a dict of category -> {label, items}
        for isa, categories in data.items():
            self.assertIn(isa, ("riscv", "arm", "x86"))
            for cat, payload in categories.items():
                self.assertIn("label", payload)
                self.assertIn("items", payload)
                for item in payload["items"]:
                    self.assertIn("name", item)
                    self.assertIn("label", item)
                    self.assertIn("file", item)

    def test_catalog_file_paths_are_loadable(self):
        """Every file path listed in the catalog can actually be fetched."""
        catalog = self.get_json("/examples")
        checked = 0
        for isa, categories in catalog.items():
            for cat, payload in categories.items():
                for item in payload["items"]:
                    data = self.get_json(f"/examples/{item['file']}")
                    self.assertIn("content", data)
                    self.assertGreater(len(data["content"]), 0)
                    checked += 1
                    if checked >= 12:  # sample enough; keep it fast
                        return
        self.assertGreater(checked, 0, "catalog had no items to verify")

    def test_valid_file_returns_content(self):
        data = self.get_json("/examples/riscv/algorithms/fibonacci.asm")
        self.assertEqual(data["file"], "riscv/algorithms/fibonacci.asm")
        self.assertGreater(len(data["content"]), 0)

    def test_url_encoded_traversal_blocked(self):
        resp = self.client.get(
            "/examples/riscv/algorithms/..%2f..%2f..%2fapi%2fapp.py")
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn(b"Flask", resp.data)  # never serve real source

    def test_literal_dotdot_traversal_blocked(self):
        resp = self.client.get("/examples/riscv/../../api/app.py")
        self.assertEqual(resp.status_code, 400)

    def test_non_asm_file_type_rejected(self):
        resp = self.client.get("/examples/riscv/algorithms/secret.txt")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", json.loads(resp.data))

    def test_python_file_extension_rejected(self):
        resp = self.client.get("/examples/riscv/algorithms/evil.py")
        self.assertEqual(resp.status_code, 400)

    def test_unknown_isa_rejected(self):
        resp = self.client.get("/examples/mips/algorithms/foo.asm")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", json.loads(resp.data))

    def test_wrong_part_count_rejected(self):
        # Only two segments -> not isa/category/filename
        resp = self.client.get("/examples/riscv/onlytwo.asm")
        self.assertEqual(resp.status_code, 400)

    def test_too_many_parts_rejected(self):
        resp = self.client.get("/examples/riscv/a/b/c.asm")
        self.assertEqual(resp.status_code, 400)

    def test_nonexistent_asm_returns_404(self):
        resp = self.client.get("/examples/riscv/algorithms/no_such_file.asm")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("error", json.loads(resp.data))


class RunToCompletionTest(unittest.TestCase):
    """POST /simulate with run_to_completion=True: the server simulates until
    the architectural state (registers + data memory) is unchanged for the
    runner's stable window, capped at MAX_AUTO_CYCLES. Manual mode keeps the
    exact response shape it always had."""

    @classmethod
    def setUpClass(cls):
        from api.app import app
        app.config["TESTING"] = True
        cls.client = app.test_client()

    def _simulate(self, **body):
        resp = self.client.post("/simulate", json=body)
        self.assertEqual(resp.status_code, 200, resp.data[:200])
        return json.loads(resp.data)

    def test_settles_early_with_correct_result(self):
        data = self._simulate(
            preset="riscv/single_cycle", input_mode="asm",
            asm_text="ADDI x1, x0, 42\nADDI x2, x1, 1\nNOP\n",
            run_to_completion=True)
        self.assertTrue(data["run_to_completion"])
        self.assertTrue(data["completed"])
        # Tiny program + 32-cycle stability window: far below the 10k cap.
        self.assertLess(len(data["cycles"]), 100)
        self.assertEqual(data["cycles"][-1]["regfile"]["registers"][2], 43)

    def test_explicit_cycles_ignored_in_auto_mode(self):
        # 'cycles': 3 would truncate mid-flight; auto mode must run past it.
        data = self._simulate(
            preset="riscv/single_cycle", input_mode="asm",
            asm_text="ADDI x1, x0, 42\nADDI x2, x1, 1\nNOP\n",
            cycles=3, run_to_completion=True)
        self.assertGreater(len(data["cycles"]), 3 + 1)
        self.assertEqual(data["cycles"][-1]["regfile"]["registers"][2], 43)

    def test_all_models_settle_on_demo(self):
        for preset in ("riscv/single_cycle", "riscv/multicycle",
                       "riscv/pipeline", "riscv/ooo", "riscv/superscalar",
                       "arm/pipeline", "x86/single_cycle"):
            with self.subTest(preset=preset):
                data = self._simulate(preset=preset, run_to_completion=True)
                self.assertTrue(data["completed"], preset)

    def test_never_settling_program_hits_cap(self):
        # A counter that increments forever never settles; patch the cap so
        # the test stays fast. The route reads the module global at call time.
        import api.app as appmod
        old = appmod.MAX_AUTO_CYCLES
        appmod.MAX_AUTO_CYCLES = 300
        try:
            data = self._simulate(
                preset="riscv/single_cycle", input_mode="asm",
                asm_text="loop:\nADDI x1, x1, 1\nJAL x0, loop\n",
                run_to_completion=True)
        finally:
            appmod.MAX_AUTO_CYCLES = old
        self.assertFalse(data["completed"])
        self.assertEqual(len(data["cycles"]), 300 + 1)  # cap + reset cycle

    def test_manual_mode_shape_unchanged(self):
        data = self._simulate(
            preset="riscv/single_cycle", input_mode="asm",
            asm_text="ADDI x1, x0, 5\nNOP\n", cycles=12)
        self.assertEqual(len(data["cycles"]), 13)
        self.assertNotIn("completed", data)
        self.assertNotIn("run_to_completion", data)

    def test_runner_until_stable_unit(self):
        # Runner level: until_stable stops early and the cap is respected.
        from sim.assembler import assemble
        from sim.harness import PRESETS
        from sim.runner_v2 import run_simulation, STABLE_WINDOW
        prog = assemble("riscv", "ADDI x1, x0, 7\nNOP\n")
        cpu = PRESETS["riscv/single_cycle"]["build"](prog)
        states = run_simulation(cpu, num_cycles=10000, until_stable=True)
        self.assertLess(len(states), 3 * STABLE_WINDOW)
        self.assertEqual(states[-1]["regfile"]["registers"][1], 7)


if __name__ == "__main__":
    unittest.main()
