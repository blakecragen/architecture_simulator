; === Control Hazard ===
; Taken branch demonstrates pipeline flush of speculatively fetched instructions
; Expected: X1=1, X2=0 (X2 never set to 99)
; Best viewed with: Pipeline

; Unconditional branch skips over instructions
MOVZ X1, #1            ; X1 = 1
B skip_block            ; taken branch -> flush pipeline

; These instructions are fetched but must be flushed
MOVZ X2, #99           ; should NOT execute
MOVZ X3, #99           ; should NOT execute
MOVZ X4, #99           ; should NOT execute

skip_block:
; Conditional branch control hazard
MOVZ X5, #5
MOVZ X6, #5
CMP X5, X6             ; sets Z flag (equal)
B.EQ equal_path        ; taken branch -> flush

MOVZ X7, #99           ; should NOT execute
MOVZ X8, #99           ; should NOT execute

equal_path:
MOVZ X9, #1            ; X9 = 1 (confirms correct execution path)

; Not-taken branch (no flush needed)
MOVZ X10, #3
MOVZ X11, #7
CMP X10, X11           ; 3 != 7
B.EQ not_taken_path    ; NOT taken, no flush
MOVZ X12, #1           ; X12 = 1 (this DOES execute)
not_taken_path:
NOP
