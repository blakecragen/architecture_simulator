; === Fibonacci (Memory Table) ===
; Store Fibonacci sequence F(0)..F(10) in memory
; mem[i*4] = F(i), base address = 0
;
; Expected: mem[0]=0, mem[4]=1, mem[8]=1, mem[12]=2, mem[16]=3, mem[20]=5, mem[24]=8, mem[28]=13, mem[32]=21, mem[36]=34, mem[40]=55
; Expected: EAX=55
; Cycles: 300
; Best viewed with: Any

; F(0) = 0
MOV EBX, 0             ; EBX = current byte offset
MOV EAX, 0             ; EAX = F(n-2) = 0
MOV [EBX], EAX         ; mem[0] = 0

; F(1) = 1
MOV ECX, 1             ; ECX = F(n-1) = 1
MOV [EBX+4], ECX       ; mem[4] = 1

; Loop to compute F(2)..F(10)
MOV ESI, 9             ; ESI = iterations remaining
MOV EBX, 8             ; EBX = current byte offset

fib_loop:
CMP ESI, 0
JLE fib_done            ; if counter <= 0, done

MOV EDX, EAX           ; EDX = F(n-2)
ADD EDX, ECX           ; EDX = F(n-2) + F(n-1) = F(n)
MOV [EBX], EDX         ; mem[offset] = F(n)
MOV EAX, ECX           ; EAX = F(n-1) (shift)
MOV ECX, EDX           ; ECX = F(n) (shift)
ADD EBX, 4             ; offset += 4
SUB ESI, 1             ; counter--
JMP fib_loop

fib_done:
MOV EAX, ECX           ; EAX = F(10) = 55
