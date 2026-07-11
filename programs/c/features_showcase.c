// features_showcase: the Core-C expansion in one program — a const-sized array
//   with an initializer, a file-scope global, ternary ?:, bitwise & | ~,
//   compound assignment, ++, and break/continue. (No function calls, so it
//   runs on every backend including x86.)
// Expected return value: 248.
// Targets: riscv, arm, x86 (single_cycle, multicycle, pipeline).
const int N = 6;
int acc = 0;                       // file-scope global accumulator

int main() {
    int a[N] = {1, 2, 3, 4, 5, 6};
    int i = 0;
    while (i < N) {
        int v = a[i];
        if ((v & 1) == 0) {        // even
            acc += v;
        } else {                   // odd -> count double
            acc += v * 2;
        }
        i++;
    }
    int flags = 0xF0 | 0x0F;       // 255
    flags &= ~0x0F;                // clear low nibble -> 240
    int pick = acc >= 30 ? flags : -1;   // ternary picks 240
    for (i = 0; i < N; i++) {
        if (i == 2) continue;
        if (i == 5) break;
        pick += i;                 // adds 0 + 1 + 3 + 4 = 8
    }
    return pick;                   // 240 + 8 = 248
}
