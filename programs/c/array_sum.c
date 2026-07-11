// array_sum: fill a 5-element array with 1..5, then sum it in a second loop.
// Expected return value: 15.
// Targets: riscv, arm, x86 (single_cycle, multicycle, pipeline).
// Exercises local arrays: indexed stores in one loop, indexed loads in
// another. Only + and comparisons, so it fits every backend.
int main() {
    int arr[5];
    int i;
    int sum = 0;
    for (i = 0; i < 5; i = i + 1) {
        arr[i] = i + 1;
    }
    for (i = 0; i < 5; i = i + 1) {
        sum = sum + arr[i];
    }
    return sum;
}
