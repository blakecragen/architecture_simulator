; === Bubble Sort ===
; Sort a 5-element array [50, 20, 40, 10, 30] in ascending order
; Uses pipeline-safe comparison: SUB + AND mask + CBNZ
;
; Expected: X5=10, X6=20, X7=30, X8=40, X9=50
; Expected: mem[0]=10, mem[8]=20, mem[16]=30, mem[24]=40, mem[32]=50
; Models: single_cycle, multicycle, pipeline
; Best viewed with: Single Cycle or Pipeline (set cycles to 300+)

; Base address and sign-check mask (loaded once)
MOVZ X20, #0           ; X20 = base address
MOVZ X16, #128         ; X16 = bit-7 mask for sign detection

; Store unsorted array: 50, 20, 40, 10, 30
MOVZ X1, #50
STR X1, [X20, #0]
MOVZ X1, #20
STR X1, [X20, #8]
MOVZ X1, #40
STR X1, [X20, #16]
MOVZ X1, #10
STR X1, [X20, #24]
MOVZ X1, #30
STR X1, [X20, #32]

; Bubble sort: 4 passes (n-1 for 5 elements)
MOVZ X10, #4           ; X10 = outer loop counter

outer_loop:
ADD X11, XZR, X20      ; X11 = pointer to start of array
MOVZ X12, #4           ; X12 = inner comparisons per pass

inner_loop:
LDR X2, [X11, #0]      ; X2 = arr[i]
NOP                     ; forwarding gap for X2
LDR X3, [X11, #8]      ; X3 = arr[i+1]

; Compare: skip swap if arr[i] < arr[i+1]
SUB X15, X2, X3         ; X15 = arr[i] - arr[i+1]
AND X17, X15, X16       ; isolate sign bit (bit 7)
CBNZ X17, no_swap       ; if negative (a < b), skip swap

; Swap arr[i] and arr[i+1]
STR X3, [X11, #0]      ; arr[i] = smaller
STR X2, [X11, #8]      ; arr[i+1] = larger

no_swap:
ADD X11, X11, #8       ; advance pointer to next pair
SUB X12, X12, #1       ; inner count--
CBNZ X12, inner_loop   ; next comparison

NOP                    ; pipeline settle between nested branches
SUB X10, X10, #1       ; outer count--
CBNZ X10, outer_loop   ; next pass

; Load sorted results into registers
LDR X5, [X20, #0]      ; X5 = 10
NOP
LDR X6, [X20, #8]      ; X6 = 20
NOP
LDR X7, [X20, #16]     ; X7 = 30
NOP
LDR X8, [X20, #24]     ; X8 = 40
NOP
LDR X9, [X20, #32]     ; X9 = 50
