; === Fibonacci ===
; Compute the 10th Fibonacci number iteratively
; F(0)=0, F(1)=1, F(2)=1, ..., F(10)=55
; Expected: EAX=55, EBX=34, ECX=0
; Models: single_cycle, ooo
; Best viewed with: Any

; --- Initialize ---
; EAX = current (a), EBX = next (b)
MOV EAX, 0             ; a = F(0) = 0
MOV EBX, 1             ; b = F(1) = 1
MOV ECX, 9             ; loop counter (9 iterations to get F(10))

fib_loop:
; Step: temp = a + b, a = b, b = temp
MOV EDX, EAX           ; EDX = a
ADD EDX, EBX           ; EDX = a + b
MOV EAX, EBX           ; EAX = b (old b becomes new a)
MOV EBX, EDX           ; EBX = a + b (sum becomes new b)

SUB ECX, 1             ; counter--
CMP ECX, 0
JG fib_loop            ; loop while counter > 0

; After 10 iterations: EAX = F(9) = 34, EBX = F(10) = 55
; Swap for cleaner output
MOV EDX, EAX           ; save F(9)
MOV EAX, EBX           ; EAX = 55
MOV EBX, EDX           ; EBX = 34
