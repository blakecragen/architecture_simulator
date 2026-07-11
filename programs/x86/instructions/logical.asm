; === Logical Instructions ===
; Exercise AND, OR, XOR in both reg,reg and reg,imm forms
; Expected: EAX=0xFF, EBX=0x0F, ECX=0xF0, EDX=0xFF, ESI=0x0F, EDI=0xAA
; Best viewed with: Any

; --- Load initial values ---
MOV EAX, 0xFF          ; EAX = 0xFF (255)
MOV ECX, 0x0F          ; ECX = 0x0F (15)

; --- AND reg, reg ---
MOV EBX, EAX           ; EBX = 0xFF
AND EBX, ECX           ; EBX = 0xFF & 0x0F = 0x0F

; --- OR reg, reg ---
MOV EDX, ECX           ; EDX = 0x0F
MOV ESI, 0xF0          ; ESI = 0xF0
OR  EDX, ESI           ; EDX = 0x0F | 0xF0 = 0xFF

; --- XOR reg, reg ---
MOV ECX, EAX           ; ECX = 0xFF
XOR ECX, ECX           ; ECX = 0xFF ^ 0xFF = 0x00

; --- AND reg, imm ---
MOV ESI, EAX           ; ESI = 0xFF
AND ESI, 0x0F          ; ESI = 0xFF & 0x0F = 0x0F

; --- OR reg, imm ---
MOV ECX, 0xA0          ; ECX = 0xA0
OR  ECX, 0x0A          ; ECX = 0xA0 | 0x0A = 0xAA

; --- XOR reg, imm ---
MOV EDI, ECX           ; EDI = 0xAA
XOR EDI, 0x00          ; EDI = 0xAA ^ 0x00 = 0xAA

; --- XOR self-clear idiom ---
MOV ECX, 0xF0          ; ECX = 0xF0 (restore for expected)
