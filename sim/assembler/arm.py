"""
ARM AArch64 (A64) assembler.

Produces 32-bit instruction words that match the existing ARMDecoder.
Supports X0-X30, XZR register names and all instructions in the decoder subset.
"""
import re
from .base import AssemblerBase, AssemblerError


# ── Register name → index lookup ────────────────────────────────────
def _parse_reg(token: str) -> int:
    """Parse an ARM register: X0-X30, XZR, SP."""
    t = token.strip().upper()
    if t == 'XZR':
        return 31
    if t == 'SP':
        # In our simulator, SP is not a separate register; treat as X31 alias
        # but for stack-pointer contexts this is acceptable
        return 31
    if t.startswith('X'):
        try:
            n = int(t[1:])
        except ValueError:
            raise AssemblerError(f"Invalid register '{token}'")
        if 0 <= n <= 30:
            return n
        raise AssemblerError(f"Register index out of range: '{token}'")
    raise AssemblerError(f"Unknown ARM register '{token}'")


# ── Condition codes ─────────────────────────────────────────────────
_COND_MAP = {
    'EQ': 0x0,
    'NE': 0x1,
    'HS': 0x2, 'CS': 0x2,
    'LO': 0x3, 'CC': 0x3,
    'MI': 0x4,
    'PL': 0x5,
    'HI': 0x8,
    'LS': 0x9,
    'GE': 0xA,
    'LT': 0xB,
    'GT': 0xC,
    'LE': 0xD,
}

# Conditions the simulator's branch unit / decoder actually resolves. The
# others (unsigned HS/LO/HI/LS and N-flag MI/PL) would decode to "never taken",
# so reject them at assemble time rather than silently never branching.
_BCOND_SUPPORTED = {'EQ', 'NE', 'LT', 'GE', 'GT', 'LE'}


