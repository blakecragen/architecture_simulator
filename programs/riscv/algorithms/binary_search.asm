; === Binary Search ===
; Search for value 30 in sorted array [10, 20, 30, 40, 50]
; Array stored at mem[100..116]
;
; Expected: x10=2, x11=30
; Cycles: 300
; Models: single_cycle, multicycle, pipeline
; Best viewed with: Any

; --- Store sorted array at base 100 ---
ADDI x20, x0, 100      ; x20 = base address

ADDI x1, x0, 10
SW   x1, 0(x20)        ; mem[100] = 10

ADDI x1, x0, 20
SW   x1, 4(x20)        ; mem[104] = 20

ADDI x1, x0, 30
SW   x1, 8(x20)        ; mem[108] = 30

ADDI x1, x0, 40
SW   x1, 12(x20)       ; mem[112] = 40

ADDI x1, x0, 50
SW   x1, 16(x20)       ; mem[116] = 50

; --- Binary search for target = 30 ---
ADDI x11, x0, 30       ; x11 = target value
ADDI x12, x0, 0        ; x12 = low index
ADDI x13, x0, 4        ; x13 = high index

bs_loop:
BLT  x13, x12, bs_notfound ; if high < low, not found

; mid = (low + high) / 2
ADD  x14, x12, x13     ; x14 = low + high
SRLI x14, x14, 1       ; x14 = mid = (low + high) >> 1

; Load arr[mid]: address = base + mid*4
SLLI x15, x14, 2       ; x15 = mid * 4
ADD  x15, x20, x15     ; x15 = base + mid*4
LW   x16, 0(x15)       ; x16 = arr[mid]

BEQ  x16, x11, bs_found ; if arr[mid] == target, found

BLT  x11, x16, bs_go_left ; if target < arr[mid], search left

; target > arr[mid]: low = mid + 1
ADDI x12, x14, 1       ; low = mid + 1
JAL  x0, bs_loop

bs_go_left:
; target < arr[mid]: high = mid - 1
ADDI x13, x14, -1      ; high = mid - 1
JAL  x0, bs_loop

bs_found:
ADD  x10, x14, x0      ; x10 = mid (found index = 2)
JAL  x0, bs_done

bs_notfound:
ADDI x10, x0, -1       ; x10 = -1 (not found)

bs_done:
NOP
