"""
Assembler tests — round-trip verification against known hex encodings.

Tests all three ISAs (RISC-V, ARM, x86) with exact byte-level comparisons
to the encodings used by the existing decoder tests.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.assembler import assemble
from sim.assembler.riscv import RISCVAssembler
from sim.assembler.arm import ARMAssembler
from sim.assembler.x86 import X86Assembler
from sim.assembler.base import AssemblerError
from sim.assembler.cheatsheet import get_cheatsheet


# ════════════════════════════════════════════════════════════════════
#  RISC-V RV32I
# ════════════════════════════════════════════════════════════════════

class TestRISCVAssembler(unittest.TestCase):
    """Test RISC-V RV32I assembler against known decoder test encodings."""

    def setUp(self):
        self.asm = RISCVAssembler()

    # ── Individual instruction encoding (from test_riscv_single_cycle.py) ──

    def test_addi_x1_x0_5(self):
        result = self.asm.assemble("ADDI x1, x0, 5")
        self.assertEqual(result, [0x00500093])

    def test_addi_x2_x0_3(self):
        result = self.asm.assemble("ADDI x2, x0, 3")
        self.assertEqual(result, [0x00300113])

    def test_add_x3_x1_x2(self):
        result = self.asm.assemble("ADD x3, x1, x2")
        self.assertEqual(result, [0x002081B3])

    def test_sub_x4_x1_x2(self):
        result = self.asm.assemble("SUB x4, x1, x2")
        self.assertEqual(result, [0x40208233])

    def test_sw_x3_0_x0(self):
        result = self.asm.assemble("SW x3, 0(x0)")
        self.assertEqual(result, [0x00302023])

    def test_lw_x5_0_x0(self):
        result = self.asm.assemble("LW x5, 0(x0)")
        self.assertEqual(result, [0x00002283])

    def test_beq_x1_x2_plus8(self):
        """BEQ x1, x2, +8 at PC=0 -> offset=8."""
        result = self.asm.assemble("BEQ x1, x2, +8")
        self.assertEqual(result, [0x00208463])

    def test_addi_x6_x0_99(self):
        result = self.asm.assemble("ADDI x6, x0, 99")
        self.assertEqual(result, [0x06300313])

    # ── Full test program (matches test_riscv_single_cycle.py PROGRAM) ──

    def test_full_program(self):
        program = """
            ADDI x1, x0, 5
            ADDI x2, x0, 3
            ADD  x3, x1, x2
            SUB  x4, x1, x2
            SW   x3, 0(x0)
            LW   x5, 0(x0)
            BEQ  x1, x2, +8
            ADDI x6, x0, 99
        """
        expected = [
            0x00500093,  # ADDI x1, x0, 5
            0x00300113,  # ADDI x2, x0, 3
            0x002081B3,  # ADD  x3, x1, x2
            0x40208233,  # SUB  x4, x1, x2
            0x00302023,  # SW   x3, 0(x0)
            0x00002283,  # LW   x5, 0(x0)
            0x00208463,  # BEQ  x1, x2, +8
            0x06300313,  # ADDI x6, x0, 99
        ]
        result = self.asm.assemble(program)
        self.assertEqual(len(result), len(expected))
        for i, (got, exp) in enumerate(zip(result, expected)):
            self.assertEqual(got, exp,
                f"Instruction {i}: got 0x{got:08X}, expected 0x{exp:08X}")

    # ── LUI ─────────────────────────────────────────────────────────

    def test_lui(self):
        result = self.asm.assemble("LUI x1, 0x12345")
        self.assertEqual(result, [0x123450B7])

    # ── JAL ─────────────────────────────────────────────────────────

    def test_jal_plus8(self):
        """JAL x1, +8 at PC=0."""
        result = self.asm.assemble("JAL x1, +8")
        self.assertEqual(result, [0x008000EF])

    # ── Branch taken (BEQ x0, x0, +8) ──────────────────────────────

    def test_beq_x0_x0_plus8(self):
        result = self.asm.assemble("BEQ x0, x0, +8")
        self.assertEqual(result, [0x00000463])

    # ── ABI register names ──────────────────────────────────────────

    def test_abi_names(self):
        """ADDI a0, zero, 5 should be same as ADDI x10, x0, 5."""
        result = self.asm.assemble("ADDI a0, zero, 5")
        expected = self.asm.assemble("ADDI x10, x0, 5")
        self.assertEqual(result, expected)

    # ── Label resolution ────────────────────────────────────────────

    def test_branch_label(self):
        """BEQ with label should resolve to correct offset."""
        program = """
            ADDI x1, x0, 5
            BEQ x1, x0, skip
            ADDI x2, x0, 99
        skip:
            ADDI x3, x0, 42
        """
        result = self.asm.assemble(program)
        # BEQ at PC=4, label 'skip' at PC=12, offset=8
        # Same encoding as BEQ x1, x0, +8
        self.assertEqual(len(result), 4)
        # Check the branch instruction (index 1) has offset 8
        beq_word = result[1]
        # Extract B-type immediate from the word
        # bits: [31] | [30:25] | [24:20] | [19:15] | [14:12] | [11:8] | [7] | [6:0]
        # imm12=bit31, imm10:5=bits30:25, imm4:1=bits11:8, imm11=bit7
        bit_12  = (beq_word >> 31) & 1
        bit_10_5 = (beq_word >> 25) & 0x3F
        bit_4_1  = (beq_word >> 8) & 0xF
        bit_11  = (beq_word >> 7) & 1
        imm_raw = (bit_12 << 12) | (bit_11 << 11) | (bit_10_5 << 5) | (bit_4_1 << 1)
        self.assertEqual(imm_raw, 8)

    # ── Logical R-type ──────────────────────────────────────────────

    def test_and_or_xor(self):
        result = self.asm.assemble("AND x3, x1, x2")
        # AND: funct7=0000000, rs2=2, rs1=1, funct3=111, rd=3, opcode=0110011
        expected = (0b0000000 << 25) | (2 << 20) | (1 << 15) | (0b111 << 12) | (3 << 7) | 0b0110011
        self.assertEqual(result[0], expected)

    def test_or(self):
        result = self.asm.assemble("OR x3, x1, x2")
        expected = (0b0000000 << 25) | (2 << 20) | (1 << 15) | (0b110 << 12) | (3 << 7) | 0b0110011
        self.assertEqual(result[0], expected)

    def test_xor(self):
        result = self.asm.assemble("XOR x3, x1, x2")
        expected = (0b0000000 << 25) | (2 << 20) | (1 << 15) | (0b100 << 12) | (3 << 7) | 0b0110011
        self.assertEqual(result[0], expected)

    # ── JALR ────────────────────────────────────────────────────────

    def test_jalr(self):
        result = self.asm.assemble("JALR x0, x1, 0")
        # JALR: imm=0, rs1=1, funct3=000, rd=0, opcode=1100111
        expected = (0 << 20) | (1 << 15) | (0 << 12) | (0 << 7) | 0b1100111
        self.assertEqual(result[0], expected)

    # ── AUIPC ───────────────────────────────────────────────────────

    def test_auipc(self):
        result = self.asm.assemble("AUIPC x1, 0x1000")
        expected = (0x1000 << 12) | (1 << 7) | 0b0010111
        self.assertEqual(result[0], expected)

    # ── Comments and whitespace ─────────────────────────────────────

    def test_comments_stripped(self):
        program = """
            ADDI x1, x0, 5  # load 5 into x1
            ; this is a comment
            ADDI x2, x0, 3  // another comment
        """
        result = self.asm.assemble(program)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], 0x00500093)
        self.assertEqual(result[1], 0x00300113)

    # ── NOP pseudo-instruction ──────────────────────────────────────

    def test_nop(self):
        result = self.asm.assemble("NOP")
        # NOP = ADDI x0, x0, 0
        expected = (0 << 20) | (0 << 15) | (0b000 << 12) | (0 << 7) | 0b0010011
        self.assertEqual(result[0], expected)

    # ── Error handling ──────────────────────────────────────────────

    def test_unknown_mnemonic(self):
        with self.assertRaises(AssemblerError):
            self.asm.assemble("BOGUS x1, x2, x3")

    def test_bad_register(self):
        with self.assertRaises(AssemblerError):
            self.asm.assemble("ADD x1, x99, x2")

    def test_dispatch(self):
        """Test the dispatch function."""
        result = assemble("riscv", "ADDI x1, x0, 5")
        self.assertEqual(result, [0x00500093])

    # ── Remaining branch types ──────────────────────────────────────

    def test_bne(self):
        """BNE x1, x2, +8 at PC=0."""
        result = self.asm.assemble("BNE x1, x2, +8")
        opcode = result[0] & 0x7F
        funct3 = (result[0] >> 12) & 0x7
        self.assertEqual(opcode, 0b1100011)
        self.assertEqual(funct3, 0b001)

    def test_blt(self):
        result = self.asm.assemble("BLT x1, x2, +8")
        funct3 = (result[0] >> 12) & 0x7
        self.assertEqual(funct3, 0b100)

    def test_bge(self):
        result = self.asm.assemble("BGE x1, x2, +8")
        funct3 = (result[0] >> 12) & 0x7
        self.assertEqual(funct3, 0b101)


# ════════════════════════════════════════════════════════════════════
#  ARM AArch64
# ════════════════════════════════════════════════════════════════════

class TestARMAssembler(unittest.TestCase):
    """Test ARM AArch64 assembler against known decoder test encodings."""

    def setUp(self):
        self.asm = ARMAssembler()

    # ── Individual instruction encoding (from test_arm_single_cycle.py) ──

    def test_movz_x1_10(self):
        result = self.asm.assemble("MOVZ X1, #10")
        self.assertEqual(result, [0xD2800141])

    def test_movz_x2_3(self):
        result = self.asm.assemble("MOVZ X2, #3")
        self.assertEqual(result, [0xD2800062])

    def test_add_x3_x1_x2(self):
        result = self.asm.assemble("ADD X3, X1, X2")
        self.assertEqual(result, [0x8B020023])

    def test_sub_x4_x1_x2(self):
        result = self.asm.assemble("SUB X4, X1, X2")
        self.assertEqual(result, [0xCB020024])

    def test_str_x3_x0_0(self):
        result = self.asm.assemble("STR X3, [X0, #0]")
        self.assertEqual(result, [0xF9000003])

    def test_ldr_x5_x0_0(self):
        result = self.asm.assemble("LDR X5, [X0, #0]")
        self.assertEqual(result, [0xF9400005])

    # ── Logical operations (from test_arm_single_cycle.py) ──────────

    def test_and(self):
        result = self.asm.assemble("AND X3, X1, X2")
        self.assertEqual(result, [0x8A020023])

    def test_orr(self):
        result = self.asm.assemble("ORR X4, X1, X2")
        self.assertEqual(result, [0xAA020024])

    def test_eor(self):
        result = self.asm.assemble("EOR X5, X1, X2")
        self.assertEqual(result, [0xCA020025])

    # ── ADD immediate ───────────────────────────────────────────────

    def test_add_imm(self):
        result = self.asm.assemble("ADD X2, X1, #5")
        self.assertEqual(result, [0x91001422])

    # ── STR/LDR with offset ─────────────────────────────────────────

    def test_str_x1_x0_0(self):
        """STR X1, [X0, #0]."""
        result = self.asm.assemble("STR X1, [X0, #0]")
        self.assertEqual(result, [0xF9000001])

    def test_ldr_x2_x0_0(self):
        """LDR X2, [X0, #0]."""
        result = self.asm.assemble("LDR X2, [X0, #0]")
        self.assertEqual(result, [0xF9400002])

    # ── Branch ──────────────────────────────────────────────────────

    def test_b_plus8(self):
        """B +8 at PC=4."""
        # B imm26: offset=+8 bytes, imm26 = 8/4 = 2
        # Full encoding: 000101 | 00000000000000000000000010 = 0x14000002
        result = self.asm.assemble("""
            NOP
            B +8
            NOP
            NOP
        """)
        self.assertEqual(result[1], 0x14000002)

    def test_bl_plus8(self):
        """BL +8 at PC=0."""
        # BL imm26: offset=+8, imm26=2 => 100101 | 2 = 0x94000002
        result = self.asm.assemble("BL +8")
        self.assertEqual(result, [0x94000002])

    # ── CBZ ─────────────────────────────────────────────────────────

    def test_cbz_x0_plus8(self):
        """CBZ X0, +8 at PC=0."""
        result = self.asm.assemble("CBZ X0, +8")
        self.assertEqual(result, [0xB4000040])

    def test_cbz_x1_plus8(self):
        """CBZ X1, +8 at PC=4 (second instruction)."""
        program = """
            MOVZ X1, #5
            CBZ X1, +8
        """
        result = self.asm.assemble(program)
        # CBZ at PC=4: sf=1, 011010, op=0, imm19=2 (8/4), Rt=1
        self.assertEqual(result[1], 0xB4000041)

    # ── SUBS / CMP ──────────────────────────────────────────────────

    def test_subs_xzr(self):
        """SUBS XZR, X0, X0 (CMP X0, X0)."""
        result = self.asm.assemble("SUBS XZR, X0, X0")
        self.assertEqual(result, [0xEB00001F])

    def test_cmp_alias(self):
        """CMP X0, X0 = SUBS XZR, X0, X0."""
        result = self.asm.assemble("CMP X0, X0")
        self.assertEqual(result, [0xEB00001F])

    # ── NOP ─────────────────────────────────────────────────────────

    def test_nop(self):
        result = self.asm.assemble("NOP")
        self.assertEqual(result, [0xD503201F])

    # ── RET ─────────────────────────────────────────────────────────

    def test_ret(self):
        result = self.asm.assemble("RET")
        # RET X30: 1101011_0010_11111_0000_00_11110_00000
        expected = (0b1101011_0010_11111_0000_00 << 10) | (30 << 5) | 0
        self.assertEqual(result, [expected])

    # ── MOV alias ───────────────────────────────────────────────────

    def test_mov_alias(self):
        """MOV X1, #10 should produce same as MOVZ X1, #10."""
        result = self.asm.assemble("MOV X1, #10")
        self.assertEqual(result, [0xD2800141])

    # ── Label resolution ────────────────────────────────────────────

    def test_b_label(self):
        """B with label should resolve correctly."""
        program = """
            MOVZ X1, #10
            B skip
            MOVZ X1, #99
        skip:
            MOVZ X2, #3
        """
        result = self.asm.assemble(program)
        # B at PC=4, 'skip' at PC=12, offset=8, imm26=2
        self.assertEqual(result[1], 0x14000002)

    # ── MOVZ values from tests ──────────────────────────────────────

    def test_movz_x1_15(self):
        result = self.asm.assemble("MOVZ X1, #15")
        self.assertEqual(result, [0xD28001E1])

    def test_movz_x2_10(self):
        result = self.asm.assemble("MOVZ X2, #10")
        self.assertEqual(result, [0xD2800142])

    def test_movz_x1_13(self):
        result = self.asm.assemble("MOVZ X1, #13")
        self.assertEqual(result, [0xD28001A1])

    def test_movz_x1_5(self):
        result = self.asm.assemble("MOVZ X1, #5")
        self.assertEqual(result, [0xD28000A1])

    # ── B.cond ──────────────────────────────────────────────────────

    def test_bcond_eq(self):
        """B.EQ +8 at PC=0."""
        result = self.asm.assemble("B.EQ +8")
        # 01010100 | imm19=2 | 0 | cond=0
        expected = (0b01010100 << 24) | (2 << 5) | 0
        self.assertEqual(result, [expected])

    def test_bcond_ne(self):
        result = self.asm.assemble("B.NE +8")
        expected = (0b01010100 << 24) | (2 << 5) | 1
        self.assertEqual(result, [expected])

    # ── Dispatch ────────────────────────────────────────────────────

    def test_dispatch(self):
        result = assemble("arm", "MOVZ X1, #10")
        self.assertEqual(result, [0xD2800141])

    # ── Error handling ──────────────────────────────────────────────

    def test_unknown_mnemonic(self):
        with self.assertRaises(AssemblerError):
            self.asm.assemble("BOGUS X1, X2")


# ════════════════════════════════════════════════════════════════════
#  x86-32 (IA-32)
# ════════════════════════════════════════════════════════════════════

class TestX86Assembler(unittest.TestCase):
    """Test x86-32 assembler against known decoder test encodings."""

    def setUp(self):
        self.asm = X86Assembler()

    # ── MOV r32, imm32 ──────────────────────────────────────────────

    def test_mov_eax_10(self):
        result = self.asm.assemble("MOV EAX, 10")
        self.assertEqual(result, [0xB8, 0x0A, 0x00, 0x00, 0x00])

    def test_mov_ecx_3(self):
        result = self.asm.assemble("MOV ECX, 3")
        self.assertEqual(result, [0xB9, 0x03, 0x00, 0x00, 0x00])

    def test_mov_eax_42(self):
        result = self.asm.assemble("MOV EAX, 42")
        self.assertEqual(result, [0xB8, 0x2A, 0x00, 0x00, 0x00])

    def test_mov_ecx_100(self):
        result = self.asm.assemble("MOV ECX, 100")
        self.assertEqual(result, [0xB9, 0x64, 0x00, 0x00, 0x00])

    # ── ADD r32, r32 ────────────────────────────────────────────────

    def test_add_eax_ecx(self):
        result = self.asm.assemble("ADD EAX, ECX")
        self.assertEqual(result, [0x01, 0xC8])

    # ── MOV r32, r32 ───────────────────────────────────────────────

    def test_mov_edx_eax(self):
        result = self.asm.assemble("MOV EDX, EAX")
        self.assertEqual(result, [0x89, 0xC2])

    # ── SUB r32, r32 ───────────────────────────────────────────────

    def test_sub_edx_ecx(self):
        result = self.asm.assemble("SUB EDX, ECX")
        self.assertEqual(result, [0x29, 0xCA])

    # ── ADD r32, imm8 ──────────────────────────────────────────────

    def test_add_eax_5(self):
        result = self.asm.assemble("ADD EAX, 5")
        self.assertEqual(result, [0x83, 0xC0, 0x05])

    # ── CMP r32, imm8 ──────────────────────────────────────────────

    def test_cmp_eax_18(self):
        result = self.asm.assemble("CMP EAX, 18")
        self.assertEqual(result, [0x83, 0xF8, 0x12])

    def test_cmp_eax_5(self):
        result = self.asm.assemble("CMP EAX, 5")
        self.assertEqual(result, [0x83, 0xF8, 0x05])

    def test_cmp_eax_3(self):
        result = self.asm.assemble("CMP EAX, 3")
        self.assertEqual(result, [0x83, 0xF8, 0x03])

    # ── SUB r32, imm8 ──────────────────────────────────────────────

    def test_sub_eax_3(self):
        result = self.asm.assemble("SUB EAX, 3")
        self.assertEqual(result, [0x83, 0xE8, 0x03])

    # ── AND / OR / XOR r32, r32 ────────────────────────────────────

    def test_and_edx_ecx(self):
        result = self.asm.assemble("AND EDX, ECX")
        self.assertEqual(result, [0x21, 0xCA])

    def test_or_ebx_ecx(self):
        result = self.asm.assemble("OR EBX, ECX")
        self.assertEqual(result, [0x09, 0xCB])

    def test_xor_eax_ecx(self):
        result = self.asm.assemble("XOR EAX, ECX")
        self.assertEqual(result, [0x31, 0xC8])

    # ── MOV r32, r32 (more cases from test) ─────────────────────────

    def test_mov_edx_eax_2(self):
        result = self.asm.assemble("MOV EDX, EAX")
        # 0x89 ModRM: mod=11, reg=EAX(0), rm=EDX(2) -> 11_000_010 = 0xC2
        self.assertEqual(result, [0x89, 0xC2])

    def test_mov_ebx_eax(self):
        result = self.asm.assemble("MOV EBX, EAX")
        # mod=11, reg=EAX(0), rm=EBX(3) -> 11_000_011 = 0xC3
        self.assertEqual(result, [0x89, 0xC3])

    # ── NOP / RET ───────────────────────────────────────────────────

    def test_nop(self):
        result = self.asm.assemble("NOP")
        self.assertEqual(result, [0x90])

    def test_ret(self):
        result = self.asm.assemble("RET")
        self.assertEqual(result, [0xC3])

    # ── PUSH / POP ──────────────────────────────────────────────────

    def test_push_eax(self):
        result = self.asm.assemble("PUSH EAX")
        self.assertEqual(result, [0x50])

    def test_pop_eax(self):
        result = self.asm.assemble("POP EAX")
        self.assertEqual(result, [0x58])

    def test_push_ebx(self):
        result = self.asm.assemble("PUSH EBX")
        self.assertEqual(result, [0x53])

    # ── JMP rel8 ────────────────────────────────────────────────────

    def test_jmp_skip_2_nops(self):
        """JMP +2 (skip 2 bytes) from PC=0.

        From test: [0xEB, 0x02] -- disp8=2, which skips 2 bytes after the JMP.
        In our assembler: offset from PC=0 is +4 (JMP is 2 bytes + skip 2 bytes),
        but the encoding is disp8 = target - (pc + 2) = 4 - 2 = 2.

        When using a label, the label would be at address 4.
        Offset from PC = 4, disp8 = 4 - 2 = 2.
        """
        program = """
            JMP skip
            NOP
            NOP
        skip:
            MOV EAX, 99
        """
        result = self.asm.assemble(program)
        self.assertEqual(result[0], 0xEB)
        self.assertEqual(result[1], 0x02)

    # ── JE (taken and not taken from test) ──────────────────────────

    def test_je_encoding(self):
        """JE with label."""
        program = """
            MOV EAX, 5
            CMP EAX, 5
            JE skip
            NOP
        skip:
            MOV ECX, 99
        """
        result = self.asm.assemble(program)
        # JE at PC=8 (5 + 3), target 'skip' at PC=11 (8+2+1), offset=3, disp8=3-2=1
        # Find the JE bytes: MOV=5bytes, CMP=3bytes -> JE at index 8
        self.assertEqual(result[8], 0x74)   # JE opcode
        self.assertEqual(result[9], 0x01)   # disp8 = 1

    # ── Full test program (from test_x86_single_cycle.py add_r32) ──

    def test_full_add_program(self):
        program = """
            MOV EAX, 10
            MOV ECX, 3
            ADD EAX, ECX
        """
        expected = [
            0xB8, 0x0A, 0x00, 0x00, 0x00,  # MOV EAX, 10
            0xB9, 0x03, 0x00, 0x00, 0x00,  # MOV ECX, 3
            0x01, 0xC8,                      # ADD EAX, ECX
        ]
        result = self.asm.assemble(program)
        self.assertEqual(result, expected)

    # ── Full logical program ────────────────────────────────────────

    def test_full_logical_program(self):
        program = """
            MOV EAX, 15
            MOV ECX, 10
            MOV EDX, EAX
            AND EDX, ECX
            MOV EBX, EAX
            OR  EBX, ECX
        """
        expected = [
            0xB8, 0x0F, 0x00, 0x00, 0x00,  # MOV EAX, 15
            0xB9, 0x0A, 0x00, 0x00, 0x00,  # MOV ECX, 10
            0x89, 0xC2,                      # MOV EDX, EAX
            0x21, 0xCA,                      # AND EDX, ECX
            0x89, 0xC3,                      # MOV EBX, EAX
            0x09, 0xCB,                      # OR  EBX, ECX
        ]
        result = self.asm.assemble(program)
        self.assertEqual(result, expected)

    # ── MOV r32, [r32] ─────────────────────────────────────────────

    def test_mov_eax_mem_ebx(self):
        """MOV EAX, [EBX]."""
        result = self.asm.assemble("MOV EAX, [EBX]")
        # 0x8B ModRM: mod=00, reg=EAX(0), rm=EBX(3) -> 00_000_011 = 0x03
        self.assertEqual(result, [0x8B, 0x03])

    # ── MOV [r32], r32 ─────────────────────────────────────────────

    def test_mov_mem_ebx_eax(self):
        """MOV [EBX], EAX."""
        result = self.asm.assemble("MOV [EBX], EAX")
        # 0x89 ModRM: mod=00, reg=EAX(0), rm=EBX(3) -> 00_000_011 = 0x03
        self.assertEqual(result, [0x89, 0x03])

    # ── MOV r32, [r32+disp8] ───────────────────────────────────────

    def test_mov_eax_mem_ebx_plus4(self):
        """MOV EAX, [EBX+4]."""
        result = self.asm.assemble("MOV EAX, [EBX+4]")
        # 0x8B ModRM: mod=01, reg=EAX(0), rm=EBX(3) -> 01_000_011 = 0x43
        self.assertEqual(result, [0x8B, 0x43, 0x04])

    # ── MOV [r32+disp8], r32 ───────────────────────────────────────

    def test_mov_mem_ebx_plus4_eax(self):
        """MOV [EBX+4], EAX."""
        result = self.asm.assemble("MOV [EBX+4], EAX")
        # 0x89 ModRM: mod=01, reg=EAX(0), rm=EBX(3) -> 01_000_011 = 0x43
        self.assertEqual(result, [0x89, 0x43, 0x04])

    # ── CALL rel32 ──────────────────────────────────────────────────

    def test_call_label(self):
        """CALL forward label."""
        program = """
            CALL func
            NOP
        func:
            MOV EAX, 42
        """
        result = self.asm.assemble(program)
        # CALL at PC=0, 5 bytes long. Target 'func' at PC=6. rel32 = 6 - 5 = 1
        self.assertEqual(result[0], 0xE8)
        self.assertEqual(result[1], 0x01)
        self.assertEqual(result[2], 0x00)
        self.assertEqual(result[3], 0x00)
        self.assertEqual(result[4], 0x00)

    # ── Variable-length PC tracking ─────────────────────────────────

    def test_variable_length_program(self):
        """Test correct byte output for mixed-size instructions."""
        program = """
            MOV EAX, 1
            NOP
            ADD EAX, 2
        """
        expected = [
            0xB8, 0x01, 0x00, 0x00, 0x00,  # MOV EAX, 1 (5 bytes)
            0x90,                            # NOP (1 byte)
            0x83, 0xC0, 0x02,               # ADD EAX, 2 (3 bytes)
        ]
        result = self.asm.assemble(program)
        self.assertEqual(result, expected)

    # ── Dispatch ────────────────────────────────────────────────────

    def test_dispatch(self):
        result = assemble("x86", "NOP")
        self.assertEqual(result, [0x90])

    # ── Error handling ──────────────────────────────────────────────

    def test_unknown_mnemonic(self):
        with self.assertRaises(AssemblerError):
            self.asm.assemble("BOGUS EAX, ECX")

    def test_bad_register(self):
        with self.assertRaises(AssemblerError):
            self.asm.assemble("MOV R0, 5")

    # ── AND/OR/XOR with imm8 ───────────────────────────────────────

    def test_and_imm8(self):
        result = self.asm.assemble("AND EAX, 0x0F")
        # 0x83, ModRM(mod=11, /4, rm=EAX=0), imm8=0x0F
        self.assertEqual(result, [0x83, 0xE0, 0x0F])

    def test_or_imm8(self):
        result = self.asm.assemble("OR EAX, 0x0F")
        # 0x83, ModRM(mod=11, /1, rm=EAX=0), imm8=0x0F
        self.assertEqual(result, [0x83, 0xC8, 0x0F])

    def test_xor_imm8(self):
        # imm8 is sign-extended by the decoder, so the 0xFF byte is written via
        # the signed value -1 (XOR EAX, -1 == XOR with 0xFFFFFFFF).
        result = self.asm.assemble("XOR EAX, -1")
        # 0x83, ModRM(mod=11, /6, rm=EAX=0), imm8=0xFF
        self.assertEqual(result, [0x83, 0xF0, 0xFF])


# ════════════════════════════════════════════════════════════════════
#  Cheatsheet
# ════════════════════════════════════════════════════════════════════

class TestCheatsheet(unittest.TestCase):
    def test_riscv_cheatsheet(self):
        cs = get_cheatsheet("riscv")
        self.assertIsInstance(cs, list)
        self.assertTrue(len(cs) > 10)
        # Check structure
        for entry in cs:
            self.assertIn("category", entry)
            self.assertIn("mnemonic", entry)
            self.assertIn("syntax", entry)
            self.assertIn("description", entry)
            self.assertIn("example", entry)

    def test_arm_cheatsheet(self):
        cs = get_cheatsheet("arm")
        self.assertIsInstance(cs, list)
        self.assertTrue(len(cs) > 10)

    def test_x86_cheatsheet(self):
        cs = get_cheatsheet("x86")
        self.assertIsInstance(cs, list)
        self.assertTrue(len(cs) > 10)

    def test_unknown_isa(self):
        with self.assertRaises(ValueError):
            get_cheatsheet("mips")


# ════════════════════════════════════════════════════════════════════
#  Dispatch function
# ════════════════════════════════════════════════════════════════════

class TestDispatch(unittest.TestCase):
    def test_unknown_isa(self):
        with self.assertRaises(ValueError):
            assemble("mips", "ADD x1, x2, x3")

    def test_case_insensitive(self):
        result = assemble("RISCV", "ADDI x1, x0, 5")
        self.assertEqual(result, [0x00500093])


# ════════════════════════════════════════════════════════════════════
#  x86 branch relaxation (rel8 -> rel32 auto-widening for label jumps)
# ════════════════════════════════════════════════════════════════════

class TestX86BranchRelaxation(unittest.TestCase):
    """Label jumps start rel8 and only widen to rel32 (JMP: E9+imm32,
    Jcc: 0F 8x+imm32) when the displacement doesn't fit — so short-jump
    encodings (and every existing program) are byte-identical, while long
    spans that used to raise 'out of range for an 8-bit field' now assemble.
    Numeric displacements (e.g. 'JE +1') always stay rel8: they are explicit
    byte offsets, not layout-dependent labels."""

    def test_short_label_jumps_stay_rel8(self):
        prog = assemble("x86", "JMP skip\nNOP\nskip:\nNOP\n")
        self.assertEqual(prog[:3], [0xEB, 0x01, 0x90])
        prog = assemble("x86", "CMP EAX, 0\nJE skip\nNOP\nskip:\nNOP\n")
        self.assertEqual(prog[3], 0x74)  # JE rel8

    def test_long_forward_jmp_widens_to_rel32(self):
        text = "JMP far\n" + "MOV EAX, 1\n" * 40 + "far:\nNOP\n"
        prog = assemble("x86", text)
        # 40 x 5-byte MOVs = 200 bytes > 127: JMP must be E9 + disp32(200).
        self.assertEqual(prog[0], 0xE9)
        disp = prog[1] | (prog[2] << 8) | (prog[3] << 16) | (prog[4] << 24)
        self.assertEqual(disp, 200)

    def test_long_backward_jcc_widens_to_rel32(self):
        text = ("loop:\n" + "MOV EAX, 1\n" * 40 +
                "CMP EAX, 0\nJNE loop\nNOP\n")
        prog = assemble("x86", text)
        # JNE rel32 = 0F 85 (0x75 + 0x10) somewhere near the end.
        self.assertIn(0x0F, prog)
        idx = len(prog) - 1 - 6  # trailing NOP, then the 6-byte Jcc
        self.assertEqual(prog[idx:idx + 2], [0x0F, 0x85])
        disp = (prog[idx + 2] | (prog[idx + 3] << 8) |
                (prog[idx + 4] << 16) | (prog[idx + 5] << 24))
        self.assertEqual(disp - (1 << 32), -(idx + 6))  # back to byte 0

    def test_numeric_displacement_never_widens(self):
        # Explicit byte offsets encode rel8 even when large-ish values are
        # given; out-of-range numerics still raise (user error, not layout).
        prog = assemble("x86", "JMP +4\nNOP\nNOP\n")
        self.assertEqual(prog[0], 0xEB)
        with self.assertRaises(AssemblerError):
            assemble("x86", "JMP +300\n")

    def test_widened_program_executes_correctly(self):
        from sim.harness import simulate
        text = ("MOV EAX, 1\nJMP far\n" + "ADD EAX, 1\n" * 60 +
                "far:\nMOV EBX, 42\nNOP\n")
        for model in ("single_cycle", "pipeline", "multicycle"):
            r = simulate("x86", model, asm=text, cycles=400)
            self.assertEqual(r.reg("EAX"), 1, model)   # ADDs skipped
            self.assertEqual(r.reg("EBX"), 42, model)

    def test_large_imm32_survives_pipeline_latch(self):
        # Regression: IF/ID + the multicycle IR latch were 32-bit and silently
        # truncated 5-6 byte instructions; high imm32 bytes vanished.
        from sim.harness import simulate
        for model in ("single_cycle", "pipeline", "multicycle"):
            r = simulate("x86", model, asm="MOV EAX, 0x7F000001\nNOP\n", cycles=60)
            self.assertEqual(r.reg("EAX"), 0x7F000001, model)


if __name__ == "__main__":
    unittest.main()
