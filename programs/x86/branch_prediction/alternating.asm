; === Alternating Branch Pattern ===
; T/NT/T/NT pattern to stress branch predictors
; Loop counts evens vs odds to create alternating taken/not-taken
; Expected: EAX=10, EBX=5, ECX=5
; Best viewed with: Pipeline

; --- Initialize ---
MOV EAX, 0             ; EAX = loop counter
MOV EBX, 0             ; EBX = even count
MOV ECX, 0             ; ECX = odd count
MOV EDX, 10            ; EDX = limit

loop_start:
; --- Test if EAX is odd (bit 0) ---
MOV ESI, EAX           ; ESI = current counter
AND ESI, 1             ; ESI = EAX & 1 (0 if even, 1 if odd)
CMP ESI, 0
JE is_even             ; alternates T/NT/T/NT...
ADD ECX, 1             ; odd count++
JMP next
is_even:
ADD EBX, 1             ; even count++
next:
ADD EAX, 1             ; counter++
CMP EAX, EDX           ; counter < 10?
JNE loop_start         ; backward branch

; EAX=10, EBX=5 (evens: 0,2,4,6,8), ECX=5 (odds: 1,3,5,7,9)
