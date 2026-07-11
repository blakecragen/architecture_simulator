"""
Assembler package for the RTL CPU Simulator.

Dispatches to the correct ISA-specific assembler based on ISA name.
"""
from .riscv import RISCVAssembler
from .arm import ARMAssembler
from .x86 import X86Assembler

_ASSEMBLERS = {
    "riscv": RISCVAssembler,
    "arm":   ARMAssembler,
    "x86":   X86Assembler,
}


def assemble(isa_name: str, text: str) -> list[int]:
    """Dispatch to the correct assembler by ISA name.

    Args:
        isa_name: One of "riscv", "arm", "x86" (case-insensitive).
        text: Assembly source text.

    Returns:
        List of ints -- 32-bit words for RISC-V/ARM, bytes for x86.
    """
    key = isa_name.strip().lower()
    if key not in _ASSEMBLERS:
        raise ValueError(
            f"Unknown ISA '{isa_name}'. Supported: {', '.join(_ASSEMBLERS)}"
        )
    return _ASSEMBLERS[key]().assemble(text)
