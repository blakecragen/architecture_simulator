; === Fibonacci ===
; Compute Fibonacci numbers: F(0)=0, F(1)=1, F(n)=F(n-1)+F(n-2)
; Computes F(10) = 55
;
; Expected: x3=55 (F(10)), x1=34, x2=55
; Models: single_cycle, multicycle, pipeline
; Best viewed with: Any

ADDI x1, x0, 0         ; x1 = F(n-2) = 0
ADDI x2, x0, 1         ; x2 = F(n-1) = 1
ADDI x4, x0, 9         ; x4 = N = 9 (loop 9 times to compute F(10))
ADDI x5, x0, 0         ; x5 = loop counter

fib_loop:
BEQ  x5, x4, fib_done  ; if counter == N, done
ADD  x3, x1, x2        ; x3 = F(n) = F(n-2) + F(n-1)
ADD  x1, x0, x2        ; x1 = F(n-1) (shift window)
ADD  x2, x0, x3        ; x2 = F(n)   (shift window)
ADDI x5, x5, 1         ; counter++
JAL  x0, fib_loop      ; loop back

fib_done:
; x3 = F(10) = 55
; Sequence: 0,1,1,2,3,5,8,13,21,34,55
NOP
