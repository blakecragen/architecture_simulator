"""
API-level end-to-end tests for the RTL CPU Simulator.

Exercises the exact same HTTP code path the UI uses by calling Flask
endpoints via test_client(). Catches any discrepancy between what the
simulator computes internally and what the API returns to the browser.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from api.app import app, PRESETS

# Reuse helpers from the direct-simulation test suite
from test_program_results import (
    _parse_expected,
    _parse_cycles_hint,
    _parse_models_hint,
    _get_reg_index,
    _get_default_models,
    ALL_MODELS,
    MODEL_CYCLE_MULTIPLIER,
    BASE_CYCLES,
)

ROOT = os.path.join(os.path.dirname(__file__), "..")
PROGRAMS_DIR = os.path.join(ROOT, "programs")

API_CYCLE_CAP = 2000  # The API clamps cycles to this value


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
        """Return the last cycle snapshot from a simulate response."""
        return cycles[-1]

    @staticmethod
    def extract_registers(state):
        """Find and return the register array from a cycle state dict."""
        for key, val in state.items():
            if isinstance(val, dict) and "registers" in val:
                return val["registers"]
        return None

    @staticmethod
    def extract_memory(state):
        """Find and return the data-memory array (skip instruction memory)."""
        for key, val in state.items():
            if isinstance(val, dict) and "memory" in val and "imem" not in key.lower():
                return val["memory"]
        return None


# ── 1. /presets ───────────────────────────────────────────────────
class TestPresetsEndpoint(APITestBase):

    def test_response_structure(self):
        data = self.get_json("/presets")
        self.assertIn("isas", data)
        self.assertIn("models", data)
        self.assertIn("presets", data)

    def test_all_three_isas(self):
        data = self.get_json("/presets")
        for isa in ("riscv", "arm", "x86"):
            self.assertIn(isa, data["isas"])

    def test_minimum_preset_count(self):
        data = self.get_json("/presets")
        self.assertGreaterEqual(len(data["presets"]), 12)

    def test_preset_fields(self):
        data = self.get_json("/presets")
        for name, p in data["presets"].items():
            with self.subTest(preset=name):
                self.assertIn("label", p)
                self.assertIn("isa", p)
                self.assertIn("model", p)


# ── 2. /isa/<name> ───────────────────────────────────────────────
class TestISAEndpoint(APITestBase):

    def test_riscv_info(self):
        data = self.get_json("/isa/riscv")
        self.assertEqual(data["num_regs"], 32)
        self.assertEqual(data["program_format"], "words")
        self.assertIn("reg_names", data)
        self.assertIn("demo_program", data)
        self.assertIn("demo_program_asm", data)

    def test_arm_info(self):
        data = self.get_json("/isa/arm")
        self.assertEqual(data["num_regs"], 32)
        self.assertEqual(data["program_format"], "words")

    def test_x86_info(self):
        data = self.get_json("/isa/x86")
        self.assertEqual(data["num_regs"], 8)
        self.assertEqual(data["program_format"], "bytes")

    def test_unknown_isa_404(self):
        self.get_json("/isa/mips", expected_status=404)


# ── 3. Supporting endpoints ──────────────────────────────────────
class TestSupportingEndpoints(APITestBase):

    def test_predictors(self):
        data = self.get_json("/predictors")
        self.assertIn("predictors", data)
        for p in data["predictors"]:
            self.assertIn("name", p)
            self.assertIn("label", p)

    def test_cheatsheet_riscv(self):
        data = self.get_json("/cheatsheet/riscv")
        self.assertIn("instructions", data)
        self.assertGreater(len(data["instructions"]), 0)
        item = data["instructions"][0]
        for key in ("category", "mnemonic", "syntax", "description", "example"):
            self.assertIn(key, item, f"cheatsheet item missing '{key}'")

    def test_cheatsheet_arm(self):
        data = self.get_json("/cheatsheet/arm")
        self.assertGreater(len(data["instructions"]), 0)

    def test_cheatsheet_x86(self):
        data = self.get_json("/cheatsheet/x86")
        self.assertGreater(len(data["instructions"]), 0)

    def test_cheatsheet_unknown_404(self):
        self.get_json("/cheatsheet/mips", expected_status=404)

    def test_topology_has_nodes_edges(self):
        data = self.get_json("/topology/riscv/single_cycle")
        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        self.assertIn("model", data)

    def test_topology_unknown_preset_404(self):
        self.get_json("/topology/riscv/nonexistent", expected_status=404)

    def test_examples_catalog(self):
        data = self.get_json("/examples")
        # At least the three ISAs should have programs
        for isa in ("riscv", "arm", "x86"):
            self.assertIn(isa, data, f"ISA '{isa}' missing from examples catalog")

    def test_examples_dsa_not_in_catalog(self):
        """dsa category is not in _CATEGORY_ORDER so it's excluded from /examples."""
        data = self.get_json("/examples")
        for isa, categories in data.items():
            self.assertNotIn("dsa", categories,
                             f"Unexpected 'dsa' category in {isa} examples catalog")

    def test_examples_single_file(self):
        # Pick a known file
        data = self.get_json("/examples/riscv/algorithms/fibonacci.asm")
        self.assertIn("content", data)
        self.assertIn("file", data)
        self.assertGreater(len(data["content"]), 0)

    def test_examples_bad_path_400(self):
        self.get_json("/examples/riscv/algorithms", expected_status=400)

    def test_examples_not_found_404(self):
        self.get_json("/examples/riscv/algorithms/nonexistent.asm",
                      expected_status=404)


