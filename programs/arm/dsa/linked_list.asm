; === Linked List ===
; Build a 4-node singly linked list and traverse it
; Node format: [value (at +0), next_ptr (at +8)] = 16 bytes per node
; Nodes at addresses 64, 80, 96, 112 (8-byte aligned for ARM)
;
; Traverse the list, summing values and counting nodes
;
; Expected: X10=100, X11=4
; Cycles: 500
; Best viewed with: Any

; --- Build linked list ---
; Node 0 at addr 64: value=10, next=80
MOVZ X1, #10
MOVZ X2, #64
STR X1, [X2, #0]       ; mem[64] = 10 (value)
MOVZ X1, #80
STR X1, [X2, #8]       ; mem[72] = 80 (next ptr)

; Node 1 at addr 80: value=20, next=96
MOVZ X1, #20
MOVZ X2, #80
STR X1, [X2, #0]       ; mem[80] = 20
MOVZ X1, #96
STR X1, [X2, #8]       ; mem[88] = 96

; Node 2 at addr 96: value=30, next=112
MOVZ X1, #30
MOVZ X2, #96
STR X1, [X2, #0]       ; mem[96] = 30
MOVZ X1, #112
STR X1, [X2, #8]       ; mem[104] = 112

; Node 3 at addr 112: value=40, next=0 (null)
MOVZ X1, #40
MOVZ X2, #112
STR X1, [X2, #0]       ; mem[112] = 40
MOVZ X1, #0
STR X1, [X2, #8]       ; mem[120] = 0 (null)

; --- Traverse linked list ---
MOVZ X10, #0           ; X10 = sum
MOVZ X11, #0           ; X11 = count
MOVZ X3, #64           ; X3 = current_ptr = head (64)

traverse:
CBZ X3, traverse_done   ; if ptr == null (0), done
LDR X4, [X3, #0]       ; X4 = current->value
NOP                     ; forwarding gap
ADD X10, X10, X4       ; sum += value
ADD X11, X11, #1       ; count++
LDR X3, [X3, #8]       ; X3 = current->next
NOP                     ; forwarding gap
B traverse

traverse_done:
; X10 = 10 + 20 + 30 + 40 = 100
; X11 = 4
NOP
