"""
Tests for the Core-C compiler (``sim.compiler``).

Three layers:
  * front end — lex/parse a minimal program, populate the UI stages, and REJECT
    out-of-scope constructs (struct/float/char/double-pointer, unknown ISA,
    x86 recursion) with a ``CompilerError``;
  * assembles-clean — every sample program, for each ISA it targets, compiles to
    assembly the project assembler accepts with no ``AssemblerError`` (this is
    what proves the codegen respects each ISA's mnemonic/immediate constraints);
  * end-to-end — compiled programs compute the expected answer on the in-order
    models and agree across them.

``sim.harness.simulate`` is NOT cycle-capped (only the Flask /simulate route is),
so these tests give the verbose compiled code enough cycles to converge
(measured worst case ~1050 on riscv/pipeline; multicycle runs at ~3-5 CPI).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.compiler import compile_c, CompilerError
from sim.assembler import assemble
from sim.harness import compile_and_simulate

C_DIR = os.path.join(os.path.dirname(__file__), "..", "programs", "c")

# program file -> (expected return value, ISAs it targets)
PROGRAMS = {
    "sum_to_n.c":            (55,  ["riscv", "arm", "x86"]),
    "fib_iter.c":            (55,  ["riscv", "arm", "x86"]),
    "factorial_iter.c":      (120, ["riscv", "arm", "x86"]),
    "gcd.c":                 (12,  ["riscv", "arm"]),
    "factorial_recursive.c": (120, ["riscv", "arm"]),
    # Compiler-tab example set (arrays, nested loops, logical ops, sorting,
    # double recursion, shifts) — expected values from each file's header.
    "array_sum.c":           (15,  ["riscv", "arm", "x86"]),
    "nested_loops.c":        (55,  ["riscv", "arm", "x86"]),
    "logic_ops.c":           (7,   ["riscv", "arm", "x86"]),
    "bubble_sort.c":         (7,   ["riscv", "arm", "x86"]),
    "fib_recursive.c":       (13,  ["riscv", "arm"]),
    "collatz.c":             (16,  ["riscv"]),
    # Expansion samples: const-sized array + ++/+= ; and a features showcase
    # (globals, ternary, bitwise, break/continue, array initializer).
    "array_fill.c":          (506, ["riscv", "arm", "x86"]),
    "features_showcase.c":   (248, ["riscv", "arm", "x86"]),
}

# Return-value register index by ISA (RISC-V a0=x10, ARM X0, x86 EAX).
RETURN_IDX = {"riscv": 10, "arm": 0, "x86": 0}

# Generous per-model cycle budgets (verbose codegen; multicycle is ~3-5 CPI).
MODEL_CYCLES = {"single_cycle": 2500, "multicycle": 7000, "pipeline": 3500}


def _src(name):
    with open(os.path.join(C_DIR, name)) as f:
        return f.read()


class TestFrontEnd(unittest.TestCase):

    def test_tokenize_and_parse_minimal(self):
        res = compile_c("int main() { int a = 2; return a + 3; }", "riscv")
        self.assertTrue(res.asm.strip())
        self.assertGreater(len(res.tokens), 5)
        self.assertIn("functions", res.ast)

    def test_source_map_present(self):
        res = compile_c(_src("sum_to_n.c"), "riscv")
        self.assertTrue(res.source_map, "expected a non-empty asm->C source map")
        for entry in res.source_map:
            self.assertIn("asm_line", entry)
            self.assertIn("c_line", entry)

    def test_runtime_helpers_untagged_in_source_map(self):
        """__mul/__divmod bodies (emitted in emit_runtime()) must NOT appear
        in the source map — they're compiler plumbing, not user source, and
        the /lab line-stepper relies on them being invisible (a stepOver of
        a '*' expression shouldn't wander into the helper's internals). The
        CALL SITE inside the function body keeps its real C line; only the
        helper's own body (after the 'JAL ra, __mul' label) is untagged."""
        for isa in ("riscv", "arm"):
            res = compile_c(
                "int main() { int a = 6; int b = 7; return a * b; }", isa)
            lines = res.asm.split("\n")
            mapped_asm_lines = {e["asm_line"] for e in res.source_map}
            in_helper = False
            for i, line in enumerate(lines, start=1):
                stripped = line.strip()
                if stripped.startswith(("__mul:", "__divmod:")):
                    in_helper = True
                if in_helper:
                    self.assertNotIn(
                        i, mapped_asm_lines,
                        f"{isa}: helper body line {i} ({stripped!r}) should "
                        f"be untagged")

    def test_unknown_isa_raises(self):
        with self.assertRaises(CompilerError):
            compile_c("int main(){return 0;}", "zzz")

    def test_rejects_out_of_scope(self):
        cases = [
            "struct P { int x; }; int main(){ return 0; }",   # struct
            "int main(){ float f = 1; return 0; }",           # float
            "int main(){ char c = 65; return 0; }",           # char
            "int main(){ int **pp; return 0; }",              # double pointer
        ]
        for src in cases:
            with self.assertRaises(CompilerError, msg=f"should reject: {src!r}"):
                compile_c(src, "riscv")

    def test_x86_rejects_recursion(self):
        # x86 has no modelled CALL/RET stack -> recursion is a compile error.
        with self.assertRaises(CompilerError):
            compile_c(_src("factorial_recursive.c"), "x86")


class TestAssemblesClean(unittest.TestCase):
    """Every sample compiles to asm the project assembler accepts (no error)."""

    def test_all_samples_assemble(self):
        for name, (_expected, isas) in PROGRAMS.items():
            for isa in isas:
                with self.subTest(program=name, isa=isa):
                    asm = compile_c(_src(name), isa).asm
                    program = assemble(isa, asm)  # raises on any bad encoding
                    self.assertGreater(len(program), 0)


class TestEndToEnd(unittest.TestCase):
    """Compiled programs compute the right answer on the in-order models."""

    def test_correctness(self):
        for name, (expected, isas) in PROGRAMS.items():
            for isa in isas:
                # x86 pipeline is only illustratively verified elsewhere; assert
                # x86 on single_cycle (the clearest model) and riscv/arm on both.
                models = ["single_cycle"] if isa == "x86" else ["single_cycle", "pipeline"]
                for model in models:
                    with self.subTest(program=name, isa=isa, model=model):
                        r = compile_and_simulate(isa, model, _src(name),
                                                 cycles=MODEL_CYCLES[model])
                        self.assertEqual(r.reg(RETURN_IDX[isa]), expected)

    def test_cross_model_agreement(self):
        # Light programs also run on multicycle; all three in-order models agree.
        for name in ("sum_to_n.c", "fib_iter.c", "factorial_iter.c"):
            expected, _isas = PROGRAMS[name]
            for isa in ("riscv", "arm"):
                vals = {}
                for model in ("single_cycle", "multicycle", "pipeline"):
                    r = compile_and_simulate(isa, model, _src(name),
                                             cycles=MODEL_CYCLES[model])
                    vals[model] = r.reg(RETURN_IDX[isa])
                with self.subTest(program=name, isa=isa):
                    self.assertEqual(set(vals.values()), {expected}, vals)


if __name__ == "__main__":
    unittest.main()
