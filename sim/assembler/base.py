"""
Base class for all ISA assemblers.

Implements a two-pass assembly pipeline:
  Pass 1 -- scan for labels, build label-to-address map.
  Pass 2 -- encode each instruction using the label map for offset resolution.
"""
import re


class AssemblerError(Exception):
    """Raised when assembly fails."""
    def __init__(self, message, line_number=None, line_text=None):
        self.line_number = line_number
        self.line_text = line_text
        detail = f"line {line_number}: " if line_number is not None else ""
        if line_text:
            detail += f"'{line_text.strip()}' -- "
        super().__init__(f"{detail}{message}")


class AssemblerBase:
    """Abstract two-pass assembler.

    Subclasses must implement:
        _encode(mnemonic, operands, pc, labels) -> int | list[int]
        _pc_increment() -> int  (fixed-width ISAs)
    """

    # ── Public API ──────────────────────────────────────────────────

    def assemble(self, text: str) -> list[int]:
        """Two-pass assembly: pass1=labels, pass2=encode.

        Returns list of ints (words for RISC-V/ARM, bytes for x86).
        """
        lines = self._preprocess(text)
        labels, cleaned = self._pass1(lines)
        return self._pass2(cleaned, labels)

    # ── Preprocessing ───────────────────────────────────────────────

    def _preprocess(self, text: str) -> list[tuple[int, str]]:
        """Strip comments, blank lines, normalize whitespace.

        Returns list of (original_line_number, cleaned_text).
        """
        result = []
        for lineno, raw in enumerate(text.splitlines(), start=1):
            # Strip line comments: # or ; or //
            line = re.split(r'[#;]|//', raw)[0]
            line = line.strip()
            if line:
                result.append((lineno, line))
        return result

    # ── Pass 1: label collection ────────────────────────────────────

    def _pass1(self, lines: list[tuple[int, str]]) -> tuple[dict, list[tuple[int, int, str]]]:
        """Scan for labels (e.g. 'loop:'), build label -> address map.

        Returns (labels_dict, cleaned_lines) where cleaned_lines is
        [(original_lineno, pc_address, instruction_text), ...].
        """
        labels: dict[str, int] = {}
        cleaned: list[tuple[int, int, str]] = []
        pc = 0

        for lineno, line in lines:
            # Check for label(s) at the start of the line
            while True:
                m = re.match(r'^([A-Za-z_]\w*)\s*:\s*(.*)', line)
                if not m:
                    break
                label_name = m.group(1)
                if label_name in labels:
                    raise AssemblerError(
                        f"Duplicate label '{label_name}'", lineno, line
                    )
                labels[label_name] = pc
                line = m.group(2).strip()

            if not line:
                continue

            cleaned.append((lineno, pc, line))
            pc += self._estimate_instruction_size_at(lineno, line)

        return labels, cleaned

    # ── Pass 2: encoding ────────────────────────────────────────────

    def _pass2(self, cleaned: list[tuple[int, int, str]], labels: dict) -> list[int]:
        """Encode each instruction line. Returns flat list of ints."""
        result = []
        for lineno, pc, line in cleaned:
            parts = self._split_instruction(line)
            mnemonic = parts[0].upper()
            operands = parts[1:]
            try:
                encoded = self._encode(mnemonic, operands, pc, labels)
            except AssemblerError:
                raise
            except Exception as e:
                raise AssemblerError(str(e), lineno, line) from e
            if isinstance(encoded, list):
                result.extend(encoded)
            else:
                result.append(encoded)
        return result

    # ── Helpers ──────────────────────────────────────────────────────

    def _split_instruction(self, line: str) -> list[str]:
        """Split 'ADD x3, x1, x2' into ['ADD', 'x3', 'x1', 'x2'].

        Handles commas and whitespace as delimiters.
        """
        # Replace commas with spaces, then split
        tokens = line.replace(',', ' ').split()
        return tokens

    def _estimate_instruction_size(self, line: str) -> int:
        """Return estimated byte size for pass-1 PC tracking.

        Override in x86 for variable-length; fixed-width ISAs use _pc_increment().
        """
        return self._pc_increment()

    def _estimate_instruction_size_at(self, lineno: int, line: str) -> int:
        """Line-identity-aware size hook. The x86 assembler overrides this for
        branch relaxation (a jump widened to rel32 must keep its widened size
        across layout iterations); everyone else falls through to the
        text-only estimator."""
        return self._estimate_instruction_size(line)

    def _pc_increment(self) -> int:
        """Fixed PC increment per instruction. Override in subclass."""
        return 4  # RISC-V and ARM default

    def _encode(self, mnemonic: str, operands: list[str], pc: int, labels: dict):
        """Encode a single instruction. Must be overridden by subclass.

        Returns int (single word) or list[int] (bytes for x86).
        """
        raise NotImplementedError

    def _parse_immediate(self, token: str) -> int:
        """Parse an immediate value: decimal, hex (0x...), or binary (0b...)."""
        token = token.strip().lstrip('#')
        if token.startswith('-'):
            return -self._parse_immediate(token[1:])
        if token.lower().startswith('0x'):
            return int(token, 16)
        if token.lower().startswith('0b'):
            return int(token, 2)
        return int(token)

    def _resolve_label_or_imm(self, token: str, pc: int, labels: dict) -> int:
        """Resolve a label to a PC-relative offset, or parse as immediate."""
        token = token.strip()
        if token in labels:
            return labels[token] - pc
        # Could be a signed offset like +8 or -4 or just a number
        return self._parse_immediate(token)

    @staticmethod
    def _mask(value: int, bits: int) -> int:
        """Mask value to the given number of bits."""
        return value & ((1 << bits) - 1)

    # ── Range validation (so out-of-range fields raise instead of
    #    silently truncating to a wrong-but-valid encoding) ───────────

    def _require_signed(self, value: int, bits: int, what: str = "immediate") -> int:
        lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
        if not (lo <= value <= hi):
            raise AssemblerError(
                f"{what} {value} out of range for signed {bits}-bit field [{lo}..{hi}]")
        return value

    def _require_unsigned(self, value: int, bits: int, what: str = "immediate") -> int:
        hi = (1 << bits) - 1
        if not (0 <= value <= hi):
            raise AssemblerError(
                f"{what} {value} out of range for unsigned {bits}-bit field [0..{hi}]")
        return value

    def _require_aligned(self, value: int, align: int, what: str = "offset") -> int:
        if value % align != 0:
            raise AssemblerError(f"{what} {value} must be a multiple of {align}")
        return value
