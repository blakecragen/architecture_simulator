// fib_recursive: naive double recursion — fib(7) = 13 (0,1,1,2,3,5,8,13).
// Expected return value: 13.
// Targets: riscv, arm (single_cycle, multicycle, pipeline).
// Exercises TWO recursive calls per frame (the callee-save path across the
// first call). The x86 backend has no CALL/RET stack, so recursion targets
// RISC-V and ARM only. (Multicycle needs ~4000 cycles — above the UI's
// 2000-cycle cap; use single-cycle or pipeline in the app.)
int fib(int n) {
    if (n < 2) {
        return n;
    }
    return fib(n - 1) + fib(n - 2);
}

int main() {
    return fib(7);
}
