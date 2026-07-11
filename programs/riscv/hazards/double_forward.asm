; === Double Forwarding ===
; rs1 forwarded from EX/MEM, rs2 forwarded from MEM/WB simultaneously
;
; Cycle analysis (5-stage pipeline):
;   Cycle 1: ADDI x1 in IF
;   Cycle 2: ADDI x1 in ID, ADDI x2 in IF
;   Cycle 3: ADDI x1 in EX, ADDI x2 in ID, ADD x3 in IF
;   Cycle 4: ADDI x1 in MEM, ADDI x2 in EX, ADD x3 in ID
;   Cycle 5: ADDI x1 in WB, ADDI x2 in MEM, ADD x3 in EX
;            ADD x3 reads: rs1=x2 from EX/MEM, rs1=x1 from MEM/WB
;            Both forwarding paths active simultaneously!
;
; Expected: x1=10, x2=20, x3=30, x4=50, x5=80
; Best viewed with: Pipeline

; --- Setup: two values written back-to-back ---
ADDI x1, x0, 10        ; x1 = 10 (will be in MEM/WB when x3 is in EX)
ADDI x2, x0, 20        ; x2 = 20 (will be in EX/MEM when x3 is in EX)

; --- Double forward: rs1 from EX/MEM (x2), rs2 from MEM/WB (x1) ---
ADD  x3, x2, x1        ; x3 = 20 + 10 = 30

; --- Another double forward scenario ---
ADDI x4, x0, 50        ; x4 = 50 (will be in MEM/WB)
ADD  x5, x3, x4        ; x5 = 30 + 50 = 80 (x3 from MEM/WB)

; --- Verify with no-hazard read ---
ADD  x6, x5, x0        ; x6 = 80 (x5 from EX/MEM)
NOP
NOP
ADD  x7, x5, x6        ; x7 = 80 + 80 = 160 (no hazard, values settled)
