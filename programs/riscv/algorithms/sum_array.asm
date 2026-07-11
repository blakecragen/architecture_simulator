; === Sum Array ===
; Store a 5-element array in memory, then sum all elements
; Array: [10, 20, 30, 40, 50]  stored at addresses 0, 4, 8, 12, 16
;
; Expected: x10=150 (sum of all elements)
; Models: single_cycle, multicycle, pipeline
; Best viewed with: Any

; --- Store array elements in memory ---
ADDI x1, x0, 10        ; x1 = 10
SW   x1, 0(x0)         ; mem[0] = 10

ADDI x1, x0, 20        ; x1 = 20
SW   x1, 4(x0)         ; mem[4] = 20

ADDI x1, x0, 30        ; x1 = 30
SW   x1, 8(x0)         ; mem[8] = 30

ADDI x1, x0, 40        ; x1 = 40
SW   x1, 12(x0)        ; mem[12] = 40

ADDI x1, x0, 50        ; x1 = 50
SW   x1, 16(x0)        ; mem[16] = 50

; --- Sum the array in a loop ---
ADDI x10, x0, 0        ; x10 = 0 (sum accumulator)
ADDI x2, x0, 0         ; x2 = 0 (byte offset into array)
ADDI x3, x0, 20        ; x3 = 20 (end offset: 5 elements * 4 bytes)

sum_loop:
BEQ  x2, x3, sum_done  ; if offset == 20, done
LW   x4, 0(x2)         ; x4 = mem[offset]
ADD  x10, x10, x4      ; sum += x4
ADDI x2, x2, 4         ; offset += 4
JAL  x0, sum_loop

sum_done:
; x10 = 10 + 20 + 30 + 40 + 50 = 150
NOP
