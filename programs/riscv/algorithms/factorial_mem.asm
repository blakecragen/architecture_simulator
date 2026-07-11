; === Factorial (Memory Table) ===
; Store factorial values 0!..7! in memory
; mem[i*4] = i!, base address = 0
;
; Expected: mem[0]=1, mem[4]=1, mem[8]=2, mem[12]=6, mem[16]=24, mem[20]=120, mem[24]=720, mem[28]=5040
; Expected: x1=5040
; Cycles: 1500
; Best viewed with: Any

; 0! = 1
ADDI x1, x0, 1         ; x1 = current factorial = 1
SW   x1, 0(x0)         ; mem[0] = 0! = 1

; 1! = 1
SW   x1, 4(x0)         ; mem[4] = 1! = 1

; Compute 2!..7! using repeated addition for multiply
ADDI x6, x0, 2         ; x6 = current N (start at 2)
ADDI x7, x0, 8         ; x7 = current mem offset (start at 8)
ADDI x8, x0, 8         ; x8 = end N (loop while N < 8)

fact_loop:
BEQ  x6, x8, fact_done ; if N == 8, done

; Multiply x1 by x6: x4 = x1 * x6
ADDI x4, x0, 0         ; x4 = product = 0
ADDI x5, x0, 0         ; x5 = counter = 0

mul_loop:
BEQ  x5, x6, mul_done  ; if counter == N, done
ADD  x4, x4, x1        ; product += x1
ADDI x5, x5, 1         ; counter++
JAL  x0, mul_loop

mul_done:
ADD  x1, x4, x0        ; x1 = product
SW   x1, 0(x7)         ; mem[offset] = N!
ADDI x6, x6, 1         ; N++
ADDI x7, x7, 4         ; offset += 4
JAL  x0, fact_loop

fact_done:
; x1 = 7! = 5040
NOP
