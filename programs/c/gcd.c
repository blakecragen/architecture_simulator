// gcd: greatest common divisor of 48 and 36 via the Euclidean algorithm.
// Expected return value: 12.
// Targets: riscv, arm (single_cycle, multicycle, pipeline).
// Uses the '%' operator, which compiles to a software divide/modulo routine.
// The x86 backend supports only a SINGLE function (no CALL/RET stack), so
// this two-function program targets RISC-V and ARM.
int gcd(int a, int b) {
    while (b != 0) {
        int t = b;
        b = a % b;
        a = t;
    }
    return a;
}

int main() {
    return gcd(48, 36);
}
