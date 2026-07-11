// sum_to_n: sum of integers 1..10 via a for-loop.
// Expected return value: 55.
// Targets: riscv, arm, x86 (single_cycle, multicycle, pipeline).
int main() {
    int sum = 0;
    int i;
    for (i = 1; i <= 10; i = i + 1) {
        sum = sum + i;
    }
    return sum;
}
