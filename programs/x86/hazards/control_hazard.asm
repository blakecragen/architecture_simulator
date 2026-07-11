; === Control Hazard ===
; Taken branch causes pipeline flush of speculatively fetched instructions
; Expected: EAX=1, EBX=10, ECX=0
; Best viewed with: Pipeline

; --- Unconditional branch causes flush ---
MOV EAX, 0             ; EAX = 0
JMP skip_bad           ; taken branch -> flush next fetched instr
MOV EAX, 99            ; FLUSHED: should never execute
MOV EAX, 88            ; FLUSHED: should never execute
skip_bad:
MOV EAX, 1             ; EAX = 1 (reached via branch)

; --- Conditional branch taken causes flush ---
MOV EBX, 10            ; EBX = 10
CMP EBX, 10            ; sets flags (equal)
JE taken_path          ; taken -> flush
MOV EBX, 0             ; FLUSHED
taken_path:
NOP                    ; landed here

; --- Conditional branch NOT taken: no flush ---
MOV ECX, 0             ; ECX = 0
CMP ECX, 5             ; 0 != 5
JE not_taken           ; not taken -> no flush
NOP                    ; this executes normally
not_taken:
NOP
