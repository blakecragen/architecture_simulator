; === Alternating Branches (Branch Prediction) ===
; T/NT/T/NT pattern to stress branch predictors
; Expected: X10=4 (counts taken branches)
; Best viewed with: Pipeline

MOVZ X1, #8            ; X1 = loop counter (8 iterations)
MOVZ X10, #0           ; X10 = taken-branch counter
MOVZ X2, #0            ; X2 = iteration index

alt_loop:
; Check if iteration is odd or even using AND with 1
; We toggle by checking the low bit of X2
MOVZ X3, #1
AND X4, X2, X3         ; X4 = X2 & 1 (0 if even, 1 if odd)

CBZ X4, skip_inc       ; if even iteration -> skip (NOT taken on odd, TAKEN on even)
ADD X10, X10, #1       ; X10++ only on odd iterations
skip_inc:

ADD X2, X2, #1         ; X2++ (next iteration)
SUB X1, X1, #1         ; X1-- (decrement counter)
CBNZ X1, alt_loop      ; loop back if counter != 0

; After: X10 = 4 (incremented on iterations 1,3,5,7)
NOP
