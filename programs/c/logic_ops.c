// logic_ops: short-circuit && / ||, ! and if/else chains build a bitmask-style
// score: +1 if (a<b && b<c), +2 if (a==4 || c==9), +4 if !(b==c), all true for
// a=3, b=5, c=9 -> 1+2+4 = 7.
// Expected return value: 7.
// Targets: riscv, arm, x86 (single_cycle, multicycle, pipeline).
// Exercises logical operators, negation and if/else without loops.
int main() {
    int a = 3;
    int b = 5;
    int c = 9;
    int score = 0;
    if (a < b && b < c) {
        score = score + 1;
    }
    if (a == 4 || c == 9) {
        score = score + 2;
    }
    if (!(b == c)) {
        score = score + 4;
    } else {
        score = 100;
    }
    return score;
}
