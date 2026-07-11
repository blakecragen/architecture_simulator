; === Load-Use Hazard ===
; Memory load followed by immediate use of loaded value
; Causes pipeline stall + forwarding
; Expected: EAX=42, EBX=42, ECX=84, EDX=42
; Best viewed with: Pipeline

; --- Store a value to memory ---
MOV EAX, 42            ; EAX = 42
MOV EBX, 0             ; EBX = 0 (base address)
MOV [EBX], EAX         ; mem[0] = 42

; --- Load from memory, then immediately use (load-use hazard) ---
MOV EDX, [EBX]         ; EDX = mem[0] = 42 (LOAD)
MOV ECX, EDX           ; ECX = 42 (USE: stall + forward from load)
ADD ECX, EDX           ; ECX = 42 + 42 = 84 (USE: forward from load)

; --- Another load-use pair ---
MOV [EBX+4], EAX       ; mem[4] = 42
MOV EBX, [EBX+4]       ; EBX = 42 (LOAD)
ADD EAX, EBX           ; EAX = 42 + 42 = 84 (USE: stall + forward)

; --- Restore expected ---
MOV EAX, 42            ; EAX = 42
MOV EBX, 42            ; EBX = 42
