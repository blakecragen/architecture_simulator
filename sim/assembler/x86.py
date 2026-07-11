"""
x86-32 (IA-32) assembler.

Produces a list of bytes (not words) that match the existing X86Decoder.
Uses Intel syntax (destination, source). Variable-length instructions.
"""
import re
from .base import AssemblerBase, AssemblerError


# ── Register name → index lookup ────────────────────────────────────
_REG_MAP = {
    'EAX': 0, 'ECX': 1, 'EDX': 2, 'EBX': 3,
    'ESP': 4, 'EBP': 5, 'ESI': 6, 'EDI': 7,
}


def _parse_reg(token: str) -> int:
    """Parse an x86-32 register name."""
    t = token.strip().upper()
    if t in _REG_MAP:
        return _REG_MAP[t]
    raise AssemblerError(f"Unknown x86 register '{token}'")


def _is_reg(token: str) -> bool:
    """Check if token is a register name."""
    return token.strip().upper() in _REG_MAP


def _is_mem(token: str) -> bool:
    """Check if token is a memory operand like [EBX] or [EBX+4]."""
    return '[' in token


def _modrm(mod: int, reg: int, rm: int) -> int:
    """Build a ModRM byte."""
    return ((mod & 3) << 6) | ((reg & 7) << 3) | (rm & 7)


def _imm32_bytes(value: int) -> list[int]:
    """Encode a 32-bit immediate as 4 little-endian bytes."""
    v = value & 0xFFFFFFFF
    return [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF]


def _imm8_byte(value: int) -> int:
    """Encode an 8-bit immediate / displacement / rel8.

    Every consumer (rel8 in JMP/Jcc, imm8 in the 0x83 Group-1 ALU, disp8 in MOV
    memory operands) is SIGN-EXTENDED by the decoder, so the meaningful range is
    signed [-128, 127]. Reject anything outside it instead of silently encoding
    a value that decodes to a different (negative) number — e.g. 200 would
    decode as -56, and a 300-byte jump would wrap to a small backward branch.
    """
    if not (-128 <= value <= 127):
        raise AssemblerError(
            f"value {value} out of range for an 8-bit sign-extended field "
            f"[-128..127] (disp8/imm8/rel8)")
    return value & 0xFF


# ── Opcode maps ─────────────────────────────────────────────────────
# ALU r/m32, r32 opcodes (src in reg field, dst in rm field)
_ALU_R32_OPCODES = {
    'ADD': 0x01,
    'OR':  0x09,
    'AND': 0x21,
    'SUB': 0x29,
    'XOR': 0x31,
    'CMP': 0x39,
}

# Group 1 /r extension for 0x83 ModRM imm8
_GRP1_EXT = {
    'ADD': 0,  # /0
    'OR':  1,  # /1
    'AND': 4,  # /4
    'SUB': 5,  # /5
    'XOR': 6,  # /6
    'CMP': 7,  # /7
}

# Jcc opcodes (rel8)
_JCC_OPCODES = {
    'JE':  0x74, 'JZ':  0x74,
    'JNE': 0x75, 'JNZ': 0x75,
    'JL':  0x7C, 'JNGE': 0x7C,
    'JGE': 0x7D, 'JNL': 0x7D,
    'JLE': 0x7E, 'JNG': 0x7E,
    'JG':  0x7F, 'JNLE': 0x7F,
}


