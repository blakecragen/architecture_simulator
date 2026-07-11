; === Nested Loop (Branch Prediction) ===
; Outer loop 3 iterations, inner loop 5 iterations each
; Tests predictor with two branch sites at different frequencies
;
; Inner branch: taken 4/5 times per inner loop (total 12 taken, 3 not-taken)
; Outer branch: taken 2/3 times (total 2 taken, 1 not-taken)
;
; Expected: x1=0, x2=0, x3=15 (3 * 5 = 15 total inner iterations)
; Best viewed with: Pipeline

ADDI x3, x0, 0         ; x3 = 0 (total inner iteration count)
ADDI x1, x0, 3         ; x1 = 3 (outer counter)

outer:
ADDI x2, x0, 5         ; x2 = 5 (inner counter, reset each outer iteration)

inner:
ADDI x3, x3, 1         ; x3++ (count total inner iterations)
ADDI x2, x2, -1        ; x2--
BNE  x2, x0, inner     ; inner branch: taken 4/5 times

ADDI x1, x1, -1        ; x1-- (outer decrement)
BNE  x1, x0, outer     ; outer branch: taken 2/3 times

; --- Loops exited: x1=0, x2=0, x3=15 ---
NOP
