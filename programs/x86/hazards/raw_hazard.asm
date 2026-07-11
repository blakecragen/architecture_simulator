; === RAW Hazard ===
; Back-to-back Read-After-Write dependency chain
; Each instruction reads the result of the previous one
; Expected: EAX=1, EBX=2, ECX=4, EDX=8, ESI=16
; Best viewed with: Pipeline

; --- RAW chain: each depends on the previous ---
MOV EAX, 1             ; EAX = 1
ADD EBX, EAX           ; EBX = 0 + 1 = 1 (RAW: reads EAX)
ADD EBX, EAX           ; EBX = 1 + 1 = 2 (RAW: reads EBX and EAX)
MOV ECX, EBX           ; ECX = 2 (RAW: reads EBX)
ADD ECX, ECX           ; ECX = 2 + 2 = 4 (RAW: reads ECX)
MOV EDX, ECX           ; EDX = 4 (RAW: reads ECX)
ADD EDX, EDX           ; EDX = 4 + 4 = 8 (RAW: reads EDX)
MOV ESI, EDX           ; ESI = 8 (RAW: reads EDX)
ADD ESI, ESI           ; ESI = 8 + 8 = 16 (RAW: reads ESI)
