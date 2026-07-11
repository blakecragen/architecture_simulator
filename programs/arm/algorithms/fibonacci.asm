; === Fibonacci ===
; Compute the 10th Fibonacci number iteratively
; Expected: X3=55 (fib(10) = 55), X1=34, X2=55
; Models: single_cycle, multicycle, ooo
; Best viewed with: Pipeline

; F(0)=0, F(1)=1, F(2)=1, ..., F(10)=55
MOVZ X1, #0            ; X1 = F(n-2) = 0
MOVZ X2, #1            ; X2 = F(n-1) = 1
MOVZ X4, #9            ; X4 = iteration count (9 iterations: F2..F10)

fib_loop:
ADD X3, X1, X2         ; X3 = F(n) = F(n-2) + F(n-1)
ADD X1, XZR, X2        ; X1 = X2 (shift: F(n-2) <- F(n-1))
ADD X2, XZR, X3        ; X2 = X3 (shift: F(n-1) <- F(n))
SUB X4, X4, #1         ; X4-- (decrement counter)
CBNZ X4, fib_loop      ; loop until X4 == 0

; Result: X3 = 55 (10th Fibonacci number)
NOP
