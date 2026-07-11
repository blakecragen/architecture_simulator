; === Nested Loop (Branch Prediction) ===
; Outer loop 3 iterations, inner loop 5 iterations each
; Expected: X1=0, X2=0, X3=15 (3*5 total inner iterations)
; Best viewed with: Pipeline

MOVZ X1, #3            ; X1 = outer counter
MOVZ X3, #0            ; X3 = total iteration count

outer:
MOVZ X2, #5            ; X2 = inner counter (reset each outer iteration)

inner:
ADD X3, X3, #1         ; X3++ (total iterations)
SUB X2, X2, #1         ; X2-- (inner counter)
CBNZ X2, inner         ; inner loop back (taken 4 times per outer)

SUB X1, X1, #1         ; X1-- (outer counter)
CBNZ X1, outer         ; outer loop back (taken 2 times)

; After: X1=0, X2=0, X3=15
NOP
