; === Arithmetic Instructions ===
; Exercise ADD, SUB, CMP in both reg,reg and reg,imm forms
; Expected: EAX=25, EBX=15, ECX=15, EDX=5, ESI=20, EDI=12
; Best viewed with: Any

; --- Load initial values ---
MOV EAX, 10            ; EAX = 10
MOV ECX, 15            ; ECX = 15

; --- ADD reg, reg ---
MOV EBX, EAX           ; EBX = 10
ADD EBX, ECX           ; EBX = 10 + 15 = 25

; --- SUB reg, reg ---
MOV EDX, ECX           ; EDX = 15
SUB EDX, EAX           ; EDX = 15 - 10 = 5

; --- ADD reg, imm ---
MOV ESI, EAX           ; ESI = 10
ADD ESI, 10            ; ESI = 10 + 10 = 20

; --- SUB reg, imm ---
MOV EDI, ECX           ; EDI = 15
SUB EDI, 3             ; EDI = 15 - 3 = 12

; --- CMP reg, imm (sets flags, does not store) ---
CMP EAX, 10            ; compare EAX with 10 (equal)
CMP EDX, 8             ; compare EDX=5 with 8 (less)

; --- CMP reg, reg ---
CMP EBX, ECX           ; compare EBX=25 with ECX=15 (greater)

; --- Final: swap into EAX for summary ---
MOV EAX, EBX           ; EAX = 25
MOV EBX, ECX           ; EBX = 15
