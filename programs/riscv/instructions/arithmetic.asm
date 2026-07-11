; === Arithmetic Instructions ===
; Exercise ADD, SUB, SLT, SLTU, ADDI, SLTI, SLTIU, SLLI, SRLI, SRAI, SLL, SRL, SRA
; Expected: x1=10, x2=20, x3=30, x4=10, x5=1, x6=0, x7=40, x8=1, x9=0, x10=80, x11=5, x12=-20 (0xFFFFFFEC), x13=80, x14=3, x15=-3 (0xFFFFFFFD)
; Best viewed with: Any

; --- Immediate arithmetic ---
ADDI x1, x0, 10        ; x1 = 10
ADDI x2, x0, 20        ; x2 = 20

; --- Register-register arithmetic ---
ADD  x3, x1, x2        ; x3 = 10 + 20 = 30
SUB  x4, x2, x1        ; x4 = 20 - 10 = 10

; --- Set less than ---
SLT  x5, x1, x2        ; x5 = (10 < 20) = 1
SLT  x6, x2, x1        ; x6 = (20 < 10) = 0
ADDI x7, x0, 40        ; x7 = 40

; --- Set less than immediate ---
SLTI  x8, x1, 15       ; x8 = (10 < 15) = 1
SLTIU x9, x7, 30       ; x9 = (40 <u 30) = 0

; --- Shift left logical ---
SLLI x10, x1, 3        ; x10 = 10 << 3 = 80

; --- Shift right logical ---
SRLI x11, x7, 3        ; x11 = 40 >> 3 = 5

; --- SUB to create negative, then shift right arithmetic ---
SUB  x12, x0, x2       ; x12 = 0 - 20 = -20
SRAI x13, x12, 0       ; x13 = -20 (no shift, just copy)

; --- Register shift operations ---
ADDI x14, x0, 3        ; x14 = 3 (shift amount)
SLL  x13, x1, x14      ; x13 = 10 << 3 = 80
SRL  x14, x10, x14     ; x14 = 80 >> 3 = 10 (reuse x14=3 as shift amount before overwrite)
ADDI x14, x0, 3        ; x14 = 3 again
SRA  x15, x12, x14     ; x15 = -20 >> 3 = -3 (arithmetic, sign-extended)
