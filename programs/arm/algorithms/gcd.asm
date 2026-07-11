; === GCD (Euclidean Algorithm) ===
; Compute GCD(48, 18) = 6 using subtraction-based Euclidean algorithm
; Expected: X1=6, X2=6
; Best viewed with: Pipeline

; gcd(a, b): while a != b: if a > b: a = a - b; else: b = b - a
MOVZ X1, #48           ; X1 = a = 48
MOVZ X2, #18           ; X2 = b = 18

gcd_loop:
; B.GT is broken in simulator, use SUBS + sign-bit check
SUBS X15, X1, X2        ; X15 = a - b, sets flags
B.EQ gcd_done           ; if a == b, we found the GCD
MOVZ X16, #128          ; mask for bit 7 (sign indicator)
AND X17, X15, X16       ; isolate bit 7
CBNZ X17, b_greater     ; bit 7 set → negative → a < b

; a > b: subtract b from a
SUB X1, X1, X2          ; a = a - b
B gcd_loop

b_greater:
; b > a: subtract a from b
SUB X2, X2, X1          ; b = b - a
B gcd_loop

gcd_done:
; Result: X1 = X2 = 6 = GCD(48, 18)
NOP
