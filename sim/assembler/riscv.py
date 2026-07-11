"""
RISC-V RV32I assembler.

Produces 32-bit instruction words that match the existing RISCVDecoder.
Supports both numeric (x0-x31) and ABI register names (zero, ra, sp, ...).
"""
import re
from .base import AssemblerBase, AssemblerError


# ── Register name → index lookup ────────────────────────────────────
_ABI_NAMES = {
    "zero": 0,  "ra": 1,   "sp": 2,   "gp": 3,   "tp": 4,
    "t0": 5,    "t1": 6,   "t2": 7,
    "s0": 8,    "fp": 8,   "s1": 9,
    "a0": 10,   "a1": 11,  "a2": 12,  "a3": 13,
    "a4": 14,   "a5": 15,  "a6": 16,  "a7": 17,
    "s2": 18,   "s3": 19,  "s4": 20,  "s5": 21,
    "s6": 22,   "s7": 23,  "s8": 24,  "s9": 25,
    "s10": 26,  "s11": 27,
    "t3": 28,   "t4": 29,  "t5": 30,  "t6": 31,
}


def _parse_reg(token: str) -> int:
    """Parse a register token: x0-x31 or ABI name."""
    t = token.strip().lower()
    if t.startswith('x'):
        try:
            n = int(t[1:])
        except ValueError:
            raise AssemblerError(f"Invalid register '{token}'")
        if 0 <= n <= 31:
            return n
        raise AssemblerError(f"Register index out of range: '{token}'")
    if t in _ABI_NAMES:
        return _ABI_NAMES[t]
    raise AssemblerError(f"Unknown register '{token}'")


# ── Opcode constants (matching sim.isa.riscv.constants) ─────────────
_OP_R_TYPE  = 0b0110011
_OP_I_ALU   = 0b0010011
_OP_LOAD    = 0b0000011
_OP_STORE   = 0b0100011
_OP_BRANCH  = 0b1100011
_OP_JAL     = 0b1101111
_OP_JALR    = 0b1100111
_OP_LUI     = 0b0110111
_OP_AUIPC   = 0b0010111

_F7_NORMAL = 0b0000000
_F7_ALT    = 0b0100000