# ── 4. /assemble ─────────────────────────────────────────────────
class TestAssembleEndpoint(APITestBase):

    def test_simple_riscv(self):
        data = self.post_json("/assemble", {
            "isa": "riscv",
            "text": "ADDI x1, x0, 42",
        })
        self.assertEqual(data["isa"], "riscv")
        self.assertIn("program", data)
        self.assertIsInstance(data["program"], list)
        self.assertGreater(len(data["program"]), 0)

    def test_multiline_with_labels(self):
        asm = "ADDI x1, x0, 5\nloop: ADDI x1, x1, -1\nBNE x1, x0, loop"
        data = self.post_json("/assemble", {"isa": "riscv", "text": asm})
        self.assertEqual(len(data["program"]), 3)

    def test_arm_assembly(self):
        data = self.post_json("/assemble", {
            "isa": "arm",
            "text": "MOVZ X1, #10",
        })
        self.assertEqual(data["isa"], "arm")
        self.assertGreater(len(data["program"]), 0)

    def test_x86_assembly(self):
        data = self.post_json("/assemble", {
            "isa": "x86",
            "text": "MOV EAX, 42",
        })
        self.assertEqual(data["isa"], "x86")
        self.assertGreater(len(data["program"]), 0)

    def test_empty_text_400(self):
        self.post_json("/assemble", {"isa": "riscv", "text": ""},
                       expected_status=400)

    def test_invalid_syntax_400(self):
        self.post_json("/assemble", {"isa": "riscv", "text": "GARBAGE"},
                       expected_status=400)

    def test_assemble_then_simulate_hex(self):
        """Roundtrip: assemble to hex, then simulate in hex mode."""
        asm_data = self.post_json("/assemble", {
            "isa": "riscv",
            "text": "ADDI x1, x0, 42",
        })
        sim_data = self.post_json("/simulate", {
            "preset": "riscv/single_cycle",
            "program": asm_data["program"],
            "cycles": 5,
            "input_mode": "hex",
        })
        self.assertIn("cycles", sim_data)
        regs = self.extract_registers(self.extract_final_state(sim_data["cycles"]))
        self.assertIsNotNone(regs)
        self.assertEqual(regs[1], 42)  # x1 = 42


