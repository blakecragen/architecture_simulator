; === Double Forwarding ===
; Two source registers forwarded from different pipeline stages
; EX/MEM forward and MEM/WB forward occur simultaneously
; Expected: EAX=3, EBX=7, ECX=10, EDX=17
; Best viewed with: Pipeline

; --- Set up initial values ---
MOV EAX, 3             ; EAX = 3
MOV EBX, 7             ; EBX = 7

; --- Both sources need forwarding from different stages ---
ADD ECX, EAX           ; ECX = 0 + 3 = 3 (forward EAX from EX/MEM)
ADD ECX, EBX           ; ECX = 3 + 7 = 10 (forward ECX from EX/MEM, EBX from MEM/WB)

; --- Another double-forward scenario ---
MOV EDX, ECX           ; EDX = 10 (forward ECX from EX/MEM)
ADD EDX, EBX           ; EDX = 10 + 7 = 17 (forward EDX from EX/MEM, EBX from later stage)
NOP
NOP
