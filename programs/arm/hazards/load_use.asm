; === Load-Use Hazard ===
; LDR followed by immediate use causes a pipeline stall + forward
; Expected: X5=42, X6=84, X7=99, X8=141
; Best viewed with: Pipeline

; Set up base address and store values
MOVZ X1, #0            ; X1 = base address 0
MOVZ X2, #42           ; X2 = 42
STR X2, [X1, #0]       ; mem[0] = 42
MOVZ X3, #99           ; X3 = 99
STR X3, [X1, #8]       ; mem[8] = 99

; Load-use hazard: LDR result used in very next instruction
LDR X5, [X1, #0]       ; X5 = mem[0] = 42 (load)
ADD X6, X5, X5         ; X6 = 42 + 42 = 84 (USE: must stall 1 cycle)

; Another load-use hazard
LDR X7, [X1, #8]       ; X7 = mem[8] = 99 (load)
ADD X8, X7, X5         ; X8 = 99 + 42 = 141 (USE: must stall 1 cycle)
