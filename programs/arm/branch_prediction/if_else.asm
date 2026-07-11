; === If-Else (Branch Prediction) ===
; Forward branches with a mix of taken/not-taken
; Expected: X10=1, X11=1, X12=1
; Best viewed with: Pipeline

; --- Test 1: condition true -> branch taken (skip else) ---
MOVZ X1, #10
MOVZ X2, #10
CMP X1, X2             ; equal
B.NE else1             ; NOT taken (they are equal)
MOVZ X10, #1           ; X10 = 1 (if-path executed)
B end1
else1:
MOVZ X10, #0           ; would set X10 = 0
end1:

; --- Test 2: condition false -> branch taken (go to else) ---
MOVZ X3, #5
MOVZ X4, #20
CMP X3, X4             ; 5 < 20, not equal
B.NE else2             ; TAKEN (they are not equal)
MOVZ X11, #0           ; skipped
B end2
else2:
MOVZ X11, #1           ; X11 = 1 (else-path executed)
end2:

; --- Test 3: greater-than check ---
MOVZ X5, #30
MOVZ X6, #15
; B.LE is broken in simulator, use SUBS + sign-bit check
SUBS X15, X5, X6        ; X15 = 30 - 15 = 15, sets flags
B.EQ else3               ; equal → go to else (not taken here)
MOVZ X16, #128           ; mask for bit 7 (sign indicator)
AND X17, X15, X16        ; isolate bit 7
CBNZ X17, else3          ; bit 7 set → negative → X5 < X6 → else
; fall through: X5 > X6 → if-path
MOVZ X12, #1           ; X12 = 1 (if-path executed)
B end3
else3:
MOVZ X12, #0
end3:
NOP
