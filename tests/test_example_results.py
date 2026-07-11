"""
Comprehensive test: simulate every example program and verify register/memory values
match the Expected: comments in each file header.
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

# Register name → index mappings
RISCV_REGS = {f"x{i}": i for i in range(32)}
ARM_REGS = {f"X{i}": i for i in range(31)}
ARM_REGS["XZR"] = 31
X86_REGS = {"EAX": 0, "ECX": 1, "EDX": 2, "EBX": 3, "ESP": 4, "EBP": 5, "ESI": 6, "EDI": 7}


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
            # Strip parenthetical annotations like "(0xFFFFFFEC)" or "(sign-extended)"
            rhs = re.sub(r'\s*\(.*?\)\s*$', '', rhs).strip()
            # Parse value
            try:
                if rhs.startswith("0x") or rhs.startswith("0X"):
                    val = int(rhs, 16)
                else:
                    val = int(rhs)
            except ValueError:
                continue
            # mem[addr] format
            mm = re.match(r"mem\[(\d+)\]", lhs)
            if mm:
                mem_expects[int(mm.group(1))] = val
            else:
                reg_expects[lhs] = val
    return reg_expects, mem_expects


def _get_reg_index(isa, reg_name):
    """Convert register name to index for the given ISA."""
    if isa == "riscv":
        return RISCV_REGS.get(reg_name)
    elif isa == "arm":
        return ARM_REGS.get(reg_name)
    elif isa == "x86":
        return X86_REGS.get(reg_name)
    return None


def _simulate(isa, text):
    """Assemble and simulate, return (registers, memory)."""
    prog = assemble(isa, text)
    mod_path = f"sim.isa.{isa}.presets.single_cycle"
    mod = __import__(mod_path, fromlist=["build"])
    cpu = mod.build(prog)
    states = run_simulation(cpu, num_cycles=500, include_reset=True)
    final = states[-1]

    regs = None
    mem = None
    for k, v in final.items():
        if isinstance(v, dict) and "registers" in v:
            regs = v["registers"]
        if isinstance(v, dict) and "memory" in v and "imem" not in k.lower():
            mem = v["memory"]
    return regs, mem


class TestExampleResults(unittest.TestCase):
    """Verify every .asm program produces correct register/memory values."""

    def test_all_examples_correct(self):
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
                        # No expected values to check
                        continue

                    with self.subTest(isa=isa, file=rel):
                        regs, mem = _simulate(isa, text)
                        self.assertIsNotNone(regs, f"{rel}: no register data")

                        # Check register expectations
                        for reg_name, expected_val in reg_expects.items():
                            idx = _get_reg_index(isa, reg_name)
                            if idx is None:
                                continue
                            actual = regs[idx]
                            # Handle 32-bit unsigned wraparound
                            if expected_val < 0:
                                expected_val = expected_val & 0xFFFFFFFF
                            self.assertEqual(
                                actual, expected_val,
                                f"{rel}: {reg_name} expected {expected_val}, got {actual}"
                            )

                        # Check memory expectations
                        if mem_expects and mem is not None:
                            for byte_addr, expected_val in mem_expects.items():
                                word_addr = byte_addr // 4
                                actual = mem[word_addr] if word_addr < len(mem) else 0
                                self.assertEqual(
                                    actual, expected_val,
                                    f"{rel}: mem[{byte_addr}] expected {expected_val}, got {actual}"
                                )

                    count += 1

        self.assertGreater(count, 0, "No programs with Expected: comments found")


if __name__ == "__main__":
    unittest.main()
