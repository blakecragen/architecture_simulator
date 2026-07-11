; === Sum Array ===
; Store a 5-element array in memory, then sum all elements
; Array: [10, 20, 30, 40, 50], Sum = 150
; Expected: EAX=150, ECX=0
; Best viewed with: Any

; --- Store array at base address 0 ---
MOV EBX, 0             ; EBX = base address

MOV EAX, 10
MOV [EBX], EAX         ; array[0] = 10

MOV EAX, 20
MOV [EBX+4], EAX       ; array[1] = 20

MOV EAX, 30
MOV [EBX+8], EAX       ; array[2] = 30

MOV EAX, 40
MOV [EBX+12], EAX      ; array[3] = 40

MOV EAX, 50
MOV [EBX+16], EAX      ; array[4] = 50

; --- Sum loop using ESI as pointer ---
MOV EAX, 0             ; EAX = sum = 0
MOV ECX, 5             ; ECX = element count
MOV ESI, 0             ; ESI = pointer (starts at base)

sum_loop:
MOV EDX, [ESI]         ; EDX = mem[ESI] = array element
ADD EAX, EDX           ; sum += element
ADD ESI, 4             ; pointer += 4 (next element)
SUB ECX, 1             ; count--
CMP ECX, 0
JG sum_loop            ; loop while count > 0

; EAX = 10 + 20 + 30 + 40 + 50 = 150
