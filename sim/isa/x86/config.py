from sim.isa.base import ISABase
from .constants import REGISTER_NAMES


class X86(ISABase):
    name = "x86"
    display_name = "x86 (IA-32)"
    description = "32-bit x86 instruction set with variable-length encoding"
    num_regs = 8
    zero_reg = False
    pc_reset = 0
    program_format = "bytes"

    def register_names(self):
        return list(REGISTER_NAMES)

    def default_nop(self):
        return 0x90  # NOP (single byte)

    def demo_program(self):
        return [
            0xB9, 0x0A, 0x00, 0x00, 0x00,  # MOV ECX, 10       ; N = 10
            0xB8, 0x00, 0x00, 0x00, 0x00,  # MOV EAX, 0        ; fib_prev = 0
            0xBB, 0x01, 0x00, 0x00, 0x00,  # MOV EBX, 1        ; fib_curr = 1
            0x89, 0xC2,                      # MOV EDX, EAX      ; loop: temp = prev
            0x01, 0xDA,                      # ADD EDX, EBX      ; temp += curr
            0x89, 0xD8,                      # MOV EAX, EBX      ; prev = curr
            0x89, 0xD3,                      # MOV EBX, EDX      ; curr = temp
            0x83, 0xE9, 0x01,                # SUB ECX, 1        ; N--
            0x83, 0xF9, 0x00,                # CMP ECX, 0        ; set flags
            0x75, 0xF0,                      # JNE loop          ; if N != 0 goto loop
        ]

    def demo_program_asm(self):
        return """\
MOV ECX, 10       ; N = 10
MOV EAX, 0        ; fib_prev = 0
MOV EBX, 1        ; fib_curr = 1
loop:
MOV EDX, EAX      ; temp = prev
ADD EDX, EBX      ; temp += curr
MOV EAX, EBX      ; prev = curr
MOV EBX, EDX      ; curr = temp
SUB ECX, 1        ; N--
CMP ECX, 0        ; set flags
JNE loop          ; if N != 0 goto loop"""
