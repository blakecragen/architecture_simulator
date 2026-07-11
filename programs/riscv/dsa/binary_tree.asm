; === Binary Tree (Array-Based) ===
; 7-node complete binary tree stored as array
; Children of node i: left = 2i+1, right = 2i+2
; Values: [50, 25, 75, 10, 35, 60, 90]
;
; Sum all node values via linear scan = 345
;
; Expected: x10=345, x11=7
; Cycles: 300
; Models: single_cycle, multicycle, pipeline
; Best viewed with: Any

; --- Store tree as array at base 0 ---
ADDI x1, x0, 50
SW   x1, 0(x0)         ; tree[0] = 50 (root)

ADDI x1, x0, 25
SW   x1, 4(x0)         ; tree[1] = 25

ADDI x1, x0, 75
SW   x1, 8(x0)         ; tree[2] = 75

ADDI x1, x0, 10
SW   x1, 12(x0)        ; tree[3] = 10

ADDI x1, x0, 35
SW   x1, 16(x0)        ; tree[4] = 35

ADDI x1, x0, 60
SW   x1, 20(x0)        ; tree[5] = 60

ADDI x1, x0, 90
SW   x1, 24(x0)        ; tree[6] = 90

; --- Sum all nodes (linear scan of the array) ---
ADDI x10, x0, 0        ; x10 = sum
ADDI x11, x0, 0        ; x11 = count
ADDI x3, x0, 7         ; x3 = total nodes
ADDI x4, x0, 0         ; x4 = byte offset

sum_loop:
BEQ  x11, x3, sum_done ; if count == 7, done
LW   x5, 0(x4)         ; x5 = tree[i]
ADD  x10, x10, x5      ; sum += tree[i]
ADDI x11, x11, 1       ; count++
ADDI x4, x4, 4         ; offset += 4
JAL  x0, sum_loop

sum_done:
; x10 = 50 + 25 + 75 + 10 + 35 + 60 + 90 = 345
; x11 = 7
NOP
