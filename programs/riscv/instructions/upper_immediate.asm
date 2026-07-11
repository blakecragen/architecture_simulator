; === Upper Immediate Instructions ===
; Exercise LUI, AUIPC
; Expected: x1=0x12345000, x2=0xABCDE000, x3=PC-relative value
; Best viewed with: Any

; --- LUI: load upper immediate ---
; LUI places the 20-bit immediate into bits [31:12], zeroing bits [11:0]
LUI  x1, 0x12345       ; x1 = 0x12345 << 12 = 0x12345000
LUI  x2, 0xABCDE       ; x2 = 0xABCDE << 12 = 0xABCDE000

; --- Construct a full 32-bit constant using LUI + ADDI ---
LUI  x3, 0x10          ; x3 = 0x10000 (upper bits)
ADDI x3, x3, 0x20      ; x3 = 0x10000 + 0x20 = 0x10020

; --- AUIPC: add upper immediate to PC ---
; AUIPC rd, imm => rd = PC + (imm << 12)
AUIPC x4, 0            ; x4 = PC of this instruction (offset 0)
AUIPC x5, 1            ; x5 = PC + 0x1000

; --- Verify AUIPC difference ---
SUB  x6, x5, x4        ; x6 = x5 - x4 = 0x1000 + 4 = 0x1004
                        ; (because AUIPC x5 is 4 bytes after AUIPC x4)
