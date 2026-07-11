"""
Test that every example .asm program in programs/ assembles successfully.

Walks the programs/ directory, calls assemble(isa, text) for each .asm file,
and asserts that each produces a non-empty program list.
"""
import os
import unittest

from sim.assembler import assemble

ROOT = os.path.join(os.path.dirname(__file__), "..")
PROGRAMS_DIR = os.path.join(ROOT, "programs")

VALID_ISAS = {"riscv", "arm", "x86"}


class TestExamplePrograms(unittest.TestCase):
    """Verify that every .asm file under programs/ assembles without error."""

    def test_all_examples_assemble(self):
        """Walk programs/ and assemble every .asm file."""
        if not os.path.isdir(PROGRAMS_DIR):
            self.skipTest("programs/ directory not found")

        count = 0
        for isa in sorted(os.listdir(PROGRAMS_DIR)):
            isa_dir = os.path.join(PROGRAMS_DIR, isa)
            if isa not in VALID_ISAS or not os.path.isdir(isa_dir):
                continue
            for dirpath, _, filenames in os.walk(isa_dir):
                for fname in sorted(filenames):
                    if not fname.endswith(".asm"):
                        continue
                    fpath = os.path.join(dirpath, fname)
                    rel = os.path.relpath(fpath, PROGRAMS_DIR)
                    with self.subTest(isa=isa, file=rel):
                        with open(fpath, "r") as f:
                            text = f.read()
                        program = assemble(isa, text)
                        self.assertIsInstance(program, list,
                                             f"{rel}: expected list, got {type(program)}")
                        self.assertGreater(len(program), 0,
                                           f"{rel}: assembled to empty program")
                    count += 1

        self.assertGreater(count, 0, "No .asm files found in programs/")


if __name__ == "__main__":
    unittest.main()
