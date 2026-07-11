// fib_iter: the 10th Fibonacci number (0,1,1,2,3,5,8,13,21,34,55) iteratively.
// Expected return value: 55.
// Targets: riscv, arm, x86 (single_cycle, multicycle, pipeline).
// Uses only + and comparisons, so it fits every backend (including x86's rel8
// jump reach).
int main() {
    int a = 0;
    int b = 1;
    int n = 10;
    int i;
    for (i = 1; i < n; i = i + 1) {
        int t = a + b;
        a = b;
        b = t;
    }
    return b;
}
