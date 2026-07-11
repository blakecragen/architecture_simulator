; === Factorial (Memory Table) ===
; Store factorial values 0!..7! in memory
; mem[i*4] = i!
;
; Expected: mem[0]=1, mem[4]=1, mem[8]=2, mem[12]=6, mem[16]=24, mem[20]=120, mem[24]=720, mem[28]=5040
; Expected: EAX=5040
; Cycles: 1500
; Best viewed with: Any

; 0! = 1, 1! = 1
MOV EBX, 0             ; EBX = base address
MOV EAX, 1             ; EAX = current factorial = 1
MOV [EBX], EAX         ; mem[0] = 0! = 1
MOV [EBX+4], EAX       ; mem[4] = 1! = 1

; Compute 2!..7! using count-down loop
MOV ECX, 2             ; ECX = current N (multiplier)
MOV EBX, 8             ; EBX = current mem offset
MOV EDI, 6             ; EDI = iterations remaining (2! through 7!)

fact_loop:
CMP EDI, 0
JLE fact_done           ; if iterations <= 0, done

; Multiply EAX by ECX: EAX = EAX * ECX via repeated addition
MOV EDX, EAX           ; EDX = original value
MOV ESI, ECX           ; ESI = multiplier counter
SUB ESI, 1             ; need (N-1) more additions (already have 1x)

mul_loop:
CMP ESI, 0
JLE mul_done            ; if counter <= 0, done
ADD EAX, EDX           ; EAX += original
SUB ESI, 1             ; counter--
JMP mul_loop

mul_done:
MOV [EBX], EAX         ; mem[offset] = N!
ADD ECX, 1             ; N++
ADD EBX, 4             ; offset += 4
SUB EDI, 1             ; iterations--
JMP fact_loop

fact_done:
; EAX = 7! = 5040
