; === Fibonacci (Memory Table) ===
; Store Fibonacci sequence F(0)..F(10) in memory
; mem[i*8] = F(i), base address = 0 (8-byte aligned for ARM)
;
; Expected: mem[0]=0, mem[8]=1, mem[16]=1, mem[24]=2, mem[32]=3, mem[40]=5, mem[48]=8, mem[56]=13, mem[64]=21, mem[72]=34, mem[80]=55
; Expected: X3=55
; Cycles: 200
; Models: single_cycle, multicycle, pipeline
; Best viewed with: Any

MOVZ X20, #0           ; X20 = base address

; F(0) = 0
MOVZ X1, #0            ; X1 = F(n-2) = 0
STR X1, [X20, #0]      ; mem[0] = 0

; F(1) = 1
MOVZ X2, #1            ; X2 = F(n-1) = 1
STR X2, [X20, #8]      ; mem[8] = 1

; Loop F(2)..F(10)
MOVZ X4, #9            ; X4 = iterations remaining
MOVZ X5, #16           ; X5 = current byte offset (starts at 16 for F(2))

fib_loop:
ADD X3, X1, X2         ; X3 = F(n) = F(n-2) + F(n-1)
ADD X6, X20, X5        ; X6 = base + offset
STR X3, [X6, #0]       ; mem[offset] = F(n)
ADD X1, XZR, X2        ; X1 = F(n-1)
ADD X2, XZR, X3        ; X2 = F(n)
ADD X5, X5, #8         ; offset += 8
SUB X4, X4, #1         ; counter--
CBNZ X4, fib_loop      ; loop until done

; X3 = F(10) = 55
NOP