# ── 5. /simulate ─────────────────────────────────────────────────
class TestSimulateEndpoint(APITestBase):

    def test_response_structure(self):
        data = self.post_json("/simulate", {
            "preset": "riscv/single_cycle",
            "cycles": 5,
            "input_mode": "asm",
            "asm_text": "ADDI x1, x0, 7",
        })
        for key in ("preset", "isa", "model", "reg_names", "cycles"):
            self.assertIn(key, data)

    def test_cycle_zero_is_reset(self):
        data = self.post_json("/simulate", {
            "preset": "riscv/single_cycle",
            "cycles": 3,
            "input_mode": "asm",
            "asm_text": "ADDI x1, x0, 1",
        })
        # cycles = reset + 3 ticks = 4 entries
        self.assertEqual(len(data["cycles"]), 4)
        # Cycle 0 has _cycle = 0
        self.assertEqual(data["cycles"][0]["_cycle"], 0)

    def test_cycle_count_matches_request(self):
        for n in (1, 10, 50):
            with self.subTest(cycles=n):
                data = self.post_json("/simulate", {
                    "preset": "riscv/single_cycle",
                    "cycles": n,
                    "input_mode": "asm",
                    "asm_text": "ADDI x1, x0, 1",
                })
                self.assertEqual(len(data["cycles"]), n + 1)  # +1 for reset

    def test_cycle_cap(self):
        data = self.post_json("/simulate", {
            "preset": "riscv/single_cycle",
            "cycles": 99999,
            "input_mode": "asm",
            "asm_text": "ADDI x1, x0, 1",
        })
        # API caps at MAX_CYCLES (+1 for the reset snapshot)
        self.assertEqual(len(data["cycles"]), API_CYCLE_CAP + 1)

    def test_asm_mode_riscv(self):
        data = self.post_json("/simulate", {
            "preset": "riscv/single_cycle",
            "cycles": 5,
            "input_mode": "asm",
            "asm_text": "ADDI x1, x0, 99",
        })
        regs = self.extract_registers(self.extract_final_state(data["cycles"]))
        self.assertEqual(regs[1], 99)

    def test_asm_mode_arm(self):
        data = self.post_json("/simulate", {
            "preset": "arm/single_cycle",
            "cycles": 5,
            "input_mode": "asm",
            "asm_text": "MOVZ X1, #77",
        })
        regs = self.extract_registers(self.extract_final_state(data["cycles"]))
        self.assertEqual(regs[1], 77)

    def test_asm_mode_x86(self):
        data = self.post_json("/simulate", {
            "preset": "x86/single_cycle",
            "cycles": 5,
            "input_mode": "asm",
            "asm_text": "MOV EAX, 55",
        })
        regs = self.extract_registers(self.extract_final_state(data["cycles"]))
        self.assertEqual(regs[0], 55)  # EAX = index 0

    def test_invalid_preset_400(self):
        self.post_json("/simulate", {"preset": "riscv/nonexistent", "cycles": 1},
                       expected_status=400)

    def test_invalid_asm_400(self):
        self.post_json("/simulate", {
            "preset": "riscv/single_cycle",
            "input_mode": "asm",
            "asm_text": "INVALID_GARBAGE",
            "cycles": 1,
        }, expected_status=400)

    def test_pipeline_model(self):
        data = self.post_json("/simulate", {
            "preset": "riscv/pipeline",
            "cycles": 10,
            "input_mode": "asm",
            "asm_text": "ADDI x1, x0, 1",
        })
        self.assertEqual(data["model"], "pipeline")

    def test_ooo_model(self):
        if "riscv/ooo" not in PRESETS:
            self.skipTest("riscv/ooo preset not available")
        data = self.post_json("/simulate", {
            "preset": "riscv/ooo",
            "cycles": 10,
            "input_mode": "asm",
            "asm_text": "ADDI x1, x0, 1",
        })
        self.assertEqual(data["model"], "ooo")

    def test_superscalar_model(self):
        if "riscv/superscalar" not in PRESETS:
            self.skipTest("riscv/superscalar preset not available")
        data = self.post_json("/simulate", {
            "preset": "riscv/superscalar",
            "cycles": 10,
            "num_lanes": 2,
            "input_mode": "asm",
            "asm_text": "ADDI x1, x0, 1\nADDI x2, x0, 2",
        })
        self.assertEqual(data["model"], "superscalar")

    def test_superscalar_accepts_num_lanes(self):
        if "riscv/superscalar" not in PRESETS:
            self.skipTest("riscv/superscalar preset not available")
        for lanes in (2, 4):
            with self.subTest(lanes=lanes):
                data = self.post_json("/simulate", {
                    "preset": "riscv/superscalar",
                    "cycles": 5,
                    "num_lanes": lanes,
                    "input_mode": "asm",
                    "asm_text": "ADDI x1, x0, 1",
                })
                self.assertIn("cycles", data)

    def test_branch_predictor_params(self):
        """Branch predictor name and stage are accepted without error."""
        data = self.post_json("/simulate", {
            "preset": "riscv/pipeline",
            "cycles": 10,
            "input_mode": "asm",
            "asm_text": "ADDI x1, x0, 1",
            "branch_predictor": "",
            "prediction_stage": "id",
        })
        self.assertIn("cycles", data)

    def test_registers_extractable(self):
        data = self.post_json("/simulate", {
            "preset": "riscv/single_cycle",
            "cycles": 5,
            "input_mode": "asm",
            "asm_text": "ADDI x1, x0, 1",
        })
        regs = self.extract_registers(self.extract_final_state(data["cycles"]))
        self.assertIsNotNone(regs)
        self.assertIsInstance(regs, list)

    def test_memory_extractable(self):
        data = self.post_json("/simulate", {
            "preset": "riscv/single_cycle",
            "cycles": 5,
            "input_mode": "asm",
            "asm_text": "ADDI x1, x0, 42\nSW x1, 0(x0)",
        })
        mem = self.extract_memory(self.extract_final_state(data["cycles"]))
        self.assertIsNotNone(mem)
        self.assertIsInstance(mem, list)


