; === Factorial ===
; Compute 7! = 5040 iteratively
; Expected: X1=5040, X2=0
; Models: single_cycle, multicycle, ooo
; Best viewed with: Pipeline

; factorial(7) = 7 * 6 * 5 * 4 * 3 * 2 * 1 = 5040
; Since ARM MUL is not in our ISA subset, we use repeated addition

MOVZ X1, #1            ; X1 = result (accumulator) = 1
MOVZ X2, #7            ; X2 = current multiplier = 7

fact_loop:
; Multiply X1 by X2 using repeated addition
; X3 = X1 * X2
MOVZ X3, #0            ; X3 = product accumulator
ADD X4, XZR, X2        ; X4 = copy of multiplier (loop counter)

mul_loop:
ADD X3, X3, X1         ; X3 += X1
SUB X4, X4, #1         ; X4--
CBNZ X4, mul_loop      ; repeat X2 times

; X3 now holds X1 * X2
ADD X1, XZR, X3        ; X1 = product
SUB X2, X2, #1         ; X2-- (next multiplier)
CBNZ X2, fact_loop     ; continue until multiplier is 0

; Result: X1 = 5040 = 7!
NOP
