; === Binary Search ===
; Search for value 30 in sorted array [10, 20, 30, 40, 50]
; Array at mem[0..32] (8-byte aligned for ARM)
; Uses unrolled decision tree (ARM lacks shift instructions)
;
; Expected: X10=2, X11=30
; Cycles: 300
; Models: single_cycle, multicycle, pipeline, ooo
; Best viewed with: Any

MOVZ X20, #0           ; X20 = base address
MOVZ X18, #128         ; X18 = sign bit mask for comparisons

; Store sorted array
MOVZ X1, #10
STR X1, [X20, #0]      ; arr[0] = 10
MOVZ X1, #20
STR X1, [X20, #8]      ; arr[1] = 20
MOVZ X1, #30
STR X1, [X20, #16]     ; arr[2] = 30
MOVZ X1, #40
STR X1, [X20, #24]     ; arr[3] = 40
MOVZ X1, #50
STR X1, [X20, #32]     ; arr[4] = 50

; Target value
MOVZ X11, #30          ; X11 = target value

; --- Level 1: Compare with arr[2] (middle element) ---
LDR X16, [X20, #16]    ; X16 = arr[2] = 30
NOP                     ; forwarding gap
SUBS X15, X16, X11     ; compare arr[2] - target
B.EQ found_2           ; arr[2] == target -> found at index 2
AND X17, X15, X18      ; check sign bit
CBNZ X17, search_right ; sign set -> arr[2] < target -> search right

; --- Target < arr[2]: search left half [0..1] ---
; Compare with arr[0]
LDR X16, [X20, #0]     ; X16 = arr[0]
NOP
SUBS X15, X16, X11
B.EQ found_0
AND X17, X15, X18
CBNZ X17, check_1      ; arr[0] < target -> check arr[1]
; arr[0] > target -> not found
B not_found

check_1:
LDR X16, [X20, #8]     ; X16 = arr[1]
NOP
SUBS X15, X16, X11
B.EQ found_1
B not_found

; --- Target > arr[2]: search right half [3..4] ---
search_right:
LDR X16, [X20, #24]    ; X16 = arr[3]
NOP
SUBS X15, X16, X11
B.EQ found_3
AND X17, X15, X18
CBNZ X17, check_4      ; arr[3] < target -> check arr[4]
B not_found

check_4:
LDR X16, [X20, #32]    ; X16 = arr[4]
NOP
SUBS X15, X16, X11
B.EQ found_4
B not_found

found_0:
MOVZ X10, #0
B done
found_1:
MOVZ X10, #1
B done
found_2:
MOVZ X10, #2
B done
found_3:
MOVZ X10, #3
B done
found_4:
MOVZ X10, #4
B done
not_found:
MOVZ X10, #255         ; 255 = not found marker
done:
NOP
