; === Move Instructions ===
; Exercise MOVZ, MOV, and NOP
; Expected: X1=42, X2=1000, X3=0, X4=255, X5=42
; Best viewed with: Any

; MOVZ — move wide with zero
MOVZ X1, #42           ; X1 = 42
MOVZ X2, #1000         ; X2 = 1000
MOVZ X3, #0            ; X3 = 0
MOVZ X4, #255          ; X4 = 255

; MOV — alias for MOVZ
MOV X5, #42            ; X5 = 42
MOV X6, #100           ; X6 = 100

; NOP — no operation (pipeline filler)
NOP
NOP
NOP

; More MOV instructions
MOV X7, #1             ; X7 = 1
MOV X8, #0xFFFF        ; X8 = 65535
