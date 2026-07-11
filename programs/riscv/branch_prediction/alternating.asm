; === Alternating Branch Pattern ===
; Counter-based T/NT/T/NT pattern to stress bimodal/gshare predictors
; Even iterations: branch taken; Odd iterations: branch not taken
;
; This creates a pathological pattern for simple bimodal predictors
; since the branch alternates taken/not-taken every iteration.
; A gshare predictor with sufficient history should handle this better.
;
; Expected: x3=4 (count of taken branches), x4=4 (count of not-taken paths)
; Best viewed with: Pipeline

ADDI x1, x0, 8         ; x1 = 8 (loop counter, 8 iterations)
ADDI x2, x0, 1         ; x2 = 1 (used for AND mask)
ADDI x3, x0, 0         ; x3 = 0 (count of times branch was taken)
ADDI x4, x0, 0         ; x4 = 0 (count of times branch was not taken)

alt_loop:
AND  x5, x1, x2        ; x5 = x1 & 1 (check if counter is odd)
BNE  x5, x0, odd_path  ; if odd, branch taken -> odd_path

; --- Even path (branch not taken) ---
ADDI x4, x4, 1         ; x4++ (not-taken count)
JAL  x0, alt_continue

odd_path:
; --- Odd path (branch taken) ---
ADDI x3, x3, 1         ; x3++ (taken count)

alt_continue:
ADDI x1, x1, -1        ; x1--
BNE  x1, x0, alt_loop  ; loop back if x1 != 0

; --- Done: x3=4 (odd values: 7,5,3,1), x4=4 (even values: 8,6,4,2) ---
NOP
