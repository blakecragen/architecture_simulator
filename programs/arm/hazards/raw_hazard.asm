; === RAW Hazard (Read-After-Write) ===
; Back-to-back RAW dependency requiring forwarding
; Expected: X1=10, X2=20, X3=30, X4=60
; Best viewed with: Pipeline

; X1 written, then immediately read by next instruction
MOVZ X1, #10           ; X1 = 10
ADD X2, X1, X1         ; X2 = X1 + X1 = 20 (RAW on X1)
ADD X3, X2, X1         ; X3 = X2 + X1 = 30 (RAW on X2)
ADD X4, X3, X3         ; X4 = X3 + X3 = 60 (RAW on X3)

; Chain continues — every instruction depends on the previous
SUB X5, X4, X1         ; X5 = X4 - X1 = 50 (RAW on X4)
ADD X6, X5, X2         ; X6 = X5 + X2 = 70 (RAW on X5)
