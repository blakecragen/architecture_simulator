"""
Compiler error type.

A single exception class carries an optional source location (1-based line
and column). ``str()`` renders it as ``line L col C: message`` when a location
is known, so both the /compile route and the tests can assert on a stable,
human-readable form.
"""
from __future__ import annotations

from typing import Optional


class CompilerError(Exception):
    """Raised for any Core-C compilation failure (lex/parse/codegen).

    Attributes:
        message: the human-readable diagnostic (no location prefix).
        line:    1-based source line, or None if unknown.
        col:     1-based source column, or None if unknown.
    """

    def __init__(self, message: str, line: Optional[int] = None,
                 col: Optional[int] = None):
        self.message = message
        self.line = line
        self.col = col
        super().__init__(self.__str__())

    def __str__(self) -> str:
        if self.line is not None and self.col is not None:
            return f"line {self.line} col {self.col}: {self.message}"
        if self.line is not None:
            return f"line {self.line}: {self.message}"
        return self.message
