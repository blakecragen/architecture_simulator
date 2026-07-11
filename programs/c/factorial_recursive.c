// factorial_recursive: 5! computed with a recursive function call.
// Expected return value: 120.
// Targets: riscv, arm (single_cycle, multicycle, pipeline).
// Exercises the software call stack (frame save/restore of the return address)
// and recursion. The x86 backend has no modelled CALL/RET stack, so recursion
// (and any multi-function program) is rejected there with a CompilerError.
int fact(int n) {
    if (n <= 1) {
        return 1;
    }
    return n * fact(n - 1);
}

int main() {
    return fact(5);
}
