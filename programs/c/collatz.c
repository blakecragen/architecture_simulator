// collatz: count the Collatz steps from 7 down to 1
// (7 -> 22 -> 11 -> 34 -> 17 -> 52 -> 26 -> 13 -> 40 -> 20 -> 10 -> 5 -> 16
//  -> 8 -> 4 -> 2 -> 1: 16 steps).
// Expected return value: 16.
// Targets: riscv (single_cycle, multicycle, pipeline).
// Halving uses the '>>' shift operator and the even-test compares
// (n >> 1) + (n >> 1) against n — no divide, so the loop stays fast. 3n+1 is
// computed with adds. Shift operators are only supported by the RISC-V
// backend (SRLI/SLLI); the ARM and x86 backends reject them, so this program
// targets RISC-V only.
int main() {
    int n = 7;
    int steps = 0;
    while (n != 1) {
        int half = n >> 1;
        if (half + half == n) {
            n = half;
        } else {
            n = n + n + n + 1;
        }
        steps = steps + 1;
    }
    return steps;
}
