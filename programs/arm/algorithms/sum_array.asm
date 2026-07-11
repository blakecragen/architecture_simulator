; === Sum Array ===
; Store a 5-element array then sum all elements
; Expected: X10=150 (10+20+30+40+50)
; Models: single_cycle, multicycle, pipeline
; Best viewed with: Pipeline

; Base address for array
MOVZ X1, #0            ; X1 = base address

; Store 5 elements: 10, 20, 30, 40, 50
MOVZ X2, #10
STR X2, [X1, #0]       ; arr[0] = 10
MOVZ X2, #20
STR X2, [X1, #8]       ; arr[1] = 20
MOVZ X2, #30
STR X2, [X1, #16]      ; arr[2] = 30
MOVZ X2, #40
STR X2, [X1, #24]      ; arr[3] = 40
MOVZ X2, #50
STR X2, [X1, #32]      ; arr[4] = 50

; Sum the array
MOVZ X10, #0           ; X10 = running sum
MOVZ X3, #5            ; X3 = element count
MOVZ X4, #0            ; X4 = byte offset

sum_loop:
LDR X5, [X1, #0]       ; load element (we advance X1)
ADD X10, X10, X5       ; sum += element
ADD X1, X1, #8         ; advance pointer by 8 bytes
SUB X3, X3, #1         ; count--
CBNZ X3, sum_loop      ; loop until all elements summed

; Result: X10 = 10 + 20 + 30 + 40 + 50 = 150
NOP
