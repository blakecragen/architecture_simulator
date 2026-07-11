; === Memory Instructions ===
; Exercise MOV in all forms (reg/imm, reg/reg, memory load, memory store), PUSH, POP
; Expected: EAX=42, EBX=42, ECX=99, EDX=99
; Best viewed with: Any

; --- MOV reg, imm ---
MOV EAX, 42            ; EAX = 42

; --- MOV reg, reg ---
MOV EBX, EAX           ; EBX = 42

; --- Set up base pointer for memory ---
MOV ECX, 0             ; ECX = 0 (base address)

; --- MOV [reg], reg (store to memory) ---
MOV [ECX], EAX         ; mem[0] = 42

; --- MOV reg, [reg] (load from memory) ---
MOV EDX, [ECX]         ; EDX = mem[0] = 42

; --- Store with displacement ---
MOV EAX, 99            ; EAX = 99
MOV [ECX+4], EAX       ; mem[4] = 99

; --- Load with displacement ---
MOV EBX, [ECX+4]       ; EBX = mem[4] = 99

; --- PUSH / POP ---
MOV ESP, 64            ; set up stack pointer
PUSH EAX               ; push 99 onto stack
MOV EAX, 0             ; clear EAX
POP EAX                ; EAX = 99 (popped)

; --- Reload expected values ---
MOV EAX, 42            ; EAX = 42
MOV EBX, 42            ; EBX = 42
MOV ECX, 99            ; ECX = 99
MOV EDX, 99            ; EDX = 99
