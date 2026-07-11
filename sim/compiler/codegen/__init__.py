"""
Code-generator dispatch for Core-C.

``get_codegen(isa)`` returns a fresh per-ISA code generator instance. Each
generator subclasses ``CodeGenBase`` and emits the project's own assembly
mnemonics for that ISA.
"""
from __future__ import annotations

from ..errors import CompilerError


def get_codegen(isa: str):
    key = isa.strip().lower()
    if key == "riscv":
        from .riscv import RISCVCodeGen
        return RISCVCodeGen()
    if key == "arm":
        from .arm import ARMCodeGen
        return ARMCodeGen()
    if key == "x86":
        from .x86 import X86CodeGen
        return X86CodeGen()
    raise CompilerError(f"no code generator for ISA '{isa}'")
