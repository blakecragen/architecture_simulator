"""Core-C compiler EXPANSION features (2026-07).

Covers the batch added on top of Core-C v1: compile-time-constant array sizes,
++/--, compound assignment, ternary ?:, bitwise & | ^ ~, break/continue, global
variables, array initializers, and array parameters. Front-end parsing, located
errors, and end-to-end correctness (compile -> assemble -> simulate) with
cross-model / cross-ISA agreement.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.compiler import compile_c
from sim.compiler.parser import parse
from sim.compiler.errors import CompilerError
from sim.harness import compile_and_simulate

_RET = {"riscv": "a0", "arm": "X0", "x86": "EAX"}


def _run(src, isa="riscv", model="single_cycle", cycles=8000):
    r = compile_and_simulate(isa, model, src, cycles=cycles)
    v = r.reg(_RET[isa])
    return v if v < 2**31 else v - 2**32   # as signed


USER_PROGRAM = """
int main() {
    int arrayLen = 100;
    int arr[arrayLen];
    int i;
    int sum = 0;
    for (i = 0; i < arrayLen/4; i = i + 4) {
        arr[i] = i + 1;
        arr[i + 1] = i + 2;
        arr[i + 2] = i + 3;
        arr[i + 3] = i + 4;
    }
    for (i = 0; i < arrayLen; i = i + 1) {
        sum = sum + arr[i];
    }
    return sum;
}
"""


class TestFrontEnd(unittest.TestCase):
    def test_user_program_parses_and_runs(self):
        # was rejected: "expected NUMBER, got 'arrayLen'"
        self.assertEqual(_run(USER_PROGRAM), 406)   # sum(1..28)

    def test_located_errors(self):
        for src, frag in [
            ("int main(){int i; int a[i]; return a[0];}", "compile-time constant"),
            ("int main(){int a[3]={1,2,3,4}; return a[0];}", "too many initializers"),
            ("int main(){int *p; return 0;}", "pointer variable"),
            ("int main(){break; return 0;}", "'break' outside a loop"),
            ("int main(){continue; return 0;}", "'continue' outside a loop"),
        ]:
            with self.subTest(src=src):
                with self.assertRaises(CompilerError) as cm:
                    compile_c(src, "riscv")
                self.assertIn(frag, str(cm.exception))


class TestOperators(unittest.TestCase):
    def test_bitwise_precedence_and_not(self):
        # & binds tighter than |, ~x == x ^ -1
        self.assertEqual(_run("int main(){int m=0xF0&0x3C|0x1; return ~m^2;}"),
                         (~((0xF0 & 0x3C) | 0x1) ^ 2))

    def test_shifts(self):
        self.assertEqual(_run("int main(){return (1<<10) + (256>>2);}"), 1024 + 64)

    def test_prefix_and_postfix_incdec(self):
        # prefix yields new value, postfix yields old
        self.assertEqual(_run("int main(){int i=5; int a=++i; return a*100+i;}"), 606)
        self.assertEqual(_run("int main(){int i=5; int a=i++; return a*100+i;}"), 506)

    def test_compound_assignment(self):
        self.assertEqual(_run("int main(){int s=10; s+=5; s*=2; s-=3; s<<=1; return s;}"),
                         (((10 + 5) * 2 - 3) << 1))
        self.assertEqual(_run("int main(){int s=0xFF; s&=0x0F; s|=0x30; s^=0x01; return s;}"),
                         ((0xFF & 0x0F) | 0x30) ^ 0x01)

    def test_ternary(self):
        self.assertEqual(_run("int main(){int n=5; return n>3?100:-1;}"), 100)
        self.assertEqual(_run("int main(){int n=2; return n>3?100:-1;}"), -1)


class TestControlFlow(unittest.TestCase):
    def test_break_and_continue(self):
        src = ("int main(){int s=0;int i;for(i=0;i<20;i++){"
               "if(i==3)continue; if(i==7)break; s+=i;} return s;}")
        self.assertEqual(_run(src), 0 + 1 + 2 + 4 + 5 + 6)

    def test_continue_in_while_runs_forever_guard(self):
        # continue must re-test the while condition (not skip the i++ that the
        # body performs) — else this would loop forever / miscount.
        src = "int main(){int i=0;int s=0;while(i<5){i++; if(i==3)continue; s+=i;} return s;}"
        self.assertEqual(_run(src), 1 + 2 + 4 + 5)


class TestArrays(unittest.TestCase):
    def test_constant_array_size_expression(self):
        self.assertEqual(
            _run("int main(){const int N=8; int a[N*2]; int i;"
                 "for(i=0;i<16;i++)a[i]=i; return a[15];}"), 15)

    def test_array_initializer_with_zero_fill(self):
        self.assertEqual(_run("int main(){int a[5]={1,2}; "
                              "return a[0]+a[1]+a[2]+a[3]+a[4];}"), 3)

    def test_inferred_size_initializer(self):
        self.assertEqual(_run("int main(){int a[]={5,10,15}; return a[0]+a[1]+a[2];}"), 30)

    def test_array_parameter_pass_by_reference(self):
        src = ("int total(int a[], int n){int s=0;int i;for(i=0;i<n;i++)s+=a[i];return s;}"
               "int main(){int x[5]={2,4,6,8,10}; return total(x,5);}")
        self.assertEqual(_run(src), 30)

    def test_array_param_can_mutate_caller_array(self):
        src = ("int bump(int a[], int n){int i;for(i=0;i<n;i++)a[i]+=1;return 0;}"
               "int main(){int x[3]={1,2,3}; bump(x,3); return x[0]+x[1]+x[2];}")
        self.assertEqual(_run(src), 2 + 3 + 4)


class TestGlobals(unittest.TestCase):
    def test_global_scalar(self):
        self.assertEqual(_run("int g=7; int main(){g+=5; return g;}"), 12)

    def test_global_array(self):
        self.assertEqual(_run("int t[3]={10,20,30}; int main(){return t[0]+t[1]+t[2];}"), 60)

    def test_global_shared_across_functions(self):
        src = ("int counter=0; int bump(){counter+=1; return counter;}"
               "int main(){bump(); bump(); return bump();}")
        self.assertEqual(_run(src), 3)


class TestCrossModelAgreement(unittest.TestCase):
    """The new features must be correct on every in-order model and ISA."""

    def test_features_agree_across_models_and_isas(self):
        cases = [
            ("int main(){int m=0xF0&0x3C|0x1; return ~m^2;}", None, ("riscv", "arm", "x86")),
            ("int main(){int s=0;int i;for(i=1;i<=10;i++)s+=i; return s;}", 55, ("riscv", "arm", "x86")),
            ("int g=100; int t[4]={1,2,3,4}; int main(){int s=g;int i;"
             "for(i=0;i<4;i++)s+=t[i]; return s;}", 110, ("riscv", "arm", "x86")),
            ("int total(int a[],int n){int s=0;int i;for(i=0;i<n;i++)s+=a[i];return s;}"
             "int main(){int x[5]={2,4,6,8,10}; return total(x,5);}", 30, ("riscv", "arm")),
        ]
        for src, expect, isas in cases:
            for isa in isas:
                vals = {m: _run(src, isa, m) for m in ("single_cycle", "multicycle", "pipeline")}
                with self.subTest(isa=isa, src=src[:30]):
                    self.assertEqual(len(set(vals.values())), 1,
                                     f"{isa} models disagree: {vals}")
                    if expect is not None:
                        self.assertEqual(vals["single_cycle"], expect)


if __name__ == "__main__":
    unittest.main()
