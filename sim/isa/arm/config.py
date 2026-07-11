from sim.isa.base import ISABase
from .constants import REGISTER_NAMES


class ARM(ISABase):
    name = "arm"
    display_name = "ARM (AArch64)"
    description = "64-bit ARM A64 instruction set (simulated as 32-bit data path)"
    num_regs = 32      # X0–X30 + XZR (index 31)
    zero_reg = True    # XZR (register 31) reads as zero
    zero_reg_index = 31  # ARM zero register is X31 (XZR), not X0
    pc_reset = 0
    program_format = "words"

    def register_names(self):
        return list(REGISTER_NAMES)

    def default_nop(self):
        return 0xD503201F  # NOP (hint #0)

    def demo_program(self):
        return [
            0xD2800141,  # MOVZ X1, #10         ; N = 10
            0xD2800002,  # MOVZ X2, #0          ; fib_prev = 0
            0xD2800023,  # MOVZ X3, #1          ; fib_curr = 1
            0x8B030044,  # ADD  X4, X2, X3      ; loop: temp = prev + curr
            0x8B1F0062,  # ADD  X2, X3, XZR     ; prev = curr
            0x8B1F0083,  # ADD  X3, X4, XZR     ; curr = temp
            0xD1000421,  # SUB  X1, X1, #1      ; N--
            0xEB1F003F,  # CMP  X1, XZR         ; set flags
            0x54FFFF61,  # B.NE loop            ; if N != 0 goto loop
        ]

    def demo_program_asm(self):
        return """\
MOVZ X1, #10         ; N = 10
MOVZ X2, #0          ; fib_prev = 0
MOVZ X3, #1          ; fib_curr = 1
loop:
ADD  X4, X2, X3      ; temp = prev + curr
ADD  X2, X3, XZR     ; prev = curr
ADD  X3, X4, XZR     ; curr = temp
SUB  X1, X1, #1      ; N--
CMP  X1, XZR         ; set flags
B.NE loop            ; if N != 0 goto loop"""
