from __future__ import annotations


class ISABase:
    """
    ISA configuration base class.

    Subclasses declare ISA-specific properties (register count, zero register,
    PC reset value, register names). The preset's build() function uses these
    to configure shared components.
    """
    name: str = "unknown"
    display_name: str = "Unknown"
    description: str = ""
    num_regs: int = 32
    zero_reg: bool = True
    zero_reg_index: int = 0
    pc_reset: int = 0
    program_format: str = "words"   # "words" (32-bit) or "bytes"

    def register_names(self) -> list[str]:
        return [f"x{i}" for i in range(self.num_regs)]

    def default_nop(self) -> int:
        """ISA-specific NOP encoding (single word or byte)."""
        return 0

    def demo_program(self) -> list[int]:
        """Default demo program for this ISA (loaded in UI on ISA switch)."""
        return []

    def demo_program_asm(self) -> str:
        """Default demo program as assembly text."""
        return ""
