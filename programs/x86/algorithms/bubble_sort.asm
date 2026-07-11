; === Bubble Sort ===
; Sort a 5-element array [50, 20, 40, 10, 30] in ascending order
; Result in memory: [10, 20, 30, 40, 50]
; Expected: EAX=10 (first element after sort)
; Best viewed with: Any

; --- Store unsorted array at address 0 ---
MOV EBX, 0             ; base address

MOV EAX, 50
MOV [EBX], EAX         ; array[0] = 50

MOV EAX, 20
MOV [EBX+4], EAX       ; array[1] = 20

MOV EAX, 40
MOV [EBX+8], EAX       ; array[2] = 40

MOV EAX, 10
MOV [EBX+12], EAX      ; array[3] = 10

MOV EAX, 30
MOV [EBX+16], EAX      ; array[4] = 30

; --- Bubble sort: 4 outer passes ---
MOV EDI, 4             ; EDI = outer passes remaining

outer:
MOV ESI, 0             ; ESI = pointer into array
MOV ECX, EDI           ; ECX = comparisons this pass

inner:
MOV EAX, [ESI]         ; EAX = array[j]
MOV EDX, [ESI+4]       ; EDX = array[j+1]
MOV EBP, EAX           ; EBP = a (copy for sign test)
SUB EBP, EDX           ; EBP = a - b, flags set
JE no_swap             ; equal -> skip swap
AND EBP, -128          ; isolate sign: 0 if a>b (small positive), non-zero if a<b
JNE no_swap            ; a < b -> skip swap (already in order)
; fall through: a > b -> swap

; --- Swap ---
MOV [ESI], EDX         ; array[j] = smaller
MOV [ESI+4], EAX       ; array[j+1] = larger

no_swap:
ADD ESI, 4             ; move to next pair
SUB ECX, 1             ; comparisons--
CMP ECX, 0
JG inner               ; continue inner loop

SUB EDI, 1             ; outer passes--
CMP EDI, 0
JG outer               ; continue outer loop

; --- Load first element to verify sort ---
MOV EAX, [EBX]         ; EAX = array[0] = 10 (smallest)
