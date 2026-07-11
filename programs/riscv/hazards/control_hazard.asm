; === Control Hazard ===
; Taken branch demonstrates pipeline flush
;
; When a branch is taken, instructions fetched after the branch
; (in the branch's shadow) must be flushed/squashed.
;
; Cycle analysis (5-stage pipeline):
;   Cycle 1: BEQ in IF
;   Cycle 2: BEQ in ID, ADDI x2 in IF (speculatively fetched)
;   Cycle 3: BEQ in EX (branch resolved, taken!), ADDI x2 in ID, ADDI x3 in IF
;            -> FLUSH: ADDI x2 and ADDI x3 are squashed
;   Cycle 4: Target instruction (ADDI x4) fetched
;
; Expected: x1=5, x2=0, x3=0, x4=1, x5=1
; Best viewed with: Pipeline

; --- Setup ---
ADDI x1, x0, 5         ; x1 = 5

; --- Taken branch: flush the instructions in the shadow ---
BEQ  x1, x1, branch_target  ; always taken (x1 == x1)
ADDI x2, x0, 99        ; FLUSHED: should never execute
ADDI x3, x0, 99        ; FLUSHED: should never execute

branch_target:
ADDI x4, x0, 1         ; x4 = 1 (proves we jumped here)

; --- Not-taken branch: no flush needed ---
BEQ  x1, x0, not_taken ; not taken (5 != 0)
ADDI x5, x0, 1         ; x5 = 1 (executes normally, branch not taken)
JAL  x0, done           ; skip not_taken target

not_taken:
ADDI x5, x0, 99        ; should not execute

done:
NOP
