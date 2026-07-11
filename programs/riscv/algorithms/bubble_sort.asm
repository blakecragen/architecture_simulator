; === Bubble Sort ===
; Create a 5-element array, bubble sort it in ascending order
; Unsorted: [50, 20, 40, 10, 30]  ->  Sorted: [10, 20, 30, 40, 50]
; Array stored at memory addresses 100-116
;
; Expected: x1=10, x2=20, x3=30, x4=40, x5=50
; Expected: mem[100]=10, mem[104]=20, mem[108]=30, mem[112]=40, mem[116]=50
; Cycles: 500
; Best viewed with: Pipeline

; --- Store unsorted array at base address 100 ---
ADDI x20, x0, 100      ; x20 = 100 (base address)

ADDI x1, x0, 50
SW   x1, 0(x20)        ; mem[100] = 50

ADDI x1, x0, 20
SW   x1, 4(x20)        ; mem[104] = 20

ADDI x1, x0, 40
SW   x1, 8(x20)        ; mem[108] = 40

ADDI x1, x0, 10
SW   x1, 12(x20)       ; mem[112] = 10

ADDI x1, x0, 30
SW   x1, 16(x20)       ; mem[116] = 30

; --- Bubble sort ---
; Outer loop: repeat N-1 = 4 times
ADDI x10, x0, 4        ; x10 = 4 (outer loop counter)

outer_loop:
BEQ  x10, x0, sort_done ; if outer counter == 0, done

; Inner loop: compare adjacent pairs
ADDI x11, x0, 0        ; x11 = 0 (inner byte offset)
ADDI x12, x0, 0        ; x12 = inner limit (will be set)
SLLI x12, x10, 2       ; x12 = outer_counter * 4 (inner limit in bytes)

inner_loop:
BEQ  x11, x12, inner_done ; if inner offset == limit, inner done

; Load arr[j] and arr[j+1]
ADD  x13, x20, x11     ; x13 = base + offset
LW   x14, 0(x13)       ; x14 = arr[j]
LW   x15, 4(x13)       ; x15 = arr[j+1]

; if arr[j] <= arr[j+1], no swap needed
BLT  x15, x14, do_swap ; if arr[j+1] < arr[j], swap
JAL  x0, no_swap

do_swap:
SW   x15, 0(x13)       ; arr[j] = arr[j+1]
SW   x14, 4(x13)       ; arr[j+1] = arr[j]

no_swap:
ADDI x11, x11, 4       ; inner offset += 4
JAL  x0, inner_loop

inner_done:
ADDI x10, x10, -1      ; outer counter--
JAL  x0, outer_loop

sort_done:
; Array is now sorted: [10, 20, 30, 40, 50]
; Verify by loading results
LW   x1, 0(x20)        ; x1 = 10
LW   x2, 4(x20)        ; x2 = 20
LW   x3, 8(x20)        ; x3 = 30
LW   x4, 12(x20)       ; x4 = 40
LW   x5, 16(x20)       ; x5 = 50
