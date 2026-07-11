// array_fill: a constant-sized local array filled with squares, then summed.
//   Shows a symbolic/constant array size (int arr[LEN]) plus ++ and += — the
//   size folds to a compile-time constant so the frame is statically known.
// Expected return value: 506.  (sum of i*i for i = 0..11)
// Targets: riscv, arm, x86 (single_cycle, multicycle, pipeline).
int main() {
    const int LEN = 12;
    int arr[LEN];
    int i;
    int sum = 0;
    for (i = 0; i < LEN; i++) {
        arr[i] = i * i;
    }
    for (i = 0; i < LEN; i++) {
        sum += arr[i];
    }
    return sum;
}
