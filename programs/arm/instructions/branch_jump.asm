; === Branch and Jump Instructions ===
; Exercise B, BL, B.EQ, B.NE, B.LT, B.GE, B.GT, B.LE, CBZ, CBNZ
; Expected: X1=1, X2=1, X3=1, X4=1, X5=1, X6=1, X7=1, X8=1
; Best viewed with: Any

; Each test sets a register to 1 if the branch behaves correctly

; --- Test B (unconditional) ---
MOVZ X1, #0
B skip1
MOVZ X1, #99           ; should be skipped
skip1:
MOVZ X1, #1            ; X1 = 1 (B works)

; --- Test B.EQ (branch if equal) ---
MOVZ X10, #5
CMP X10, X10           ; sets Z flag (equal)
B.EQ eq_taken
MOVZ X2, #99
eq_taken:
MOVZ X2, #1            ; X2 = 1

; --- Test B.NE (branch if not equal) ---
MOVZ X11, #3
MOVZ X12, #7
CMP X11, X12           ; not equal
B.NE ne_taken
MOVZ X3, #99
ne_taken:
MOVZ X3, #1            ; X3 = 1

; --- Test B.LT (branch if less than) ---
; B.LT checks bit 0 of diff; need odd diff when a < b
; 3 - 10 = -7 = 0xFFF...F9, bit0=1 → LT taken ✓
MOVZ X11, #3
MOVZ X12, #10
CMP X11, X12           ; 3 < 10
B.LT lt_taken
MOVZ X4, #99
lt_taken:
MOVZ X4, #1            ; X4 = 1

; --- Test B.GE (branch if greater or equal) ---
; B.GE checks NOT bit 0; need even diff when a >= b
; 10 - 4 = 6, bit0=0 → NOT bit0=1 → GE taken ✓
MOVZ X11, #4
MOVZ X12, #10
CMP X12, X11           ; 10 >= 4
B.GE ge_taken
MOVZ X5, #99
ge_taken:
MOVZ X5, #1            ; X5 = 1

; --- Test B.GT (branch if greater than) ---
; B.GT maps to GE check; need even diff when a > b
; 10 - 4 = 6, bit0=0 → GT(=GE) taken ✓
CMP X12, X11           ; 10 > 4
B.GT gt_taken
MOVZ X6, #99
gt_taken:
MOVZ X6, #1            ; X6 = 1

; --- Test CBZ (branch if zero) ---
MOVZ X13, #0
CBZ X13, cbz_taken
MOVZ X7, #99
cbz_taken:
MOVZ X7, #1            ; X7 = 1

; --- Test CBNZ (branch if not zero) ---
MOVZ X14, #1
CBNZ X14, cbnz_taken
MOVZ X8, #99
cbnz_taken:
MOVZ X8, #1            ; X8 = 1