class RISCVAssembler(AssemblerBase):
    """RISC-V RV32I two-pass assembler."""

    def _pc_increment(self) -> int:
        return 4

    def _encode(self, mnemonic: str, operands: list[str], pc: int, labels: dict) -> int:
        mn = mnemonic.upper()

        # ── R-type ──────────────────────────────────────────────────
        if mn in ('ADD', 'SUB', 'AND', 'OR', 'XOR', 'SLT', 'SLTU',
                  'SLL', 'SRL', 'SRA'):
            return self._encode_r(mn, operands)

        # ── I-type ALU ──────────────────────────────────────────────
        if mn in ('ADDI', 'ANDI', 'ORI', 'XORI', 'SLTI', 'SLTIU',
                  'SLLI', 'SRLI', 'SRAI'):
            return self._encode_i_alu(mn, operands)

        # ── Load ────────────────────────────────────────────────────
        if mn == 'LW':
            return self._encode_load(operands)

        # ── Store ───────────────────────────────────────────────────
        if mn == 'SW':
            return self._encode_store(operands)

        # ── Branch ──────────────────────────────────────────────────
        if mn in ('BEQ', 'BNE', 'BLT', 'BGE', 'BLTU', 'BGEU'):
            return self._encode_branch(mn, operands, pc, labels)

        # ── JAL ─────────────────────────────────────────────────────
        if mn == 'JAL':
            return self._encode_jal(operands, pc, labels)

        # ── JALR ────────────────────────────────────────────────────
        if mn == 'JALR':
            return self._encode_jalr(operands)

        # ── LUI ─────────────────────────────────────────────────────
        if mn == 'LUI':
            return self._encode_lui(operands)

        # ── AUIPC ───────────────────────────────────────────────────
        if mn == 'AUIPC':
            return self._encode_auipc(operands)

        # ── NOP (pseudo) ────────────────────────────────────────────
        if mn == 'NOP':
            # NOP = ADDI x0, x0, 0
            return self._encode_i_alu('ADDI', ['x0', 'x0', '0'])

        raise AssemblerError(f"Unknown RISC-V mnemonic '{mnemonic}'")

    # ── R-type: funct7[31:25] | rs2[24:20] | rs1[19:15] | funct3[14:12] | rd[11:7] | opcode[6:0]
    def _encode_r(self, mn: str, ops: list[str]) -> int:
        if len(ops) != 3:
            raise AssemblerError(f"{mn} requires 3 operands, got {len(ops)}")
        rd  = _parse_reg(ops[0])
        rs1 = _parse_reg(ops[1])
        rs2 = _parse_reg(ops[2])

        funct3, funct7 = {
            'ADD':  (0b000, _F7_NORMAL),
            'SUB':  (0b000, _F7_ALT),
            'SLL':  (0b001, _F7_NORMAL),
            'SLT':  (0b010, _F7_NORMAL),
            'SLTU': (0b011, _F7_NORMAL),
            'XOR':  (0b100, _F7_NORMAL),
            'SRL':  (0b101, _F7_NORMAL),
            'SRA':  (0b101, _F7_ALT),
            'OR':   (0b110, _F7_NORMAL),
            'AND':  (0b111, _F7_NORMAL),
        }[mn]

        return (
            (funct7 << 25) | (rs2 << 20) | (rs1 << 15) |
            (funct3 << 12) | (rd << 7)   | _OP_R_TYPE
        )

    # ── I-type ALU: imm[31:20] | rs1[19:15] | funct3[14:12] | rd[11:7] | opcode[6:0]
    def _encode_i_alu(self, mn: str, ops: list[str]) -> int:
        if len(ops) != 3:
            raise AssemblerError(f"{mn} requires 3 operands, got {len(ops)}")
        rd  = _parse_reg(ops[0])
        rs1 = _parse_reg(ops[1])
        imm = self._parse_immediate(ops[2])

        funct3_map = {
            'ADDI':  0b000,
            'SLTI':  0b010,
            'SLTIU': 0b011,
            'XORI':  0b100,
            'ORI':   0b110,
            'ANDI':  0b111,
            'SLLI':  0b001,
            'SRLI':  0b101,
            'SRAI':  0b101,
        }
        funct3 = funct3_map[mn]

        if mn == 'SLLI':
            # shamt in bits [24:20], funct7=0000000
            self._require_unsigned(imm, 5, "shift amount")
            shamt = imm & 0x1F
            imm12 = (_F7_NORMAL << 5) | shamt
        elif mn == 'SRLI':
            self._require_unsigned(imm, 5, "shift amount")
            shamt = imm & 0x1F
            imm12 = (_F7_NORMAL << 5) | shamt
        elif mn == 'SRAI':
            self._require_unsigned(imm, 5, "shift amount")
            shamt = imm & 0x1F
            imm12 = (_F7_ALT << 5) | shamt
        else:
            self._require_signed(imm, 12, f"{mn} immediate")
            imm12 = self._mask(imm, 12)

        return (
            (imm12 << 20) | (rs1 << 15) |
            (funct3 << 12) | (rd << 7) | _OP_I_ALU
        )

    # ── Load: LW rd, offset(rs1)
    def _encode_load(self, ops: list[str]) -> int:
        rd, offset, rs1 = self._parse_mem_operand(ops)
        self._require_signed(offset, 12, "load offset")
        imm12 = self._mask(offset, 12)
        funct3 = 0b010  # WORD
        return (
            (imm12 << 20) | (rs1 << 15) |
            (funct3 << 12) | (rd << 7) | _OP_LOAD
        )

    # ── Store: SW rs2, offset(rs1)
    def _encode_store(self, ops: list[str]) -> int:
        rs2_idx, offset, rs1 = self._parse_mem_operand(ops)
        self._require_signed(offset, 12, "store offset")
        imm = self._mask(offset, 12)
        imm_4_0  = imm & 0x1F
        imm_11_5 = (imm >> 5) & 0x7F
        funct3 = 0b010  # WORD
        return (
            (imm_11_5 << 25) | (rs2_idx << 20) | (rs1 << 15) |
            (funct3 << 12) | (imm_4_0 << 7) | _OP_STORE
        )

    # ── Branch: B-type immediate encoding
    def _encode_branch(self, mn: str, ops: list[str], pc: int, labels: dict) -> int:
        if len(ops) != 3:
            raise AssemblerError(f"{mn} requires 3 operands, got {len(ops)}")
        rs1 = _parse_reg(ops[0])
        rs2 = _parse_reg(ops[1])
        offset = self._resolve_label_or_imm(ops[2], pc, labels)

        funct3_map = {
            'BEQ':  0b000,
            'BNE':  0b001,
            'BLT':  0b100,
            'BGE':  0b101,
            'BLTU': 0b110,
            'BGEU': 0b111,
        }
        funct3 = funct3_map[mn]

        # B-type immediate: imm[12|10:5|4:1|11]
        self._require_signed(offset, 13, f"{mn} branch offset")
        self._require_aligned(offset, 2, f"{mn} branch offset")
        imm = self._mask(offset, 13)
        bit_12  = (imm >> 12) & 1
        bit_11  = (imm >> 11) & 1
        bit_10_5 = (imm >> 5) & 0x3F
        bit_4_1  = (imm >> 1) & 0xF

        return (
            (bit_12 << 31) | (bit_10_5 << 25) | (rs2 << 20) | (rs1 << 15) |
            (funct3 << 12) | (bit_4_1 << 8) | (bit_11 << 7) | _OP_BRANCH
        )

    # ── JAL: J-type immediate encoding
    def _encode_jal(self, ops: list[str], pc: int, labels: dict) -> int:
        if len(ops) != 2:
            raise AssemblerError(f"JAL requires 2 operands, got {len(ops)}")
        rd = _parse_reg(ops[0])
        offset = self._resolve_label_or_imm(ops[1], pc, labels)

        # J-type: imm[20|10:1|11|19:12]
        self._require_signed(offset, 21, "JAL offset")
        self._require_aligned(offset, 2, "JAL offset")
        imm = self._mask(offset, 21)
        bit_20    = (imm >> 20) & 1
        bit_10_1  = (imm >> 1) & 0x3FF
        bit_11    = (imm >> 11) & 1
        bit_19_12 = (imm >> 12) & 0xFF

        return (
            (bit_20 << 31) | (bit_10_1 << 21) | (bit_11 << 20) |
            (bit_19_12 << 12) | (rd << 7) | _OP_JAL
        )

    # ── JALR: I-type
    def _encode_jalr(self, ops: list[str]) -> int:
        if len(ops) != 3:
            raise AssemblerError(f"JALR requires 3 operands, got {len(ops)}")
        rd  = _parse_reg(ops[0])
        rs1 = _parse_reg(ops[1])
        imm = self._parse_immediate(ops[2])
        self._require_signed(imm, 12, "JALR offset")
        imm12 = self._mask(imm, 12)
        funct3 = 0b000
        return (
            (imm12 << 20) | (rs1 << 15) |
            (funct3 << 12) | (rd << 7) | _OP_JALR
        )

    # ── LUI: U-type
    def _encode_lui(self, ops: list[str]) -> int:
        if len(ops) != 2:
            raise AssemblerError(f"LUI requires 2 operands, got {len(ops)}")
        rd  = _parse_reg(ops[0])
        imm = self._parse_immediate(ops[1])
        # imm is the upper 20-bit value (not shifted yet for the user)
        # LUI encoding: imm[31:12] | rd[11:7] | opcode[6:0]
        imm20 = self._mask(imm, 20)
        return (imm20 << 12) | (rd << 7) | _OP_LUI

    # ── AUIPC: U-type
    def _encode_auipc(self, ops: list[str]) -> int:
        if len(ops) != 2:
            raise AssemblerError(f"AUIPC requires 2 operands, got {len(ops)}")
        rd  = _parse_reg(ops[0])
        imm = self._parse_immediate(ops[1])
        imm20 = self._mask(imm, 20)
        return (imm20 << 12) | (rd << 7) | _OP_AUIPC

    # ── Memory operand parser: "rd, offset(rs1)" or ["rd", "offset(rs1)"]
    def _parse_mem_operand(self, ops: list[str]) -> tuple[int, int, int]:
        """Parse load/store operands: 'rd, offset(rs1)'.

        Returns (reg_index, offset_int, base_reg_index).
        """
        if len(ops) == 2:
            reg = _parse_reg(ops[0])
            m = re.match(r'(-?\w+)\((\w+)\)', ops[1])
            if not m:
                raise AssemblerError(
                    f"Invalid memory operand: '{ops[1]}'. Expected 'offset(reg)'"
                )
            offset = self._parse_immediate(m.group(1))
            base = _parse_reg(m.group(2))
            return reg, offset, base
        elif len(ops) == 3:
            # Some assemblers split "0(x0)" into separate tokens after comma handling;
            # try the common case of ops[1] containing the offset(base)
            reg = _parse_reg(ops[0])
            combined = ops[1] + ops[2] if '(' in ops[1] else ops[1] + '(' + ops[2]
            m = re.match(r'(-?\w+)\((\w+)\)', combined)
            if not m:
                raise AssemblerError(
                    f"Invalid memory operand: '{' '.join(ops[1:])}'"
                )
            offset = self._parse_immediate(m.group(1))
            base = _parse_reg(m.group(2))
            return reg, offset, base
        else:
            raise AssemblerError(
                f"Load/store requires 2 operands: reg, offset(base). Got {len(ops)}"
            )

    def _split_instruction(self, line: str) -> list[str]:
        """Override to handle offset(base) syntax without splitting inside parens."""
        # First, find the mnemonic
        parts = line.split(None, 1)
        if len(parts) == 1:
            return [parts[0]]
        mnemonic = parts[0]
        rest = parts[1]

        # Split on commas, but preserve offset(reg) as a single token
        tokens = [t.strip() for t in rest.split(',')]
        return [mnemonic] + [t for t in tokens if t]
