"""Core-C print() builtin + debugger symbol table (used by the /lab page).

print(expr) compiles to a store of the value at PRINT_ADDR (byte 2040, word
510) on every backend; /compile exposes `symbols` with static addresses for
main's locals. Both are verified end-to-end: compile -> assemble -> simulate
single_cycle -> inspect dmem state.

Data memory is 64 KB (16384 words) and the per-cycle snapshot is a dense low
window + a sparse `memory_hi` map for high words (the riscv/arm software stack
lives near the top of memory), so reads go through `_dmem_word` which
reconstructs any word from either half.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.harness import PRESETS
from sim.compiler import compile_c
from sim.compiler.codegen.base import PRINT_ADDR
from sim.assembler import assemble
from sim.runner_v2 import run_simulation

ISAS = ("riscv", "arm", "x86")


def _dmem_word(state, byte_addr):
    """Reconstruct one data-memory word from the dense window + sparse high map."""
    d = state["dmem"]
    size = d.get("size", len(d["memory"]))
    w = (byte_addr >> 2) % size
    dense = d["memory"]
    if w < len(dense):
        return dense[w]
    hi = d.get("memory_hi", {})
    return hi.get(w, hi.get(str(w), 0))


def _same_word(addr_a, addr_b, size):
    return (addr_a >> 2) % size == (addr_b >> 2) % size

SRC = """
int main() {
    int a = 6;
    int b = 7;
    int c = a * b;
    print(c);
    print(a + b);
    return c;
}
"""


def _run(isa, asm):
    prog = assemble(isa, asm)
    return run_simulation(PRESETS[f"{isa}/single_cycle"]["build"](prog),
                          num_cycles=5000, include_reset=True, until_stable=True)


def _print_events(states):
    """Replicates the lab terminal's detection: dmem writes to the console
    word, deduping identical write signals held across consecutive cycles."""
    events, prev = [], None
    for st in states:
        d = st.get("dmem") or {}
        if not d.get("wen"):
            prev = None
            continue
        size = d.get("size", len(d.get("memory", [])) or 1)
        sig = (d.get("write_addr"), d.get("wdata"))
        if _same_word(d.get("write_addr", 0), PRINT_ADDR, size) and sig != prev:
            events.append(d["wdata"])
        prev = sig
    return events


class TestPrintBuiltin(unittest.TestCase):
    def test_print_stores_to_console_word_on_every_isa(self):
        for isa in ISAS:
            with self.subTest(isa=isa):
                states = _run(isa, compile_c(SRC, isa).asm)
                self.assertEqual(_print_events(states), [42, 13])

    def test_print_wrong_arity_rejected(self):
        from sim.compiler.errors import CompilerError
        with self.assertRaises(CompilerError):
            compile_c("int main() { print(1, 2); return 0; }", "riscv")

    def test_user_function_named_print_shadows_builtin(self):
        src = """
        int print(int x) { return x + 1; }
        int main() { return print(4); }
        """
        # riscv supports multiple functions; the user's print must win.
        asm = compile_c(src, "riscv").asm
        self.assertIn("func_print", asm)
        states = _run("riscv", asm)
        self.assertEqual(_print_events(states), [])  # no console stores


class TestDebuggerSymbols(unittest.TestCase):
    def test_symbol_addresses_hold_final_values(self):
        for isa in ISAS:
            with self.subTest(isa=isa):
                result = compile_c(SRC, isa)
                syms = {s["name"]: s for s in result.symbols}
                self.assertEqual(set(syms), {"a", "b", "c"})
                states = _run(isa, result.asm)
                last = states[-1]
                values = {n: _dmem_word(last, s["addr"]) for n, s in syms.items()}
                self.assertEqual(values, {"a": 6, "b": 7, "c": 42})

    def test_symbols_include_location_and_stride(self):
        for isa, frag in (("riscv", "(sp)"), ("arm", "[X28"), ("x86", "[EBP")):
            with self.subTest(isa=isa):
                syms = compile_c(SRC, isa).symbols
                self.assertTrue(all(frag in s["location"] for s in syms))
                self.assertTrue(all(s["stride"] in (4, 8) for s in syms))

    def test_array_symbol_spans_elements(self):
        src = """
        int main() {
            int arr[3];
            arr[0] = 11; arr[1] = 22; arr[2] = 33;
            return arr[1];
        }
        """
        result = compile_c(src, "riscv")
        arr = next(s for s in result.symbols if s["name"] == "arr")
        self.assertEqual((arr["kind"], arr["size"]), ("array", 3))
        states = _run("riscv", result.asm)
        last = states[-1]
        got = [_dmem_word(last, arr["addr"] + i * arr["stride"])
               for i in range(3)]
        self.assertEqual(got, [11, 22, 33])

    def test_dmem_state_exposes_write_addr(self):
        states = _run("riscv", compile_c(SRC, "riscv").asm)
        self.assertTrue(any("write_addr" in (st.get("dmem") or {})
                            for st in states))


if __name__ == "__main__":
    unittest.main()
