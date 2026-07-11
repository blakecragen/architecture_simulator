; === Factorial (Memory Table) ===
; Store factorial values 0!..7! in memory (8-byte aligned for ARM)
; mem[i*8] = i!
;
; Expected: mem[0]=1, mem[8]=1, mem[16]=2, mem[24]=6, mem[32]=24, mem[40]=120, mem[48]=720, mem[56]=5040
; Expected: X1=5040
; Cycles: 1500
; Best viewed with: Any

MOVZ X20, #0           ; X20 = base address

; 0! = 1
MOVZ X1, #1            ; X1 = current factorial = 1
STR X1, [X20, #0]      ; mem[0] = 0! = 1

; 1! = 1
STR X1, [X20, #8]      ; mem[8] = 1! = 1

; Compute 2!..7!
MOVZ X6, #2            ; X6 = current N
MOVZ X7, #16           ; X7 = current mem offset
MOVZ X8, #8            ; X8 = end N (loop while N < 8)

fact_loop:
; Compare N with end: if N == 8, done
SUBS X15, X6, X8       ; compare N - 8
B.EQ fact_done

; Multiply X1 by X6: X4 = X1 * X6
MOVZ X4, #0            ; X4 = product
ADD X5, XZR, X6        ; X5 = counter = N

mul_loop:
ADD X4, X4, X1         ; product += X1
SUB X5, X5, #1         ; counter--
CBNZ X5, mul_loop      ; loop N times

ADD X1, XZR, X4        ; X1 = product
ADD X9, X20, X7        ; X9 = base + offset
STR X1, [X9, #0]       ; mem[offset] = N!
ADD X6, X6, #1         ; N++
ADD X7, X7, #8         ; offset += 8
B fact_loop

fact_done:
; X1 = 7! = 5040
NOP
