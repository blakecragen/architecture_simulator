"""
Core-C lexer.

Turns source text into a flat list of ``Token(kind, value, line, col)``.
Line comments (``//``) and block comments (``/* ... */``) are skipped. Every
token records the 1-based line and column of its first character so the parser
can raise located ``CompilerError``s and codegen can build a source map.

Token kinds:
    KEYWORD    int if else while for return void
    IDENT      identifiers (function/variable names)
    NUMBER     decimal / 0x.. / 0b.. integer literals (value is the int)
    OP         operators and punctuation (value is the literal text, e.g. '==')
    EOF        end-of-input sentinel (one, at the end)
"""
from __future__ import annotations

from typing import List

from .errors import CompilerError

KEYWORDS = {"int", "if", "else", "while", "for", "return", "void",
            "break", "continue", "const"}

# Operators, longest-match first: 3-char, then 2-char, then 1-char.
_OPS_3 = ["<<=", ">>="]
_OPS_2 = [
    "<<", ">>", "<=", ">=", "==", "!=", "&&", "||",
    "++", "--", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=",
]
_SINGLE_OPS = set("+-*/%<>=!&|^~?:()[]{};,")

# Reserved words that name features Core-C v1 does NOT support. Flagging them at
# lex/keyword time gives a precise located error instead of a confusing parse
# failure downstream.
_UNSUPPORTED_KEYWORDS = {
    "char", "float", "double", "struct", "union", "enum", "long", "short",
    "unsigned", "signed", "typedef", "static", "switch", "case",
    "do", "goto", "sizeof", "malloc", "free",
}


class Token:
    __slots__ = ("kind", "value", "line", "col")

    def __init__(self, kind: str, value, line: int, col: int):
        self.kind = kind
        self.value = value
        self.line = line
        self.col = col

    def to_dict(self) -> dict:
        return {"kind": self.kind, "value": self.value,
                "line": self.line, "col": self.col}

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Token({self.kind!r}, {self.value!r}, {self.line}, {self.col})"


class Lexer:
    def __init__(self, source: str):
        self.src = source
        self.n = len(source)
        self.i = 0
        self.line = 1
        self.col = 1

    def _advance(self) -> str:
        ch = self.src[self.i]
        self.i += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _peek(self, ahead: int = 0) -> str:
        j = self.i + ahead
        return self.src[j] if j < self.n else ""

    def _skip_ws_and_comments(self) -> None:
        while self.i < self.n:
            ch = self.src[self.i]
            if ch in " \t\r\n":
                self._advance()
            elif ch == "/" and self._peek(1) == "/":
                # line comment
                while self.i < self.n and self.src[self.i] != "\n":
                    self._advance()
            elif ch == "/" and self._peek(1) == "*":
                start_line, start_col = self.line, self.col
                self._advance()
                self._advance()
                closed = False
                while self.i < self.n:
                    if self.src[self.i] == "*" and self._peek(1) == "/":
                        self._advance()
                        self._advance()
                        closed = True
                        break
                    self._advance()
                if not closed:
                    raise CompilerError("unterminated block comment",
                                        start_line, start_col)
            else:
                break

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []
        while True:
            self._skip_ws_and_comments()
            if self.i >= self.n:
                tokens.append(Token("EOF", "", self.line, self.col))
                return tokens

            line, col = self.line, self.col
            ch = self.src[self.i]

            # ── identifier / keyword ──────────────────────────────
            if ch.isalpha() or ch == "_":
                start = self.i
                while self.i < self.n and (self.src[self.i].isalnum()
                                           or self.src[self.i] == "_"):
                    self._advance()
                word = self.src[start:self.i]
                if word in _UNSUPPORTED_KEYWORDS:
                    raise CompilerError(
                        f"unsupported type/keyword '{word}' "
                        f"(Core-C v1 supports only 'int')", line, col)
                kind = "KEYWORD" if word in KEYWORDS else "IDENT"
                tokens.append(Token(kind, word, line, col))
                continue

            # ── number literal ────────────────────────────────────
            if ch.isdigit():
                start = self.i
                if ch == "0" and self._peek(1) in ("x", "X"):
                    self._advance()
                    self._advance()
                    while self.i < self.n and self.src[self.i] in "0123456789abcdefABCDEF":
                        self._advance()
                    text = self.src[start:self.i]
                    if len(text) <= 2:
                        raise CompilerError("malformed hex literal", line, col)
                    tokens.append(Token("NUMBER", int(text, 16), line, col))
                    continue
                if ch == "0" and self._peek(1) in ("b", "B"):
                    self._advance()
                    self._advance()
                    while self.i < self.n and self.src[self.i] in "01":
                        self._advance()
                    text = self.src[start:self.i]
                    if len(text) <= 2:
                        raise CompilerError("malformed binary literal", line, col)
                    tokens.append(Token("NUMBER", int(text, 2), line, col))
                    continue
                while self.i < self.n and self.src[self.i].isdigit():
                    self._advance()
                # A digit immediately followed by an identifier char is illegal
                # (e.g. 12abc) — reject rather than silently splitting.
                if self.i < self.n and (self.src[self.i].isalpha()
                                        or self.src[self.i] == "_"):
                    raise CompilerError("invalid number literal", line, col)
                tokens.append(Token("NUMBER", int(self.src[start:self.i]), line, col))
                continue

            # ── operators / punctuation (longest match first) ─────
            three = self.src[self.i:self.i + 3]
            if three in _OPS_3:
                self._advance(); self._advance(); self._advance()
                tokens.append(Token("OP", three, line, col))
                continue
            two = self.src[self.i:self.i + 2]
            if two in _OPS_2:
                self._advance()
                self._advance()
                tokens.append(Token("OP", two, line, col))
                continue
            if ch in _SINGLE_OPS:
                self._advance()
                tokens.append(Token("OP", ch, line, col))
                continue

            raise CompilerError(f"unexpected character {ch!r}", line, col)


def tokenize(source: str) -> List[Token]:
    """Convenience wrapper: source text -> list[Token] (including EOF)."""
    return Lexer(source).tokenize()
