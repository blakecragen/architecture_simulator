// factorial_iter: 5! computed iteratively with the '*' operator.
// Expected return value: 120.
// Targets: riscv, arm, x86 (single_cycle, multicycle, pipeline).
// NOTE: uses multiply. On RISC-V/ARM this compiles to a software multiply
// routine (RV32I / the ARM subset have no hardware MUL); the x86 backend
// emits an inline multiply loop (long jumps relax to rel32 automatically).
int main() {
    int n = 5;
    int result = 1;
    int i;
    for (i = 1; i <= n; i = i + 1) {
        result = result * i;
    }
    return result;
}
