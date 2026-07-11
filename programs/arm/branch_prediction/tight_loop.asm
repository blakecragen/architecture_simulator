; === Tight Loop (Branch Prediction) ===
; Backward branch taken 19/20 times; tests predictor learning
; Expected: X1=0 (counted down from 20), X2=20 (iteration count)
; Best viewed with: Pipeline

MOVZ X1, #20           ; X1 = counter = 20
MOVZ X2, #0            ; X2 = iteration count

loop:
ADD X2, X2, #1         ; X2++ (count iterations)
SUB X1, X1, #1         ; X1-- (decrement counter)
CBNZ X1, loop          ; branch back if X1 != 0 (taken 19 times, not-taken once)

; After loop: X1 = 0, X2 = 20
NOP
