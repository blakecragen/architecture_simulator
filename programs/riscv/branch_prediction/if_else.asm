; === If-Else (Branch Prediction) ===
; Forward branches with a mix of taken and not-taken paths
; Tests predictor on forward (usually not-taken) branches
;
; Expected: x10=1, x11=2, x12=3
; Best viewed with: Pipeline

; --- Test 1: value > 0, take the "positive" path ---
ADDI x1, x0, 5         ; x1 = 5

; if (x1 < 0) goto negative1
BLT  x1, x0, negative1 ; not taken (5 >= 0)
ADDI x10, x0, 1        ; x10 = 1 (positive path)
JAL  x0, endif1
negative1:
ADDI x10, x0, -1       ; not executed
endif1:

; --- Test 2: value < 0, take the "negative" path ---
ADDI x2, x0, -3        ; x2 = -3

; if (x2 >= 0) goto positive2
BGE  x2, x0, positive2 ; not taken (-3 < 0)
ADDI x11, x0, 2        ; x11 = 2 (negative path)
JAL  x0, endif2
positive2:
ADDI x11, x0, -2       ; not executed
endif2:

; --- Test 3: equality check ---
ADDI x3, x0, 7         ; x3 = 7
ADDI x4, x0, 7         ; x4 = 7

; if (x3 != x4) goto not_equal
BNE  x3, x4, not_equal ; not taken (7 == 7)
ADDI x12, x0, 3        ; x12 = 3 (equal path)
JAL  x0, endif3
not_equal:
ADDI x12, x0, -3       ; not executed
endif3:
NOP