class X86Assembler(AssemblerBase):
    """x86-32 two-pass assembler producing byte lists.

    Label jumps get BRANCH RELAXATION: every JMP/Jcc to a label starts as
    rel8 (2 bytes, the historical encoding); any jump whose displacement
    does not fit widens to rel32 (JMP: E9+imm32, 5 bytes; Jcc: 0F 8x+imm32,
    6 bytes) and STAYS wide, so the label layout re-converges (widening is
    monotonic). Numeric offsets (e.g. 'JE +1') always encode rel8 — they are
    explicit byte displacements, not layout-dependent.
    """

    def _pc_increment(self) -> int:
        # Not used for x86 (variable-length), but needed as fallback
        return 1

    # ── Branch relaxation ───────────────────────────────────────────
    def assemble(self, text: str) -> list[int]:
        lines = self._preprocess(text)
        self._wide_jumps = set()   # linenos widened to rel32 (sticky)
        while True:
            labels, cleaned = self._pass1(lines)
            changed = False
            for lineno, pc, line in cleaned:
                parts = self._split_instruction(line)
                mn = parts[0].upper() if parts else ""
                if mn != "JMP" and mn not in _JCC_OPCODES:
                    continue
                if lineno in self._wide_jumps or len(parts) < 2:
                    continue
                target = parts[1].strip()
                if target not in labels:
                    continue   # numeric displacement: stays rel8
                disp8 = (labels[target] - pc) - 2
                if not (-128 <= disp8 <= 127):
                    self._wide_jumps.add(lineno)
                    changed = True
            if not changed:
                break
        # _encode() keys wideness by final pc (unique per instruction).
        self._wide_pcs = {pc for (ln, pc, _line) in cleaned
                          if ln in self._wide_jumps}
        return self._pass2(cleaned, labels)

    def _estimate_instruction_size_at(self, lineno: int, line: str) -> int:
        if lineno in getattr(self, "_wide_jumps", ()):
            parts = self._split_instruction(line)
            return 5 if parts and parts[0].upper() == "JMP" else 6
        return self._estimate_instruction_size(line)

    def _estimate_instruction_size(self, line: str) -> int:
        """Estimate instruction byte length for pass-1 PC tracking.

        Uses the bracket-aware splitter (NOT a naive whitespace split) so a
        spaced memory operand like ``[EBX + 4]`` is seen as one token and sized
        as disp8 — otherwise pass-1 (2 bytes) disagrees with pass-2 (3 bytes)
        and every later branch label drifts.
        """
        parts = self._split_instruction(line)
        if not parts:
            return 0
        mn = parts[0].upper()

        # 1-byte instructions
        if mn in ('NOP', 'RET'):
            return 1
        if mn == 'PUSH' or mn == 'POP':
            return 1

        # 2-byte: JMP rel8, Jcc rel8
        if mn == 'JMP':
            return 2
        if mn in _JCC_OPCODES:
            return 2

        # 5-byte: CALL rel32
        if mn == 'CALL':
            return 5

        # MOV has multiple forms
        if mn == 'MOV':
            if len(parts) >= 3:
                dst = parts[1].strip().rstrip(',')
                src = parts[2].strip().rstrip(',')
                # MOV r, [r] or MOV [r], r = 2 bytes (mod=00)
                # MOV r, [r+disp8] or MOV [r+disp8], r = 3 bytes
                if _is_mem(dst) or _is_mem(src):
                    mem = dst if _is_mem(dst) else src
                    if '+' in mem or '-' in mem:
                        return 3  # mod=01 with disp8
                    return 2  # mod=00
                # MOV r, r = 2 bytes
                if _is_reg(dst) and _is_reg(src):
                    return 2
                # MOV r, imm32 = 5 bytes
                if _is_reg(dst):
                    return 5
            return 5  # default guess

        # ALU r32, r32 = 2 bytes; ALU r32, imm8 = 3 bytes
        if mn in _ALU_R32_OPCODES or mn in _GRP1_EXT:
            if len(parts) >= 3:
                src = parts[2].strip().rstrip(',')
                if _is_reg(src):
                    return 2
                else:
                    return 3  # imm8
            return 2

        return 2  # fallback

    def _split_instruction(self, line: str) -> list[str]:
        """Split x86 instruction, keeping memory operands like [EBX+4] intact."""
        parts = line.split(None, 1)
        if len(parts) == 1:
            return [parts[0]]
        mnemonic = parts[0]
        rest = parts[1]

        # Split on commas but keep [brackets] contents together
        tokens = []
        current = ''
        depth = 0
        for ch in rest:
            if ch == '[':
                depth += 1
                current += ch
            elif ch == ']':
                depth -= 1
                current += ch
            elif ch == ',' and depth == 0:
                t = current.strip()
                if t:
                    tokens.append(t)
                current = ''
            else:
                current += ch
        t = current.strip()
        if t:
            tokens.append(t)

        return [mnemonic] + tokens

    def _encode(self, mnemonic: str, operands: list[str], pc: int, labels: dict) -> list[int]:
        mn = mnemonic.upper()

        # ── NOP ─────────────────────────────────────────────────────
        if mn == 'NOP':
            return [0x90]

        # ── RET ─────────────────────────────────────────────────────
        if mn == 'RET':
            return [0xC3]

        # ── PUSH r32 ───────────────────────────────────────────────
        if mn == 'PUSH':
            if len(operands) != 1:
                raise AssemblerError(f"PUSH requires 1 operand, got {len(operands)}")
            r = _parse_reg(operands[0])
            return [0x50 + r]

        # ── POP r32 ────────────────────────────────────────────────
        if mn == 'POP':
            if len(operands) != 1:
                raise AssemblerError(f"POP requires 1 operand, got {len(operands)}")
            r = _parse_reg(operands[0])
            return [0x58 + r]

        # ── JMP rel8 / rel32 (relaxed) ─────────────────────────────
        if mn == 'JMP':
            if len(operands) != 1:
                raise AssemblerError(f"JMP requires 1 operand, got {len(operands)}")
            offset = self._resolve_label_or_imm(operands[0], pc, labels)
            if pc in getattr(self, '_wide_pcs', ()):
                # JMP rel32 (E9): displacement relative to NEXT instr (pc+5)
                return [0xE9] + _imm32_bytes(offset - 5)
            # JMP rel8: displacement is relative to NEXT instruction (pc+2)
            disp8 = offset - 2
            return [0xEB, _imm8_byte(disp8)]

        # ── Jcc rel8 / rel32 (relaxed) ─────────────────────────────
        if mn in _JCC_OPCODES:
            if len(operands) != 1:
                raise AssemblerError(f"{mn} requires 1 operand, got {len(operands)}")
            offset = self._resolve_label_or_imm(operands[0], pc, labels)
            if pc in getattr(self, '_wide_pcs', ()):
                # Jcc rel32 (0F 80+cc): displacement relative to pc+6
                return [0x0F, _JCC_OPCODES[mn] + 0x10] + _imm32_bytes(offset - 6)
            # Jcc rel8: displacement is relative to NEXT instruction (pc+2)
            disp8 = offset - 2
            return [_JCC_OPCODES[mn], _imm8_byte(disp8)]

        # ── CALL rel32 ─────────────────────────────────────────────
        if mn == 'CALL':
            if len(operands) != 1:
                raise AssemblerError(f"CALL requires 1 operand, got {len(operands)}")
            offset = self._resolve_label_or_imm(operands[0], pc, labels)
            # CALL rel32: displacement relative to NEXT instruction (pc+5)
            rel32 = offset - 5
            return [0xE8] + _imm32_bytes(rel32)

        # ── MOV ─────────────────────────────────────────────────────
        if mn == 'MOV':
            return self._encode_mov(operands, pc, labels)

        # ── ALU operations (ADD, SUB, AND, OR, XOR, CMP) ──────────
        if mn in _ALU_R32_OPCODES:
            return self._encode_alu(mn, operands)

        raise AssemblerError(f"Unknown x86 mnemonic '{mnemonic}'")

    # ── MOV encoding ────────────────────────────────────────────────
    def _encode_mov(self, ops: list[str], pc: int, labels: dict) -> list[int]:
        if len(ops) != 2:
            raise AssemblerError(f"MOV requires 2 operands, got {len(ops)}")
        dst, src = ops[0], ops[1]

        # MOV [r32], r32 or MOV [r32+disp8], r32
        if _is_mem(dst) and _is_reg(src):
            base, disp = self._parse_mem(dst)
            reg = _parse_reg(src)
            # A displacement *token* (even "+0") means disp8 form, matching
            # _estimate_instruction_size which sizes on the token's presence.
            if disp is not None:
                return [0x89, _modrm(0b01, reg, base), _imm8_byte(disp)]
            else:
                return [0x89, _modrm(0b00, reg, base)]

        # MOV r32, [r32] or MOV r32, [r32+disp8]
        if _is_reg(dst) and _is_mem(src):
            reg = _parse_reg(dst)
            base, disp = self._parse_mem(src)
            if disp is not None:
                return [0x8B, _modrm(0b01, reg, base), _imm8_byte(disp)]
            else:
                return [0x8B, _modrm(0b00, reg, base)]

        # MOV r32, r32
        if _is_reg(dst) and _is_reg(src):
            src_idx = _parse_reg(src)
            dst_idx = _parse_reg(dst)
            # 0x89: MOV r/m32, r32 → reg=src, rm=dst
            return [0x89, _modrm(0b11, src_idx, dst_idx)]

        # MOV r32, imm32
        if _is_reg(dst):
            r = _parse_reg(dst)
            imm = self._parse_immediate(src)
            return [0xB8 + r] + _imm32_bytes(imm)

        raise AssemblerError(f"Invalid MOV operands: {dst}, {src}")

    # ── ALU encoding ────────────────────────────────────────────────
    def _encode_alu(self, mn: str, ops: list[str]) -> list[int]:
        if len(ops) != 2:
            raise AssemblerError(f"{mn} requires 2 operands, got {len(ops)}")
        dst, src = ops[0], ops[1]

        # ALU r32, r32
        if _is_reg(dst) and _is_reg(src):
            opcode = _ALU_R32_OPCODES[mn]
            src_idx = _parse_reg(src)
            dst_idx = _parse_reg(dst)
            # opcode: r/m32, r32 → reg=src, rm=dst
            return [opcode, _modrm(0b11, src_idx, dst_idx)]

        # ALU r32, imm8
        if _is_reg(dst) and mn in _GRP1_EXT:
            r = _parse_reg(dst)
            imm = self._parse_immediate(src)
            ext = _GRP1_EXT[mn]
            return [0x83, _modrm(0b11, ext, r), _imm8_byte(imm)]

        raise AssemblerError(f"Invalid {mn} operands: {dst}, {src}")

    # ── Memory operand parser ───────────────────────────────────────
    def _parse_mem(self, token: str) -> tuple[int, int | None]:
        """Parse [REG] or [REG+disp] or [REG-disp].

        Returns (base_reg_index, displacement_or_None).
        """
        inner = token.strip().strip('[]').strip()

        # [REG+disp] or [REG-disp]
        m = re.match(r'(\w+)\s*([+-])\s*(\w+)', inner)
        if m:
            base = _parse_reg(m.group(1))
            sign = 1 if m.group(2) == '+' else -1
            disp = self._parse_immediate(m.group(3)) * sign
            return base, disp

        # [REG]
        base = _parse_reg(inner)
        return base, None
