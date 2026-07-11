; === Nested Loop (Branch Prediction) ===
; Outer loop 3 iterations, inner loop 5 iterations each
; Total inner body executions = 15
; Expected: EAX=15, EBX=0, ECX=3
; Best viewed with: Pipeline

; --- Initialize ---
MOV EAX, 0             ; EAX = total count
MOV ECX, 0             ; ECX = outer counter

outer:
MOV EBX, 0             ; EBX = inner counter (reset each outer)

inner:
ADD EAX, 1             ; total++
ADD EBX, 1             ; inner++
CMP EBX, 5             ; inner < 5?
JNE inner              ; backward branch for inner loop

ADD ECX, 1             ; outer++
CMP ECX, 3             ; outer < 3?
JNE outer              ; backward branch for outer loop

; EAX = 15, EBX = 5, ECX = 3
MOV EBX, 0             ; clear EBX for clean result
