; === Logical Instructions ===
; Exercise AND, ORR, EOR
; Expected: X3=0x0000, X6=0x00F0, X7=0xFFFF, X8=0xFFFF, X9=0xAAAA, X10=0x5555, X11=0xFFFF, X12=0x0000, X13=0xFFFF
; Best viewed with: Any

; Load operands
MOVZ X1, #0xFF00       ; X1 = 0xFF00
MOVZ X2, #0x00FF       ; X2 = 0x00FF

; AND — bitwise AND
AND X3, X1, X2         ; X3 = 0xFF00 & 0x00FF = 0x0000
; Wait, that's 0. Let's use better values.

; Load new operands for interesting results
MOVZ X4, #0x0FF0       ; X4 = 0x0FF0
MOVZ X5, #0x00FF       ; X5 = 0x00FF

; AND
AND X6, X4, X5         ; X6 = 0x0FF0 & 0x00FF = 0x00F0

; ORR — bitwise OR
ORR X7, X1, X2         ; X7 = 0xFF00 | 0x00FF = 0xFFFF

; EOR — bitwise XOR
EOR X8, X1, X2         ; X8 = 0xFF00 ^ 0x00FF = 0xFFFF

; More logical operations
MOVZ X9, #0xAAAA       ; X9 = 0xAAAA
MOVZ X10, #0x5555      ; X10 = 0x5555

; XOR of complementary patterns
EOR X11, X9, X10       ; X11 = 0xAAAA ^ 0x5555 = 0xFFFF

; AND of complementary patterns
AND X12, X9, X10       ; X12 = 0xAAAA & 0x5555 = 0x0000

; OR of complementary patterns
ORR X13, X9, X10       ; X13 = 0xAAAA | 0x5555 = 0xFFFF
