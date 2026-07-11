; === Factorial ===
; Compute 7! = 5040 iteratively
; Expected: EAX=5040, ECX=1
; Best viewed with: Any

; --- Initialize ---
MOV EAX, 1             ; EAX = result = 1
MOV ECX, 7             ; ECX = n = 7

fact_loop:
; --- Multiply by repeated addition ---
; result = result * ECX (via repeated addition)
MOV EBX, EAX           ; EBX = result (copy for adding)
MOV EDX, ECX           ; EDX = multiplier counter
SUB EDX, 1             ; we already have 1x, need (ECX-1) more additions

mul_loop:
CMP EDX, 0
JLE mul_done           ; if multiplier counter <= 0, done
ADD EAX, EBX           ; result += original result
SUB EDX, 1             ; multiplier counter--
JMP mul_loop

mul_done:
SUB ECX, 1             ; n--
CMP ECX, 1
JG fact_loop           ; loop while n > 1

; EAX = 7! = 5040
