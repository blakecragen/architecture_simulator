; === Branch and Jump Instructions ===
; Exercise JMP, JE, JNE, JL, JGE, JLE, JG
; Expected: EAX=1, EBX=1, ECX=1, EDX=1, ESI=1, EDI=1
; Best viewed with: Any

; Each test sets a register to 1 if the branch behaves correctly

; --- Test JMP (unconditional) ---
MOV EAX, 0
JMP skip1
MOV EAX, 99            ; should be skipped
skip1:
MOV EAX, 1             ; EAX = 1

; --- Test JE (branch if equal) ---
MOV EBX, 5
CMP EBX, 5             ; equal
JE eq_taken
MOV EBX, 99
eq_taken:
MOV EBX, 1             ; EBX = 1

; --- Test JNE (branch if not equal) ---
MOV ECX, 3
CMP ECX, 7             ; not equal
JNE ne_taken
MOV ECX, 99
ne_taken:
MOV ECX, 1             ; ECX = 1

; --- Test JL (branch if less) ---
MOV EDX, 3
CMP EDX, 10            ; 3 < 10, diff=-7 (odd), bit0=1 -> JL taken
JL lt_taken
MOV EDX, 99
lt_taken:
MOV EDX, 1             ; EDX = 1

; --- Test JGE (branch if greater or equal) ---
MOV ESI, 10
CMP ESI, 4             ; 10 >= 4, diff=6 (even), bit0=0 -> JGE taken
JGE ge_taken
MOV ESI, 99
ge_taken:
MOV ESI, 1             ; ESI = 1

; --- Test JG (branch if greater) ---
MOV EDI, 10
CMP EDI, 5             ; 10 > 5
JG gt_taken
MOV EDI, 99
gt_taken:
MOV EDI, 1             ; EDI = 1
