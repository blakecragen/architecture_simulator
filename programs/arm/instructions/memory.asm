; === Memory Instructions ===
; Exercise LDR and STR with unsigned offset addressing
; Expected: X5=42, X6=99, X7=42
; Best viewed with: Any

; Set up base address for memory operations
MOVZ X1, #0            ; X1 = base address 0

; Store values to memory
MOVZ X2, #42           ; X2 = 42
STR X2, [X1, #0]       ; mem[0] = 42

MOVZ X3, #99           ; X3 = 99
STR X3, [X1, #8]       ; mem[8] = 99

MOVZ X4, #7            ; X4 = 7
STR X4, [X1, #16]      ; mem[16] = 7

; Load values back from memory
LDR X5, [X1, #0]       ; X5 = mem[0] = 42
LDR X6, [X1, #8]       ; X6 = mem[8] = 99
LDR X7, [X1, #0]       ; X7 = mem[0] = 42 (verify again)

; Store a computed value
ADD X8, X5, X6         ; X8 = 42 + 99 = 141
STR X8, [X1, #24]      ; mem[24] = 141

; Load it back
LDR X9, [X1, #24]      ; X9 = mem[24] = 141
