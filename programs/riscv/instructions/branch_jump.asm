; === Branch and Jump Instructions ===
; Exercise BEQ, BNE, BLT, BGE, BLTU, BGEU, JAL, JALR
; Each branch stores a marker value to prove the correct path was taken
; Expected: x10=1, x11=1, x12=1, x13=1, x14=1, x15=1, x17=1, x18=1
; Best viewed with: Any

; --- Setup ---
ADDI x1, x0, 5         ; x1 = 5
ADDI x2, x0, 5         ; x2 = 5
ADDI x3, x0, 10        ; x3 = 10
ADDI x4, x0, -1        ; x4 = -1 (0xFFFFFFFF unsigned)

; --- BEQ: branch if x1 == x2 (5 == 5, taken) ---
BEQ  x1, x2, beq_taken
ADDI x10, x0, 0        ; skipped
beq_taken:
ADDI x10, x0, 1        ; x10 = 1

; --- BNE: branch if x1 != x3 (5 != 10, taken) ---
BNE  x1, x3, bne_taken
ADDI x11, x0, 0        ; skipped
bne_taken:
ADDI x11, x0, 1        ; x11 = 1

; --- BLT: branch if x1 < x3 signed (5 < 10, taken) ---
BLT  x1, x3, blt_taken
ADDI x12, x0, 0        ; skipped
blt_taken:
ADDI x12, x0, 1        ; x12 = 1

; --- BGE: branch if x3 >= x1 signed (10 >= 5, taken) ---
BGE  x3, x1, bge_taken
ADDI x13, x0, 0        ; skipped
bge_taken:
ADDI x13, x0, 1        ; x13 = 1

; --- BLTU: branch if x1 <u x4 (5 <u 0xFFFFFFFF, taken) ---
BLTU x1, x4, bltu_taken
ADDI x14, x0, 0        ; skipped
bltu_taken:
ADDI x14, x0, 1        ; x14 = 1

; --- BGEU: branch if x4 >=u x1 (0xFFFFFFFF >=u 5, taken) ---
BGEU x4, x1, bgeu_taken
ADDI x15, x0, 0        ; skipped
bgeu_taken:
ADDI x15, x0, 1        ; x15 = 1

; --- JAL: jump and link (x16 = return address) ---
JAL  x16, jal_target
ADDI x17, x0, 0        ; skipped
jal_target:
ADDI x17, x0, 1        ; x17 = 1

; --- JALR: jump to address in register ---
AUIPC x20, 0           ; x20 = PC of this instruction
ADDI  x20, x20, 12     ; x20 = PC + 12 = address of jalr_land
JALR  x19, x20, 0      ; jump to jalr_land, x19 = return address
ADDI  x18, x0, 0       ; skipped
jalr_land:
ADDI x18, x0, 1        ; x18 = 1