class ARMAssembler(AssemblerBase):
    """ARM AArch64 two-pass assembler."""

    def _preprocess(self, text: str) -> list[tuple[int, str]]:
        """Override: ARM uses # for immediates, so only ; and // are comments."""
        import re
        result = []
        for lineno, raw in enumerate(text.splitlines(), start=1):
            line = re.split(r';|//', raw)[0]
            line = line.strip()
            if line:
                result.append((lineno, line))
        return result

    def _pc_increment(self) -> int:
        return 4

    def _split_instruction(self, line: str) -> list[str]:
        """Split ARM instruction, handling [Xn, #imm] addressing mode."""
        parts = line.split(None, 1)
        if len(parts) == 1:
            return [parts[0]]
        mnemonic = parts[0]
        rest = parts[1]

        # Handle memory operand [Xn, #offset] -- keep brackets content together
        # We'll parse it specially in the encoder, but need to tokenize carefully
        tokens = []
        i = 0
        current = ''
        while i < len(rest):
            ch = rest[i]
            if ch == '[':
                # Read until matching ]
                j = rest.index(']', i)
                tokens.append(current.strip().rstrip(','))
                tokens.append(rest[i:j+1].strip())
                current = ''
                i = j + 1
                # skip trailing comma
                while i < len(rest) and rest[i] in (' ', ','):
                    i += 1
                continue
            elif ch == ',':
                t = current.strip()
                if t:
                    tokens.append(t)
                current = ''
            else:
                current += ch
            i += 1
        t = current.strip()
        if t:
            tokens.append(t)

        # Filter empty tokens
        tokens = [t for t in tokens if t]
        return [mnemonic] + tokens

    def _encode(self, mnemonic: str, operands: list[str], pc: int, labels: dict) -> int:
        mn = mnemonic.upper()

        # ── NOP ─────────────────────────────────────────────────────
        if mn == 'NOP':
            return 0xD503201F

        # ── RET ─────────────────────────────────────────────────────
        if mn == 'RET':
            rn = 30  # default X30
            if operands:
                rn = _parse_reg(operands[0])
            # 1101011_0010_11111_0000_00_Rn[9:5]_00000
            return (0b1101011_0010_11111_0000_00 << 10) | (rn << 5) | 0b00000

        # ── B.cond ──────────────────────────────────────────────────
        if mn.startswith('B.'):
            cond_str = mn[2:]
            return self._encode_bcond(cond_str, operands, pc, labels)

        # ── B (unconditional) ───────────────────────────────────────
        if mn == 'B':
            return self._encode_b(operands, pc, labels)

        # ── BL (branch with link) ──────────────────────────────────
        if mn == 'BL':
            return self._encode_bl(operands, pc, labels)

        # ── CBZ / CBNZ ─────────────────────────────────────────────
        if mn in ('CBZ', 'CBNZ'):
            return self._encode_cbz_cbnz(mn, operands, pc, labels)

        # ── CMP (alias for SUBS XZR, Rn, Rm) ───────────────────────
        if mn == 'CMP':
            return self._encode_dp_reg_arith('SUBS', ['XZR'] + operands)

        # ── SUBS ────────────────────────────────────────────────────
        if mn == 'SUBS':
            return self._encode_dp_reg_arith(mn, operands)

        # ── ADD / SUB (register or immediate) ───────────────────────
        if mn in ('ADD', 'SUB'):
            # Check if third operand is immediate (starts with #)
            if len(operands) == 3 and operands[2].strip().startswith('#'):
                return self._encode_dp_imm_addsub(mn, operands)
            else:
                return self._encode_dp_reg_arith(mn, operands)

        # ── AND / ORR / EOR ─────────────────────────────────────────
        if mn in ('AND', 'ORR', 'EOR'):
            return self._encode_dp_reg_logical(mn, operands)

        # ── MOVZ / MOV ──────────────────────────────────────────────
        if mn in ('MOVZ', 'MOV'):
            return self._encode_movz(operands)

        # ── LDR / STR ──────────────────────────────────────────────
        if mn in ('LDR', 'STR'):
            return self._encode_ldst(mn, operands)

        raise AssemblerError(f"Unknown ARM mnemonic '{mnemonic}'")

    # ── Data Processing Register (arithmetic): ADD, SUB, SUBS ───────
    def _encode_dp_reg_arith(self, mn: str, ops: list[str]) -> int:
        if len(ops) != 3:
            raise AssemblerError(f"{mn} requires 3 register operands, got {len(ops)}")
        rd = _parse_reg(ops[0])
        rn = _parse_reg(ops[1])
        rm = _parse_reg(ops[2])

        opc_map = {'ADD': 0b00, 'SUB': 0b10, 'SUBS': 0b11}
        opc = opc_map[mn]

        # sf=1 | opc[30:29] | 01011 | shift=00 | 0 | Rm | imm6=000000 | Rn | Rd
        return (
            (1 << 31) | (opc << 29) | (0b01011 << 24) |
            (0 << 22) | (0 << 21) | (rm << 16) |
            (0 << 10) | (rn << 5) | rd
        )

    # ── Data Processing Register (logical): AND, ORR, EOR ──────────
    def _encode_dp_reg_logical(self, mn: str, ops: list[str]) -> int:
        if len(ops) != 3:
            raise AssemblerError(f"{mn} requires 3 register operands, got {len(ops)}")
        rd = _parse_reg(ops[0])
        rn = _parse_reg(ops[1])
        rm = _parse_reg(ops[2])

        opc_map = {'AND': 0b00, 'ORR': 0b01, 'EOR': 0b10}
        opc = opc_map[mn]

        # sf=1 | opc[30:29] | 01010 | shift=00 | 0 | Rm | imm6=000000 | Rn | Rd
        return (
            (1 << 31) | (opc << 29) | (0b01010 << 24) |
            (0 << 22) | (0 << 21) | (rm << 16) |
            (0 << 10) | (rn << 5) | rd
        )

    # ── Data Processing Immediate (ADD/SUB) ─────────────────────────
    def _encode_dp_imm_addsub(self, mn: str, ops: list[str]) -> int:
        if len(ops) != 3:
            raise AssemblerError(f"{mn} imm requires 3 operands, got {len(ops)}")
        rd = _parse_reg(ops[0])
        rn = _parse_reg(ops[1])
        imm12 = self._parse_immediate(ops[2])

        opc_map = {'ADD': 0b00, 'SUB': 0b10}
        opc = opc_map[mn]

        if imm12 < 0:
            other = 'SUB' if mn == 'ADD' else 'ADD'
            raise AssemblerError(
                f"{mn} immediate {imm12} must be non-negative (use {other} for negatives)")

        # Check for shift
        sh = 0
        if imm12 > 0xFFF:
            # Could be shifted by 12
            if (imm12 & 0xFFF) == 0 and (imm12 >> 12) <= 0xFFF:
                sh = 1
                imm12 = imm12 >> 12
            else:
                raise AssemblerError(f"Immediate {imm12} too large for ADD/SUB immediate")

        # sf=1 | opc[30:29] | 100010 | sh | imm12[21:10] | Rn[9:5] | Rd[4:0]
        return (
            (1 << 31) | (opc << 29) | (0b100010 << 23) |
            (sh << 22) | ((imm12 & 0xFFF) << 10) | (rn << 5) | rd
        )

    # ── MOVZ ────────────────────────────────────────────────────────
    def _encode_movz(self, ops: list[str]) -> int:
        if len(ops) != 2:
            raise AssemblerError(f"MOVZ requires 2 operands, got {len(ops)}")
        rd = _parse_reg(ops[0])
        imm16 = self._parse_immediate(ops[1])

        if imm16 < 0:
            raise AssemblerError(f"MOVZ immediate {imm16} must be non-negative")

        # Determine hw (half-word shift)
        hw = 0
        val = imm16
        if val > 0xFFFF:
            if (val & 0xFFFF) == 0 and ((val >> 16) & 0xFFFF) <= 0xFFFF:
                hw = 1
                imm16 = (val >> 16) & 0xFFFF
            else:
                raise AssemblerError(f"MOVZ immediate too large: {val}")
        else:
            imm16 = val & 0xFFFF

        # sf=1 | opc=10 | 100101 | hw[22:21] | imm16[20:5] | Rd[4:0]
        return (
            (1 << 31) | (0b10 << 29) | (0b100101 << 23) |
            (hw << 21) | (imm16 << 5) | rd
        )

    # ── Load/Store unsigned offset ──────────────────────────────────
    def _encode_ldst(self, mn: str, ops: list[str]) -> int:
        if len(ops) < 2:
            raise AssemblerError(f"{mn} requires at least 2 operands")
        rt = _parse_reg(ops[0])

        # Parse [Xn, #offset] or [Xn]
        mem_op = ops[1]
        if not mem_op.startswith('['):
            raise AssemblerError(f"Expected memory operand in brackets: '{mem_op}'")

        inner = mem_op.strip('[]').strip()
        parts = [p.strip() for p in inner.split(',')]
        rn = _parse_reg(parts[0])
        offset = 0
        if len(parts) > 1:
            offset = self._parse_immediate(parts[1])

        # Scale: size=11 (64-bit), scale = 8
        # imm12 = offset / 8
        scale = 8
        if offset % scale != 0:
            raise AssemblerError(
                f"Offset {offset} must be a multiple of {scale} for 64-bit LDR/STR"
            )
        # The scaled unsigned-offset LDR/STR form cannot encode a negative
        # offset (that needs LDUR) and the imm12 field is 12-bit unsigned.
        if offset < 0:
            raise AssemblerError(
                "LDR/STR scaled offset must be non-negative (use LDUR for negative offsets)")
        imm12 = offset // scale
        self._require_unsigned(imm12, 12, "LDR/STR scaled offset")

        opc = 0b01 if mn == 'LDR' else 0b00  # load=01, store=00

        # size[31:30]=11 | 111 | V=0 | 01 | opc[23:22] | imm12[21:10] | Rn[9:5] | Rt[4:0]
        return (
            (0b11 << 30) | (0b111 << 27) | (0 << 26) | (0b01 << 24) |
            (opc << 22) | (imm12 << 10) | (rn << 5) | rt
        )

    # ── B (unconditional) ───────────────────────────────────────────
    def _encode_b(self, ops: list[str], pc: int, labels: dict) -> int:
        if len(ops) != 1:
            raise AssemblerError(f"B requires 1 operand, got {len(ops)}")
        offset = self._resolve_label_or_imm(ops[0], pc, labels)

        # Offset is in bytes, imm26 = offset / 4
        if offset % 4 != 0:
            raise AssemblerError(f"Branch offset {offset} must be a multiple of 4")
        imm26 = self._mask(offset >> 2, 26)

        # 000101 | imm26
        return (0b000101 << 26) | imm26

    # ── BL (branch with link) ──────────────────────────────────────
    def _encode_bl(self, ops: list[str], pc: int, labels: dict) -> int:
        if len(ops) != 1:
            raise AssemblerError(f"BL requires 1 operand, got {len(ops)}")
        offset = self._resolve_label_or_imm(ops[0], pc, labels)

        if offset % 4 != 0:
            raise AssemblerError(f"Branch offset {offset} must be a multiple of 4")
        imm26 = self._mask(offset >> 2, 26)

        # 100101 | imm26
        return (0b100101 << 26) | imm26

    # ── B.cond ──────────────────────────────────────────────────────
    def _encode_bcond(self, cond_str: str, ops: list[str], pc: int, labels: dict) -> int:
        if len(ops) != 1:
            raise AssemblerError(f"B.{cond_str} requires 1 operand, got {len(ops)}")

        cond_str = cond_str.upper()
        if cond_str not in _COND_MAP:
            raise AssemblerError(f"Unknown condition code '{cond_str}'")
        if cond_str not in _BCOND_SUPPORTED:
            raise AssemblerError(
                f"B.{cond_str} is not supported by the simulator's branch unit "
                f"(supported conditions: EQ, NE, LT, GE, GT, LE)")
        cond = _COND_MAP[cond_str]

        offset = self._resolve_label_or_imm(ops[0], pc, labels)
        if offset % 4 != 0:
            raise AssemblerError(f"Branch offset {offset} must be a multiple of 4")
        imm19 = self._mask(offset >> 2, 19)

        # 01010100 | imm19[23:5] | 0 | cond[3:0]
        return (0b01010100 << 24) | (imm19 << 5) | (0 << 4) | cond

    # ── CBZ / CBNZ ─────────────────────────────────────────────────
    def _encode_cbz_cbnz(self, mn: str, ops: list[str], pc: int, labels: dict) -> int:
        if len(ops) != 2:
            raise AssemblerError(f"{mn} requires 2 operands, got {len(ops)}")
        rt = _parse_reg(ops[0])
        offset = self._resolve_label_or_imm(ops[1], pc, labels)

        if offset % 4 != 0:
            raise AssemblerError(f"Branch offset {offset} must be a multiple of 4")
        imm19 = self._mask(offset >> 2, 19)

        op = 0 if mn == 'CBZ' else 1

        # sf=1 | 011010 | op | imm19[23:5] | Rt[4:0]
        return (
            (1 << 31) | (0b011010 << 25) | (op << 24) |
            (imm19 << 5) | rt
        )