# ── 6. Program regression via API ────────────────────────────────
class TestSimulatePrograms(APITestBase):
    """Walk all .asm files with Expected: comments and verify via the API."""

    def test_all_programs_via_api(self):
        if not os.path.isdir(PROGRAMS_DIR):
            self.skipTest("programs/ directory not found")

        # Build set of available presets from the API itself
        presets_data = self.get_json("/presets")
        available_presets = set(presets_data["presets"].keys())

        count = 0
        for isa in ["riscv", "arm", "x86"]:
            isa_dir = os.path.join(PROGRAMS_DIR, isa)
            if not os.path.isdir(isa_dir):
                continue
            for dirpath, _, filenames in os.walk(isa_dir):
                for fname in sorted(filenames):
                    if not fname.endswith(".asm"):
                        continue
                    fpath = os.path.join(dirpath, fname)
                    rel = os.path.relpath(fpath, PROGRAMS_DIR)

                    with open(fpath) as f:
                        text = f.read()

                    reg_expects, mem_expects = _parse_expected(text)
                    if not reg_expects and not mem_expects:
                        continue

                    cycles_hint = _parse_cycles_hint(text)

                    models_hint = _parse_models_hint(text)
                    if models_hint:
                        models = [m for m in models_hint if m in ALL_MODELS[isa]]
                    else:
                        models = _get_default_models(isa, rel)

                    for model in models:
                        preset_name = f"{isa}/{model}"
                        if preset_name not in available_presets:
                            continue

                        multiplier = MODEL_CYCLE_MULTIPLIER[model]
                        if cycles_hint:
                            raw_cycles = cycles_hint * multiplier
                        else:
                            raw_cycles = BASE_CYCLES * multiplier
                        num_cycles = min(raw_cycles, API_CYCLE_CAP)

                        # Skip if the program needs more cycles than the API cap
                        if raw_cycles > API_CYCLE_CAP:
                            continue

                        body = {
                            "preset": preset_name,
                            "cycles": num_cycles,
                            "input_mode": "asm",
                            "asm_text": text,
                        }
                        if model == "superscalar":
                            body["num_lanes"] = 2

                        with self.subTest(isa=isa, model=model, file=rel):
                            data = self.post_json("/simulate", body)
                            final = self.extract_final_state(data["cycles"])
                            regs = self.extract_registers(final)
                            mem = self.extract_memory(final)

                            self.assertIsNotNone(
                                regs,
                                f"{rel} [{model}]: no register data in API response")

                            for reg_name, expected_val in reg_expects.items():
                                idx = _get_reg_index(isa, reg_name)
                                if idx is None:
                                    continue
                                actual = regs[idx]
                                if expected_val < 0:
                                    expected_val = expected_val & 0xFFFFFFFF
                                self.assertEqual(
                                    actual, expected_val,
                                    f"{rel} [{model}] via API: {reg_name} "
                                    f"expected {expected_val}, got {actual}")

                            if mem_expects and mem is not None:
                                for byte_addr, expected_val in mem_expects.items():
                                    word_addr = byte_addr // 4
                                    actual = (
                                        mem[word_addr]
                                        if word_addr < len(mem)
                                        else 0
                                    )
                                    self.assertEqual(
                                        actual, expected_val,
                                        f"{rel} [{model}] via API: mem[{byte_addr}] "
                                        f"expected {expected_val}, got {actual}")

                        count += 1

        self.assertGreater(count, 0, "No programs with Expected: comments found")


