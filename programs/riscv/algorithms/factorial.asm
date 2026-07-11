; === Factorial ===
; Compute factorial(7) = 5040
; Uses iterative multiplication via repeated addition
;
; Since RV32I has no MUL instruction, we implement multiply
; as repeated addition in an inner loop.
;
; Expected: x1=5040 (7!)
; Best viewed with: Any

ADDI x1, x0, 1         ; x1 = result = 1
ADDI x2, x0, 7         ; x2 = N = 7 (compute 7!)

fact_loop:
ADDI x3, x0, 1         ; x3 = 1
BEQ  x2, x3, fact_done ; if N == 1, done

; --- Multiply x1 by x2 via repeated addition ---
; x4 = x1 * x2 (result = result * current_n)
ADDI x4, x0, 0         ; x4 = 0 (product accumulator)
ADDI x5, x0, 0         ; x5 = 0 (add counter)

mul_loop:
BEQ  x5, x2, mul_done  ; if counter == x2, multiplication done
ADD  x4, x4, x1        ; x4 += x1
ADDI x5, x5, 1         ; counter++
JAL  x0, mul_loop

mul_done:
ADD  x1, x4, x0        ; x1 = product (move result)
ADDI x2, x2, -1        ; N--
JAL  x0, fact_loop

fact_done:
; x1 = 7! = 5040
NOP
