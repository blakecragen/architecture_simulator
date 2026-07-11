; === Arithmetic Instructions ===
; Exercise ADD, SUB, SUBS, and CMP
; Expected: X1=10, X2=3, X3=13, X4=7, X5=20, X6=15, X7=5, X8=0
; Best viewed with: Any

; Load initial values
MOVZ X1, #10           ; X1 = 10
MOVZ X2, #3            ; X2 = 3

; ADD register
ADD X3, X1, X2         ; X3 = 10 + 3 = 13

; SUB register
SUB X4, X1, X2         ; X4 = 10 - 3 = 7

; ADD immediate
ADD X5, X1, #10        ; X5 = 10 + 10 = 20

; SUB immediate
SUB X6, X5, #5         ; X6 = 20 - 5 = 15

; SUBS sets flags (register form only)
MOVZ X9, #5            ; X9 = 5
SUBS X7, X1, X9        ; X7 = 10 - 5 = 5, flags updated

; CMP (alias for SUBS XZR, ...)
CMP X1, X2             ; compare X1 and X2, flags updated

; SUB to zero
SUB X8, X1, X1         ; X8 = 10 - 10 = 0
