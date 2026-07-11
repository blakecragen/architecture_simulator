// bubble_sort: sort {5,2,4,1,3} ascending with bubble sort, then return
// (max - min) + median = (arr[4] - arr[0]) + arr[2] = (5 - 1) + 3 = 7.
// Expected return value: 7.
// Targets: riscv, arm, x86 (single_cycle, multicycle, pipeline).
// Exercises arrays, nested loops, comparisons and swap via a temp. (Long
// jumps relax to rel32 on x86. Multicycle needs ~4000 cycles — above the
// UI's manual 2000-cycle cap; use auto mode or single-cycle/pipeline.)
int main() {
    int arr[5];
    int i;
    int j;
    arr[0] = 5;
    arr[1] = 2;
    arr[2] = 4;
    arr[3] = 1;
    arr[4] = 3;
    for (i = 0; i < 4; i = i + 1) {
        for (j = 0; j < 4 - i; j = j + 1) {
            if (arr[j] > arr[j + 1]) {
                int t = arr[j];
                arr[j] = arr[j + 1];
                arr[j + 1] = t;
            }
        }
    }
    return (arr[4] - arr[0]) + arr[2];
}
