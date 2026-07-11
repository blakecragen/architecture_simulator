from sim.isa.base import ISABase
from .constants import REGISTER_NAMES


class RISCV(ISABase):
    name = "riscv"
    display_name = "RISC-V (RV32I)"
    description = "32-bit RISC-V base integer instruction set"
    num_regs = 32
    zero_reg = True
    pc_reset = 0x0000_0000
    program_format = "words"

    def register_names(self):
        return list(REGISTER_NAMES)

    def default_nop(self):
        return 0x00000013  # ADDI x0, x0, 0

    def demo_program(self):
        return [
            0x00A00093,  # ADDI  x1, x0, 10     ; N = 10
            0x00000113,  # ADDI  x2, x0, 0      ; fib_prev = 0
            0x00100193,  # ADDI  x3, x0, 1      ; fib_curr = 1
            0x00310233,  # ADD   x4, x2, x3     ; loop: temp = prev + curr
            0x00018113,  # ADDI  x2, x3, 0      ; prev = curr
            0x00020193,  # ADDI  x3, x4, 0      ; curr = temp
            0xFFF08093,  # ADDI  x1, x1, -1     ; N--
            0xFE0098E3,  # BNE   x1, x0, loop   ; if N != 0 goto loop
        ]

    def demo_program_asm(self):
        return """\
ADDI  x1, x0, 10     ; N = 10
ADDI  x2, x0, 0      ; fib_prev = 0
ADDI  x3, x0, 1      ; fib_curr = 1
loop:
ADD   x4, x2, x3     ; temp = prev + curr
ADDI  x2, x3, 0      ; prev = curr
ADDI  x3, x4, 0      ; curr = temp
ADDI  x1, x1, -1     ; N--
BNE   x1, x0, loop   ; if N != 0 goto loop"""
