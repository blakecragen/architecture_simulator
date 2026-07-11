; === GCD (Euclidean Algorithm) ===
; Compute GCD(48, 18) = 6 using subtraction-based Euclidean algorithm
; Expected: EAX=6
; Best viewed with: Any

; --- Initialize ---
MOV EAX, 48            ; EAX = a = 48
MOV EBX, 18            ; EBX = b = 18

; --- GCD loop: while a != b, subtract smaller from larger ---
gcd_loop:
CMP EAX, EBX           ; compare a and b
JE gcd_done            ; if a == b, GCD found

; Determine which is larger using AND mask trick
MOV EBP, EAX           ; EBP = a
SUB EBP, EBX           ; EBP = a - b
AND EBP, -128          ; 0 if a>b (positive diff < 128), non-zero if a<b
JNE a_less             ; a < b -> go to a_less

; a > b: a = a - b
SUB EAX, EBX
JMP gcd_loop

a_less:
; a < b: b = b - a
SUB EBX, EAX
JMP gcd_loop

gcd_done:
; EAX = EBX = GCD(48, 18) = 6
