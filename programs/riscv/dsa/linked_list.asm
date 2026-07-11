; === Linked List ===
; Build a 4-node singly linked list and traverse it
; Node format: [value (4B), next_ptr (4B)] = 8 bytes per node
; Nodes at addresses 100, 108, 116, 124
;
; Traverse the list, summing values and counting nodes
;
; Expected: x10=100, x11=4
; Cycles: 300
; Best viewed with: Any

; --- Build linked list ---
ADDI x20, x0, 100      ; x20 = base address for nodes

; Node 0 at addr 100: value=10, next=108
ADDI x1, x0, 10
SW   x1, 0(x20)        ; mem[100] = 10 (value)
ADDI x1, x0, 108
SW   x1, 4(x20)        ; mem[104] = 108 (next ptr)

; Node 1 at addr 108: value=20, next=116
ADDI x1, x0, 20
ADDI x2, x0, 108
SW   x1, 0(x2)         ; mem[108] = 20
ADDI x1, x0, 116
SW   x1, 4(x2)         ; mem[112] = 116

; Node 2 at addr 116: value=30, next=124
ADDI x1, x0, 30
ADDI x2, x0, 116
SW   x1, 0(x2)         ; mem[116] = 30
ADDI x1, x0, 124
SW   x1, 4(x2)         ; mem[120] = 124

; Node 3 at addr 124: value=40, next=0 (null)
ADDI x1, x0, 40
ADDI x2, x0, 124
SW   x1, 0(x2)         ; mem[124] = 40
SW   x0, 4(x2)         ; mem[128] = 0 (null)

; --- Traverse linked list ---
ADDI x10, x0, 0        ; x10 = sum = 0
ADDI x11, x0, 0        ; x11 = count = 0
ADD  x3, x20, x0       ; x3 = current_ptr = head (100)

traverse:
BEQ  x3, x0, traverse_done ; if ptr == null, done
LW   x4, 0(x3)         ; x4 = current->value
ADD  x10, x10, x4      ; sum += value
ADDI x11, x11, 1       ; count++
LW   x3, 4(x3)         ; x3 = current->next
JAL  x0, traverse

traverse_done:
; x10 = 10 + 20 + 30 + 40 = 100
; x11 = 4
NOP