# ── 7. ARM bubble sort targeted regression ────────────────────────
class TestArmBubbleSortRegression(APITestBase):
    """
    Targeted regression for the ARM bubble_sort bug that showed
    mem=[10,20,20,40,30] instead of [10,20,30,40,50] in the UI.
    """

    def test_arm_bubble_sort_single_cycle(self):
        fpath = os.path.join(PROGRAMS_DIR, "arm", "algorithms", "bubble_sort.asm")
        if not os.path.isfile(fpath):
            self.skipTest("arm/algorithms/bubble_sort.asm not found")
        with open(fpath) as f:
            text = f.read()

        data = self.post_json("/simulate", {
            "preset": "arm/single_cycle",
            "cycles": 500,
            "input_mode": "asm",
            "asm_text": text,
        })

        final = self.extract_final_state(data["cycles"])
        regs = self.extract_registers(final)
        mem = self.extract_memory(final)

        self.assertIsNotNone(regs)
        self.assertIsNotNone(mem)

        # Register expectations
        self.assertEqual(regs[5], 10, "X5 should be 10")
        self.assertEqual(regs[6], 20, "X6 should be 20")
        self.assertEqual(regs[7], 30, "X7 should be 30")
        self.assertEqual(regs[8], 40, "X8 should be 40")
        self.assertEqual(regs[9], 50, "X9 should be 50")

        # Memory expectations (word-addressed: byte_addr // 4)
        self.assertEqual(mem[0 // 4], 10, "mem[0] should be 10")
        self.assertEqual(mem[8 // 4], 20, "mem[8] should be 20")
        self.assertEqual(mem[16 // 4], 30, "mem[16] should be 30")
        self.assertEqual(mem[24 // 4], 40, "mem[24] should be 40")
        self.assertEqual(mem[32 // 4], 50, "mem[32] should be 50")

    def test_arm_bubble_sort_pipeline(self):
        fpath = os.path.join(PROGRAMS_DIR, "arm", "algorithms", "bubble_sort.asm")
        if not os.path.isfile(fpath):
            self.skipTest("arm/algorithms/bubble_sort.asm not found")
        if "arm/pipeline" not in PRESETS:
            self.skipTest("arm/pipeline preset not available")
        with open(fpath) as f:
            text = f.read()

        data = self.post_json("/simulate", {
            "preset": "arm/pipeline",
            "cycles": 500,
            "input_mode": "asm",
            "asm_text": text,
        })

        final = self.extract_final_state(data["cycles"])
        regs = self.extract_registers(final)
        mem = self.extract_memory(final)

        self.assertIsNotNone(regs)
        self.assertIsNotNone(mem)

        self.assertEqual(regs[5], 10, "X5 should be 10")
        self.assertEqual(regs[6], 20, "X6 should be 20")
        self.assertEqual(regs[7], 30, "X7 should be 30")
        self.assertEqual(regs[8], 40, "X8 should be 40")
        self.assertEqual(regs[9], 50, "X9 should be 50")

        self.assertEqual(mem[0 // 4], 10, "mem[0] should be 10")
        self.assertEqual(mem[8 // 4], 20, "mem[8] should be 20")
        self.assertEqual(mem[16 // 4], 30, "mem[16] should be 30")
        self.assertEqual(mem[24 // 4], 40, "mem[24] should be 40")
        self.assertEqual(mem[32 // 4], 50, "mem[32] should be 50")


if __name__ == "__main__":
    unittest.main()
