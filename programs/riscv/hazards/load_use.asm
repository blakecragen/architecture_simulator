; === Load-Use Hazard ===
; LW followed by immediate use causes a 1-cycle stall + forward
;
; Cycle analysis (5-stage pipeline):
;   Cycle 1: SW in IF
;   ...
;   Cycle N: LW x2 in IF
;   Cycle N+1: LW x2 in ID, ADD x3 in IF
;   Cycle N+2: LW x2 in EX, ADD x3 in ID  <-- hazard detected, stall inserted
;   Cycle N+3: LW x2 in MEM, ADD x3 stalled (bubble in EX)
;   Cycle N+4: LW x2 in WB, ADD x3 in EX   <-- forward from MEM/WB
;
; The load-use hazard cannot be fully resolved by forwarding alone
; because the data is not available until the MEM stage completes.
;
; Expected: x1=42, x2=42, x3=84, x4=42, x5=126
; Best viewed with: Pipeline

; --- Store a value to memory ---
ADDI x1, x0, 42        ; x1 = 42
SW   x1, 0(x0)         ; mem[0] = 42

; --- Load-use hazard: LW then immediate use ---
LW   x2, 0(x0)         ; x2 = mem[0] = 42
ADD  x3, x2, x1        ; x3 = 42 + 42 = 84 (load-use: stall + forward)

; --- Another load-use ---
LW   x4, 0(x0)         ; x4 = mem[0] = 42
ADD  x5, x4, x3        ; x5 = 42 + 84 = 126 (load-use: stall + forward)
