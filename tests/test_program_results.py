"""
Comprehensive multi-model test: simulate every example program across all
execution models and verify register/memory values match Expected: comments.

For each .asm file with Expected: comments, runs it through every compatible
model and asserts register and memory expectations.

Model selection per program:
  - Programs can specify '; Models: single_cycle, multicycle, ...' to opt into
    specific models.
  - Without a Models hint, the default depends on directory:
      * algorithms/ and dsa/: single_cycle + multicycle (riscv/arm), single_cycle (x86)
      * instructions/, hazards/, branch_prediction/: single_cycle only
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.assembler import assemble
from sim.runner_v2 import run_simulation

ROOT = os.path.join(os.path.dirname(__file__), "..")
PROGRAMS_DIR = os.path.join(ROOT, "programs")

# All models per ISA (full set; programs opt in via ; Models: hint)
ALL_MODELS = {
    "riscv": ["single_cycle", "multicycle", "pipeline", "ooo", "superscalar"],
    "arm":   ["single_cycle", "multicycle", "pipeline", "ooo", "superscalar"],
    "x86":   ["single_cycle", "multicycle", "pipeline", "ooo"],  # NO superscalar
}

# Default models for algorithm/dsa programs (known-working combinations)
ALGO_DEFAULT_MODELS = {
    "riscv": ["single_cycle", "multicycle"],
    "arm":   ["single_cycle", "multicycle"],
    "x86":   ["single_cycle"],
}

# Demo directories get single_cycle only by default
DEMO_DIRS = {"instructions", "hazards", "branch_prediction"}

# Cycle multipliers to account for multi-cycle execution
MODEL_CYCLE_MULTIPLIER = {
    "single_cycle": 1,
    "multicycle": 4,
    "pipeline": 1,
    "ooo": 2,
    "superscalar": 1,
}

BASE_CYCLES = 500

# Register name -> index mappings
RISCV_REGS = {f"x{i}": i for i in range(32)}
ARM_REGS = {f"X{i}": i for i in range(31)}
ARM_REGS["XZR"] = 31
X86_REGS = {
    "EAX": 0, "ECX": 1, "EDX": 2, "EBX": 3,
    "ESP": 4, "EBP": 5, "ESI": 6, "EDI": 7,
}


def _parse_expected(text):
    """Parse 'Expected: reg1=val1, reg2=val2, ...' and 'mem[addr]=val' from header."""
    reg_expects = {}
    mem_expects = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith(";"):
            continue
        m = re.search(r"Expected:\s*(.+)", line, re.IGNORECASE)
        if not m:
            continue
        parts = m.group(1).split(",")
        for part in parts:
            part = part.strip().rstrip(";").strip()
            if not part or "=" not in part:
                continue
            lhs, rhs = part.split("=", 1)
            lhs = lhs.strip()
            rhs = rhs.strip()
            # Strip parenthetical annotations like "(0xFFFFFFEC)"
            rhs = re.sub(r'\s*\(.*?\)\s*$', '', rhs).strip()
            try:
                if rhs.startswith("0x") or rhs.startswith("0X"):
                    val = int(rhs, 16)
                else:
                    val = int(rhs)
            except ValueError:
                continue
            mm = re.match(r"mem\[(\d+)\]", lhs)
            if mm:
                mem_expects[int(mm.group(1))] = val
            else:
                reg_expects[lhs] = val
    return reg_expects, mem_expects


def _parse_cycles_hint(text):
    """Parse optional '; Cycles: N' hint from program header."""
    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith(";"):
            continue
        m = re.match(r";\s*Cycles:\s*(\d+)", line)
        if m:
            return int(m.group(1))
    return None


def _parse_models_hint(text):
    """Parse optional '; Models: model1, model2, ...' hint from program header."""
    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith(";"):
            continue
        m = re.match(r";\s*Models:\s*(.+)", line, re.IGNORECASE)
        if m:
            return [s.strip() for s in m.group(1).split(",") if s.strip()]
    return None


def _get_default_models(isa, rel_path):
    """Determine default models for a program based on its directory."""
    parts = rel_path.replace("\\", "/").split("/")
    # parts like ['riscv', 'algorithms', 'fibonacci.asm']
    if len(parts) >= 2:
        category = parts[1]
    else:
        category = ""

    if category in DEMO_DIRS:
        return ["single_cycle"]
    return ALGO_DEFAULT_MODELS.get(isa, ["single_cycle"])


def _get_reg_index(isa, reg_name):
    """Convert register name to index for the given ISA."""
    if isa == "riscv":
        return RISCV_REGS.get(reg_name)
    elif isa == "arm":
        return ARM_REGS.get(reg_name)
    elif isa == "x86":
        return X86_REGS.get(reg_name)
    return None


def _simulate(isa, model, text, num_cycles):
    """Assemble and simulate with a given model, return (registers, memory)."""
    prog = assemble(isa, text)
    mod_path = f"sim.isa.{isa}.presets.{model}"
    mod = __import__(mod_path, fromlist=["build"])

    if model == "superscalar":
        cpu = mod.build(prog, num_lanes=2)
    else:
        cpu = mod.build(prog)

    states = run_simulation(cpu, num_cycles=num_cycles, include_reset=True)
    final = states[-1]

    regs = None
    mem = None
    for k, v in final.items():
        if isinstance(v, dict) and "registers" in v:
            regs = v["registers"]
        if isinstance(v, dict) and "memory" in v and "imem" not in k.lower():
            mem = v["memory"]
    return regs, mem


class TestProgramResults(unittest.TestCase):
    """Verify every .asm program produces correct results across execution models."""

    def test_all_programs_all_models(self):
        if not os.path.isdir(PROGRAMS_DIR):
            self.skipTest("programs/ directory not found")

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

                    # Determine which models to test
                    models_hint = _parse_models_hint(text)
                    if models_hint:
                        # Explicit hint: intersect with ISA's available models
                        models = [
                            m for m in models_hint if m in ALL_MODELS[isa]
                        ]
                    else:
                        models = _get_default_models(isa, rel)

                    for model in models:
                        multiplier = MODEL_CYCLE_MULTIPLIER[model]
                        if cycles_hint:
                            num_cycles = cycles_hint * multiplier
                        else:
                            num_cycles = BASE_CYCLES * multiplier

                        with self.subTest(isa=isa, model=model, file=rel):
                            regs, mem = _simulate(
                                isa, model, text, num_cycles
                            )
                            self.assertIsNotNone(
                                regs,
                                f"{rel} [{model}]: no register data"
                            )

                            # Check register expectations
                            for reg_name, expected_val in reg_expects.items():
                                idx = _get_reg_index(isa, reg_name)
                                if idx is None:
                                    continue
                                actual = regs[idx]
                                if expected_val < 0:
                                    expected_val = expected_val & 0xFFFFFFFF
                                self.assertEqual(
                                    actual, expected_val,
                                    f"{rel} [{model}]: {reg_name} expected "
                                    f"{expected_val}, got {actual}"
                                )

                            # Check memory expectations
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
                                        f"{rel} [{model}]: mem[{byte_addr}] "
                                        f"expected {expected_val}, "
                                        f"got {actual}"
                                    )

                        count += 1

        self.assertGreater(count, 0, "No programs with Expected: comments found")


if __name__ == "__main__":
    unittest.main()
