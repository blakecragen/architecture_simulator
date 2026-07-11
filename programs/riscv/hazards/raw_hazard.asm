; === RAW (Read After Write) Hazard ===
; Back-to-back RAW dependency demonstrating forwarding
; The ADD reads x1 in its EX stage while ADDI writes x1 in its WB stage
;
; Cycle analysis (5-stage pipeline):
;   Cycle 1: ADDI x1 in IF
;   Cycle 2: ADDI x1 in ID, ADD x2 in IF
;   Cycle 3: ADDI x1 in EX, ADD x2 in ID  <-- RAW hazard: ADD needs x1
;   Cycle 4: ADDI x1 in MEM, ADD x2 in EX  <-- forwarding from EX/MEM
;   Cycle 5: ADDI x1 in WB, ADD x2 in MEM
;
; Expected: x1=10, x2=10, x3=20, x4=30, x5=130
; Best viewed with: Pipeline

; --- RAW hazard: x1 written then immediately read ---
ADDI x1, x0, 10        ; x1 = 10
ADD  x2, x1, x0        ; x2 = x1 + 0 = 10 (RAW on x1, forward from EX/MEM)

; --- Chained RAW: each instruction depends on the previous ---
ADD  x3, x1, x2        ; x3 = 10 + 10 = 20 (RAW on x2)
ADD  x4, x2, x3        ; x4 = 10 + 20 = 30 (RAW on x3)

; --- Longer chain ---
ADDI x5, x0, 100       ; x5 = 100
ADD  x5, x5, x4        ; x5 = 100 + 30 = 130 (RAW on x5 and x4)
