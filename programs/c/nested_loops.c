// nested_loops: triangle count — for i in 1..5, add i copies of i (25+... no:
// sum over i of (i added i times) = 1*1 + 2*2 + 3*3 + 4*4 + 5*5 = 55, computed
// with repeated addition only (no multiply).
// Expected return value: 55.
// Targets: riscv, arm, x86 (single_cycle, multicycle, pipeline).
// Exercises nested for-loops with only + and comparisons. (The outer loop's
// back-jump exceeds rel8 reach on x86; the assembler's branch relaxation
// widens it to JMP/Jcc rel32 automatically.)
int main() {
    int total = 0;
    int i;
    int j;
    for (i = 1; i <= 5; i = i + 1) {
        for (j = 0; j < i; j = j + 1) {
            total = total + i;
        }
    }
    return total;
}
