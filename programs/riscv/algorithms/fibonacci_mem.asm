; === Fibonacci (Memory Table) ===
; Store Fibonacci sequence F(0)..F(10) in memory as a DP table
; mem[i*4] = F(i), base address = 0
;
; Expected: mem[0]=0, mem[4]=1, mem[8]=1, mem[12]=2, mem[16]=3, mem[20]=5, mem[24]=8, mem[28]=13, mem[32]=21, mem[36]=34, mem[40]=55
; Expected: x3=55
; Cycles: 200
; Best viewed with: Any

; F(0) = 0
ADDI x1, x0, 0         ; x1 = F(n-2) = 0
SW   x1, 0(x0)         ; mem[0] = 0

; F(1) = 1
ADDI x2, x0, 1         ; x2 = F(n-1) = 1
SW   x2, 4(x0)         ; mem[4] = 1

; Loop to compute F(2)..F(10)
ADDI x4, x0, 9         ; x4 = iterations remaining
ADDI x5, x0, 8         ; x5 = current byte offset (starts at 8 for F(2))

fib_loop:
BEQ  x4, x0, fib_done  ; if counter == 0, done
ADD  x3, x1, x2        ; x3 = F(n) = F(n-2) + F(n-1)
SW   x3, 0(x5)         ; mem[offset] = F(n)
ADD  x1, x0, x2        ; x1 = F(n-1) (shift window)
ADD  x2, x0, x3        ; x2 = F(n)   (shift window)
ADDI x5, x5, 4         ; offset += 4
ADDI x4, x4, -1        ; counter--
JAL  x0, fib_loop

fib_done:
; x3 = F(10) = 55
NOP
