; === GCD (Greatest Common Divisor) ===
; Compute GCD using Euclidean algorithm (subtraction-based)
; GCD(48, 18) = 6
;
; Algorithm: while a != b: if a > b then a = a - b else b = b - a
;
; Expected: x1=6 (GCD result), x2=6
; Best viewed with: Any

ADDI x1, x0, 48        ; x1 = a = 48
ADDI x2, x0, 18        ; x2 = b = 18

gcd_loop:
BEQ  x1, x2, gcd_done  ; if a == b, GCD found

BLT  x1, x2, b_greater ; if a < b, subtract from b

; a > b: a = a - b
SUB  x1, x1, x2        ; a = a - b
JAL  x0, gcd_loop

b_greater:
; b > a: b = b - a
SUB  x2, x2, x1        ; b = b - a
JAL  x0, gcd_loop

gcd_done:
; x1 = x2 = GCD(48, 18) = 6
;
; Trace: (48,18)->(30,18)->(12,18)->(12,6)->(6,6) done
NOP
