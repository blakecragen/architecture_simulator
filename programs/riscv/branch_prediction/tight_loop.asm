; === Tight Loop (Branch Prediction) ===
; Backward branch taken 19/20 times (counter from 20 down to 1)
; Tests predictor's ability to learn a strongly-taken backward branch
;
; The branch is taken 19 times and not-taken once (on exit).
; A simple bimodal predictor should quickly learn to predict taken.
;
; Expected: x1=0, x2=210 (sum of 20+19+...+1 = 210)
; Best viewed with: Pipeline

ADDI x1, x0, 20        ; x1 = 20 (loop counter)
ADDI x2, x0, 0         ; x2 = 0  (accumulator)

loop:
ADD  x2, x2, x1        ; x2 += x1
ADDI x1, x1, -1        ; x1--
BNE  x1, x0, loop      ; if x1 != 0, branch back (taken 19 times, not-taken once)

; --- Loop exited, x1=0, x2=210 ---
NOP
