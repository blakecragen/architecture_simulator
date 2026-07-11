"""
Core-C abstract syntax tree.

Small dataclass-style node hierarchy. Every node records the 1-based source
``line`` it originated on (used for the source map and located errors) and
exposes ``to_dict()`` producing a JSON-serializable nested dict — the /compile
route returns this verbatim as ``stages.ast``.

Node families:
    Program(functions, globals)
    Function(name, params, body)          params: list[str]
    Expressions:
        Number(value)
        Var(name)
        Index(array, index)               a[i]
        Unary(op, operand)                 - ! * &   (~ is desugared to ^ -1)
        Binary(op, left, right)            + - * / % < <= > >= == != && || & | ^ << >>
        Assign(target, value)              target is Var|Index|Unary('*')
        Ternary(cond, then_expr, else_expr)   cond ? a : b
        IncDec(target, op, prefix)         ++/-- (op '+'/'-', prefix bool)
        Call(name, args)
    Statements:
        VarDecl(name, init, is_array, size, init_list, is_global)
        ExprStmt(expr)
        If(cond, then_body, else_body)
        While(cond, body)
        For(init, cond, step, body)
        Return(value)
        Break() / Continue()
        Block(statements)
"""
from __future__ import annotations

from typing import List, Optional


class Node:
    line: int = 0

    def to_dict(self) -> dict:  # pragma: no cover - overridden everywhere
        raise NotImplementedError


# ── Top level ─────────────────────────────────────────────────────────
class Program(Node):
    def __init__(self, functions: List["Function"], globals: Optional[list] = None,
                 line: int = 0):
        self.functions = functions
        self.globals = globals or []      # list[VarDecl] declared at file scope
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "Program",
                "globals": [g.to_dict() for g in self.globals],
                "functions": [f.to_dict() for f in self.functions]}


class Function(Node):
    def __init__(self, name: str, params: List[str], body: "Block", line: int = 0):
        self.name = name
        self.params = params
        self.body = body
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "Function", "name": self.name, "params": list(self.params),
                "line": self.line, "body": self.body.to_dict()}


# ── Expressions ───────────────────────────────────────────────────────
class Number(Node):
    def __init__(self, value: int, line: int = 0):
        self.value = value
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "Number", "value": self.value, "line": self.line}


class Var(Node):
    def __init__(self, name: str, line: int = 0):
        self.name = name
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "Var", "name": self.name, "line": self.line}


class Index(Node):
    def __init__(self, array: Node, index: Node, line: int = 0):
        self.array = array
        self.index = index
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "Index", "array": self.array.to_dict(),
                "index": self.index.to_dict(), "line": self.line}


class Unary(Node):
    def __init__(self, op: str, operand: Node, line: int = 0):
        self.op = op
        self.operand = operand
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "Unary", "op": self.op,
                "operand": self.operand.to_dict(), "line": self.line}


class Binary(Node):
    def __init__(self, op: str, left: Node, right: Node, line: int = 0):
        self.op = op
        self.left = left
        self.right = right
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "Binary", "op": self.op, "left": self.left.to_dict(),
                "right": self.right.to_dict(), "line": self.line}


class Assign(Node):
    def __init__(self, target: Node, value: Node, line: int = 0):
        self.target = target
        self.value = value
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "Assign", "target": self.target.to_dict(),
                "value": self.value.to_dict(), "line": self.line}


class Call(Node):
    def __init__(self, name: str, args: List[Node], line: int = 0):
        self.name = name
        self.args = args
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "Call", "name": self.name,
                "args": [a.to_dict() for a in self.args], "line": self.line}


class Ternary(Node):
    """cond ? then_expr : else_expr"""
    def __init__(self, cond: Node, then_expr: Node, else_expr: Node, line: int = 0):
        self.cond = cond
        self.then_expr = then_expr
        self.else_expr = else_expr
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "Ternary", "cond": self.cond.to_dict(),
                "then": self.then_expr.to_dict(),
                "else": self.else_expr.to_dict(), "line": self.line}


class IncDec(Node):
    """++/-- on an lvalue. op is '+' or '-'; prefix vs postfix changes the
    value the expression yields (new value vs old value)."""
    def __init__(self, target: Node, op: str, prefix: bool, line: int = 0):
        self.target = target
        self.op = op
        self.prefix = prefix
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "IncDec", "op": self.op, "prefix": self.prefix,
                "target": self.target.to_dict(), "line": self.line}


# ── Statements ────────────────────────────────────────────────────────
class VarDecl(Node):
    def __init__(self, name: str, init: Optional[Node], is_array: bool = False,
                 size: Optional[int] = None, init_list: Optional[List[Node]] = None,
                 is_global: bool = False, line: int = 0):
        self.name = name
        self.init = init
        self.is_array = is_array
        self.size = size
        self.init_list = init_list        # array initializer: list[expr] or None
        self.is_global = is_global
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "VarDecl", "name": self.name, "is_array": self.is_array,
                "size": self.size, "line": self.line, "is_global": self.is_global,
                "init": self.init.to_dict() if self.init is not None else None,
                "init_list": [e.to_dict() for e in self.init_list]
                if self.init_list is not None else None}


class ExprStmt(Node):
    def __init__(self, expr: Node, line: int = 0):
        self.expr = expr
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "ExprStmt", "expr": self.expr.to_dict(), "line": self.line}


class If(Node):
    def __init__(self, cond: Node, then_body: "Block",
                 else_body: Optional["Block"], line: int = 0):
        self.cond = cond
        self.then_body = then_body
        self.else_body = else_body
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "If", "cond": self.cond.to_dict(),
                "then": self.then_body.to_dict(), "line": self.line,
                "else": self.else_body.to_dict() if self.else_body else None}


class While(Node):
    def __init__(self, cond: Node, body: "Block", line: int = 0):
        self.cond = cond
        self.body = body
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "While", "cond": self.cond.to_dict(),
                "body": self.body.to_dict(), "line": self.line}


class For(Node):
    def __init__(self, init: Optional[Node], cond: Optional[Node],
                 step: Optional[Node], body: "Block", line: int = 0):
        self.init = init
        self.cond = cond
        self.step = step
        self.body = body
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "For",
                "init": self.init.to_dict() if self.init else None,
                "cond": self.cond.to_dict() if self.cond else None,
                "step": self.step.to_dict() if self.step else None,
                "body": self.body.to_dict(), "line": self.line}


class Return(Node):
    def __init__(self, value: Optional[Node], line: int = 0):
        self.value = value
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "Return", "line": self.line,
                "value": self.value.to_dict() if self.value is not None else None}


class Block(Node):
    def __init__(self, statements: List[Node], line: int = 0):
        self.statements = statements
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "Block",
                "statements": [s.to_dict() for s in self.statements]}


class Break(Node):
    def __init__(self, line: int = 0):
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "Break", "line": self.line}


class Continue(Node):
    def __init__(self, line: int = 0):
        self.line = line

    def to_dict(self) -> dict:
        return {"node": "Continue", "line": self.line}
