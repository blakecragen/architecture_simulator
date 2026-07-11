"""
Core-C compiler package.

Public entry point:

    compile_c(source, isa) -> CompileResult

``compile_c`` runs the pure-Python front end (lex -> parse -> per-ISA codegen)
to produce the project's own assembly text, which flows unchanged through
``sim/assembler`` and the simulator harness. Compilation is entirely local and
self-contained — it never invokes an external compiler/toolchain.

CompileResult carries the assembly plus every intermediate stage so the UI can
render a compiler pipeline view:
    .asm        final assembly text (project mnemonics)
    .backend    always "python"
    .tokens     list[dict] {kind, value, line, col}
    .ast        JSON-serializable dict (Program.to_dict())
    .source_map list[dict] {asm_line, c_line}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .errors import CompilerError
from .lexer import tokenize
from .parser import Parser
from .codegen import get_codegen

__all__ = ["compile_c", "CompileResult", "CompilerError"]

_SUPPORTED_ISAS = ("riscv", "arm", "x86")


@dataclass
class CompileResult:
    asm: str
    backend: str = "python"
    tokens: List[dict] = field(default_factory=list)
    ast: dict = field(default_factory=dict)
    source_map: List[dict] = field(default_factory=list)
    # Static debugger symbols for main's frame: {name, kind, addr, size,
    # stride, location}.
    symbols: List[dict] = field(default_factory=list)


def compile_c(source: str, isa: str) -> CompileResult:
    """Compile Core-C ``source`` to assembly for ``isa`` (fully local).

    Args:
        source: Core-C source text.
        isa: one of "riscv", "arm", "x86".

    Returns:
        CompileResult with .asm and the intermediate stages.

    Raises:
        CompilerError: unknown ISA, or any lex/parse/codegen failure.
    """
    if not isinstance(source, str):
        raise CompilerError("source must be a string")
    key = isa.strip().lower() if isinstance(isa, str) else ""
    if key not in _SUPPORTED_ISAS:
        raise CompilerError(
            f"unknown ISA '{isa}' (expected one of {list(_SUPPORTED_ISAS)})")

    tokens = tokenize(source)
    ast_root = Parser(tokens).parse_program()
    token_dicts = [t.to_dict() for t in tokens]
    ast_dict = ast_root.to_dict()

    cg = get_codegen(key)
    asm = cg.generate(ast_root)
    return CompileResult(asm=asm, backend="python", tokens=token_dicts,
                         ast=ast_dict, source_map=cg.source_map,
                         symbols=cg.symbols())
