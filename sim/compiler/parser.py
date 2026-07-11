"""
Core-C recursive-descent parser.

Grammar (Core C):
    program     := (function | global-decl)+
    global-decl := var-decl ';'
    function    := ['const'] ('int'|'void') IDENT '(' params ')' block
    params      := ε | 'void' | param (',' param)*
    param       := ['const'] 'int' ['*'] IDENT ['[' [expr] ']']   (array/ptr param)
    block       := '{' statement* '}'
    statement   := var-decl ';' | 'if' ... | 'while' ... | 'for' ...
                 | 'break' ';' | 'continue' ';' | 'return' [expr] ';'
                 | block | expr ';'
    var-decl    := ['const'] 'int' IDENT
                     [ '[' [const-expr] ']' ]        (const-expr / inferred size)
                     [ '=' (expr | '{' expr,* '}') ] (scalar init or array list)

Expressions are parsed by precedence climbing. From lowest to highest:
assignment (= and op= compound forms), ternary ?:, || && | ^ &, == != , relational,
shifts, + -, * / %, then unary (- ! ~ & * prefix-++/--) and postfix ([]  ++/--).
Array sizes must be compile-time constants (literals / prior consts / arithmetic
over them), folded by ``_const_eval``. ``~x`` desugars to ``x ^ -1`` and
``a op= b`` to ``a = a op b``. Function names are pre-scanned so forward and
recursive calls resolve. Out-of-scope constructs raise ``CompilerError(msg, line, col)``.
"""
from __future__ import annotations

from typing import List, Optional

from . import ast
from .errors import CompilerError
from .lexer import Token, tokenize

# Binary operator precedence (higher binds tighter). Assignment and the ternary
# conditional are handled separately (lower than any binary op). Bitwise
# | ^ & sit between && and the equality operators, matching C.
_BINARY_PREC = {
    "||": 1,
    "&&": 2,
    "|": 3,
    "^": 4,
    "&": 5,
    "==": 6, "!=": 6,
    "<": 7, "<=": 7, ">": 7, ">=": 7,
    "<<": 8, ">>": 8,
    "+": 9, "-": 9,
    "*": 10, "/": 10, "%": 10,
}

# op= forms desugar to  target = target op value.
_COMPOUND_ASSIGN = {
    "+=": "+", "-=": "-", "*=": "*", "/=": "/", "%=": "%",
    "&=": "&", "|=": "|", "^=": "^", "<<=": "<<", ">>=": ">>",
}


class Parser:
    def __init__(self, tokens: List[Token]):
        self.toks = tokens
        self.pos = 0
        self.func_names: set[str] = set()
        # name -> int value for names bound to a compile-time constant (used to
        # resolve array sizes like `int arr[N]`). Reset to the global consts at
        # each function boundary so locals don't leak between functions.
        self.const_env: dict = {}

    # ── token helpers ─────────────────────────────────────────────
    @property
    def cur(self) -> Token:
        return self.toks[self.pos]

    def _at_end(self) -> bool:
        return self.cur.kind == "EOF"

    def _advance(self) -> Token:
        tok = self.toks[self.pos]
        if tok.kind != "EOF":
            self.pos += 1
        return tok

    def _check(self, kind: str, value=None) -> bool:
        t = self.cur
        if t.kind != kind:
            return False
        return value is None or t.value == value

    def _accept(self, kind: str, value=None) -> Optional[Token]:
        if self._check(kind, value):
            return self._advance()
        return None

    def _expect(self, kind: str, value=None) -> Token:
        if self._check(kind, value):
            return self._advance()
        want = f"{kind} {value!r}" if value is not None else kind
        got = self.cur
        got_desc = repr(got.value) if got.kind != "EOF" else "end of input"
        raise CompilerError(f"expected {want}, got {got_desc}",
                            got.line, got.col)

    # ── entry ─────────────────────────────────────────────────────
    def parse_program(self) -> ast.Program:
        # Pre-scan function names for forward/recursive references.
        self._prescan_functions()
        functions: List[ast.Function] = []
        globals_: List[ast.VarDecl] = []
        while not self._at_end():
            if self._is_function_ahead():
                functions.append(self._parse_function())
            else:
                decl = self._parse_var_decl(is_global=True)
                self._expect("OP", ";")
                globals_.append(decl)
        if not functions:
            raise CompilerError("program has no functions", 1, 1)
        return ast.Program(functions, globals=globals_, line=1)

    def _is_function_ahead(self) -> bool:
        """True if the next top-level item is a function definition (vs a global
        variable declaration). Looks past an optional 'const' + type + IDENT for
        an opening '('."""
        i = self.pos
        if self.toks[i].kind == "KEYWORD" and self.toks[i].value == "const":
            i += 1
        # A malformed start is handed to _parse_function for a precise error.
        if not (self.toks[i].kind == "KEYWORD"
                and self.toks[i].value in ("int", "void")):
            return True
        if i + 1 >= len(self.toks) or self.toks[i + 1].kind != "IDENT":
            return True
        return (i + 2 < len(self.toks) and self.toks[i + 2].kind == "OP"
                and self.toks[i + 2].value == "(")

    def _prescan_functions(self) -> None:
        # Walk tokens looking for '<type> IDENT (' at what is plausibly a
        # top-level function definition. This is a light scan; the real
        # structural validation happens in _parse_function.
        i = 0
        toks = self.toks
        depth = 0
        while i < len(toks) and toks[i].kind != "EOF":
            t = toks[i]
            if t.kind == "OP" and t.value == "{":
                depth += 1
            elif t.kind == "OP" and t.value == "}":
                depth -= 1
            elif (depth == 0 and t.kind == "KEYWORD" and t.value in ("int", "void")
                    and i + 2 < len(toks)
                    and toks[i + 1].kind == "IDENT"
                    and toks[i + 2].kind == "OP" and toks[i + 2].value == "("):
                self.func_names.add(toks[i + 1].value)
            i += 1

    # ── functions ─────────────────────────────────────────────────
    def _parse_function(self) -> ast.Function:
        self._accept("KEYWORD", "const")   # tolerate a const-qualified return type
        ret_tok = self.cur
        if not (self._check("KEYWORD", "int") or self._check("KEYWORD", "void")):
            raise CompilerError(
                "expected function definition beginning with 'int' or 'void'",
                ret_tok.line, ret_tok.col)
        self._advance()  # return type
        name_tok = self._expect("IDENT")
        self._expect("OP", "(")
        params = self._parse_params()
        self._expect("OP", ")")
        # Locals declared in this body must not leak into sibling functions;
        # snapshot the (global) const environment and restore it afterwards.
        saved_consts = dict(self.const_env)
        body = self._parse_block()
        self.const_env = saved_consts
        return ast.Function(name_tok.value, params, body, line=name_tok.line)

    def _parse_params(self) -> List[str]:
        params: List[str] = []
        if self._check("OP", ")"):
            return params
        # allow 'void' as the sole "no params" marker
        if self._check("KEYWORD", "void") and \
                self.toks[self.pos + 1].kind == "OP" and \
                self.toks[self.pos + 1].value == ")":
            self._advance()
            return params
        while True:
            self._accept("KEYWORD", "const")   # tolerate 'const int' params
            self._expect("KEYWORD", "int")
            star = self._accept("OP", "*")      # int *p  -> pointer param
            name_tok = self._expect("IDENT")
            if self._accept("OP", "["):
                # array parameter: int a[]  or  int a[N] — both decay to a
                # pointer (the caller passes the base address). Skip any size.
                if not self._check("OP", "]"):
                    self._parse_expression()
                self._expect("OP", "]")
            params.append(name_tok.value)
            if not self._accept("OP", ","):
                break
        return params

    # ── statements ────────────────────────────────────────────────
    def _parse_block(self) -> ast.Block:
        brace = self._expect("OP", "{")
        stmts: List[ast.Node] = []
        while not self._check("OP", "}") and not self._at_end():
            stmts.append(self._parse_statement())
        self._expect("OP", "}")
        return ast.Block(stmts, line=brace.line)

    def _parse_statement(self) -> ast.Node:
        t = self.cur

        if self._check("OP", "{"):
            return self._parse_block()

        if self._check("KEYWORD", "int") or self._check("KEYWORD", "const"):
            decl = self._parse_var_decl()
            self._expect("OP", ";")
            return decl

        if self._check("KEYWORD", "if"):
            return self._parse_if()

        if self._check("KEYWORD", "while"):
            return self._parse_while()

        if self._check("KEYWORD", "for"):
            return self._parse_for()

        if self._check("KEYWORD", "break"):
            self._advance()
            self._expect("OP", ";")
            return ast.Break(line=t.line)

        if self._check("KEYWORD", "continue"):
            self._advance()
            self._expect("OP", ";")
            return ast.Continue(line=t.line)

        if self._check("KEYWORD", "return"):
            self._advance()
            if self._check("OP", ";"):
                self._advance()
                return ast.Return(None, line=t.line)
            expr = self._parse_expression()
            self._expect("OP", ";")
            return ast.Return(expr, line=t.line)

        if self._check("KEYWORD", "else"):
            raise CompilerError("'else' without matching 'if'", t.line, t.col)

        # Reject stray declarations of unsupported types already handled by the
        # lexer; anything else is an expression statement.
        expr = self._parse_expression()
        self._expect("OP", ";")
        return ast.ExprStmt(expr, line=t.line)

    def _parse_var_decl(self, is_global: bool = False) -> ast.VarDecl:
        self._accept("KEYWORD", "const")   # optional; folded like any constexpr
        self._expect("KEYWORD", "int")
        # Reject pointer declarations 'int *p;' — pointers are only supported as
        # the address-of/deref operators on existing ints and as int[] params.
        if self._check("OP", "*"):
            star = self.cur
            raise CompilerError("pointer variable declarations are not supported "
                                "(use int and &/* on scalars, or int[] params)",
                                star.line, star.col)
        name_tok = self._expect("IDENT")
        is_array = False
        size = None
        init_list = None
        if self._accept("OP", "["):
            if self._check("OP", "]"):
                self._advance()            # int a[] — size inferred from init
                is_array = True
            else:
                # Array size may be any compile-time-constant expression
                # (literal, prior const, or arithmetic over them), e.g.
                # int arr[N], int arr[N*4], int arr[8+2].
                size = self._const_eval(self._parse_expression())
                if size <= 0:
                    raise CompilerError("array size must be positive",
                                        name_tok.line, name_tok.col)
                is_array = True
                self._expect("OP", "]")
        init = None
        if self._accept("OP", "="):
            if is_array:
                init_list = self._parse_init_list()
                if size is None:
                    if not init_list:
                        raise CompilerError("empty initializer needs an array size",
                                            name_tok.line, name_tok.col)
                    size = len(init_list)
                elif len(init_list) > size:
                    raise CompilerError(
                        f"too many initializers ({len(init_list)}) for "
                        f"'{name_tok.value}[{size}]'", name_tok.line, name_tok.col)
            else:
                init = self._parse_expression()
        if is_array and size is None:
            raise CompilerError(f"array '{name_tok.value}' needs a size or an "
                                f"initializer", name_tok.line, name_tok.col)
        # Record a compile-time constant so LATER array sizes can reference it.
        if not is_array and init is not None:
            try:
                self.const_env[name_tok.value] = self._const_eval(init)
            except CompilerError:
                self.const_env.pop(name_tok.value, None)   # not a constant
        return ast.VarDecl(name_tok.value, init, is_array, size, init_list,
                           is_global, line=name_tok.line)

    def _parse_init_list(self) -> List[ast.Node]:
        self._expect("OP", "{")
        elems: List[ast.Node] = []
        if not self._check("OP", "}"):
            while True:
                elems.append(self._parse_expression())
                if not self._accept("OP", ","):
                    break
        self._expect("OP", "}")
        return elems

    def _const_eval(self, node: ast.Node) -> int:
        """Fold a compile-time integer constant expression, or raise.

        Handles literals, names bound to earlier constants, and integer
        arithmetic/bitwise/shift over them (C trunc-toward-zero for / and %).
        """
        if isinstance(node, ast.Number):
            return node.value
        if isinstance(node, ast.Var):
            if node.name in self.const_env:
                return self.const_env[node.name]
            raise CompilerError(
                f"'{node.name}' is not a compile-time constant "
                f"(array sizes must be constant)", node.line)
        if isinstance(node, ast.Unary):
            v = self._const_eval(node.operand)
            if node.op == "-":
                return -v
            if node.op == "+":
                return v
            if node.op == "~":
                return ~v
            raise CompilerError("operator not allowed in a constant expression",
                                node.line)
        if isinstance(node, ast.Binary):
            a = self._const_eval(node.left)
            b = self._const_eval(node.right)
            op = node.op
            if op == "+": return a + b
            if op == "-": return a - b
            if op == "*": return a * b
            if op in ("/", "%"):
                if b == 0:
                    raise CompilerError("division by zero in constant expression",
                                        node.line)
                q = abs(a) // abs(b)
                if (a < 0) != (b < 0):
                    q = -q
                return q if op == "/" else a - q * b
            if op == "<<": return a << b
            if op == ">>": return a >> b
            if op == "&": return a & b
            if op == "|": return a | b
            if op == "^": return a ^ b
        raise CompilerError("not a compile-time constant expression",
                            getattr(node, "line", None))

    def _parse_if(self) -> ast.If:
        t = self._expect("KEYWORD", "if")
        self._expect("OP", "(")
        cond = self._parse_expression()
        self._expect("OP", ")")
        then_body = self._as_block(self._parse_statement())
        else_body = None
        if self._accept("KEYWORD", "else"):
            else_body = self._as_block(self._parse_statement())
        return ast.If(cond, then_body, else_body, line=t.line)

    def _parse_while(self) -> ast.While:
        t = self._expect("KEYWORD", "while")
        self._expect("OP", "(")
        cond = self._parse_expression()
        self._expect("OP", ")")
        body = self._as_block(self._parse_statement())
        return ast.While(cond, body, line=t.line)

    def _parse_for(self) -> ast.For:
        t = self._expect("KEYWORD", "for")
        self._expect("OP", "(")
        # init: declaration or expression or empty
        init = None
        if not self._check("OP", ";"):
            if self._check("KEYWORD", "int") or self._check("KEYWORD", "const"):
                init = self._parse_var_decl()
            else:
                init = ast.ExprStmt(self._parse_expression(), line=self.cur.line)
        self._expect("OP", ";")
        cond = None
        if not self._check("OP", ";"):
            cond = self._parse_expression()
        self._expect("OP", ";")
        step = None
        if not self._check("OP", ")"):
            step = self._parse_expression()
        self._expect("OP", ")")
        body = self._as_block(self._parse_statement())
        return ast.For(init, cond, step, body, line=t.line)

    @staticmethod
    def _as_block(stmt: ast.Node) -> ast.Block:
        if isinstance(stmt, ast.Block):
            return stmt
        return ast.Block([stmt], line=stmt.line)

    # ── expressions (precedence climbing) ─────────────────────────
    def _parse_expression(self) -> ast.Node:
        return self._parse_assignment()

    def _parse_assignment(self) -> ast.Node:
        left = self._parse_ternary()
        if self._check("OP", "="):
            eq = self._advance()
            value = self._parse_assignment()  # right-associative
            self._require_lvalue(left, eq)
            return ast.Assign(left, value, line=eq.line)
        # compound assignment:  target op= value  ->  target = target op value
        if self._check("OP") and self.cur.value in _COMPOUND_ASSIGN:
            op_tok = self._advance()
            self._require_lvalue(left, op_tok)
            value = self._parse_assignment()
            combined = ast.Binary(_COMPOUND_ASSIGN[op_tok.value], left, value,
                                  line=op_tok.line)
            return ast.Assign(left, combined, line=op_tok.line)
        return left

    def _parse_ternary(self) -> ast.Node:
        cond = self._parse_binary(0)
        if self._check("OP", "?"):
            q = self._advance()
            then_expr = self._parse_assignment()
            self._expect("OP", ":")
            else_expr = self._parse_assignment()
            return ast.Ternary(cond, then_expr, else_expr, line=q.line)
        return cond

    @staticmethod
    def _require_lvalue(node: ast.Node, tok: Token) -> None:
        if not (isinstance(node, (ast.Var, ast.Index))
                or (isinstance(node, ast.Unary) and node.op == "*")):
            raise CompilerError("invalid assignment target", tok.line, tok.col)

    def _parse_binary(self, min_prec: int) -> ast.Node:
        left = self._parse_unary()
        while self._check("OP") and self.cur.value in _BINARY_PREC:
            op_tok = self.cur
            prec = _BINARY_PREC[op_tok.value]
            if prec < min_prec:
                break
            self._advance()
            # left-associative: parse right side with higher min precedence
            right = self._parse_binary(prec + 1)
            left = ast.Binary(op_tok.value, left, right, line=op_tok.line)
        return left

    def _parse_unary(self) -> ast.Node:
        t = self.cur
        # prefix ++/-- : ++x  ->  IncDec(x, prefix=True)
        if self._check("OP") and t.value in ("++", "--"):
            self._advance()
            operand = self._parse_unary()
            self._require_lvalue(operand, t)
            return ast.IncDec(operand, "+" if t.value == "++" else "-",
                              prefix=True, line=t.line)
        if self._check("OP") and t.value in ("-", "!", "*", "&", "+", "~"):
            self._advance()
            operand = self._parse_unary()
            if t.value == "+":
                return operand  # unary plus is identity
            if t.value == "~":
                # bitwise NOT: ~x == x ^ -1 (reuses the XOR lowering).
                return ast.Binary("^", operand, ast.Number(-1, line=t.line),
                                  line=t.line)
            if t.value == "&" and not isinstance(operand, (ast.Var, ast.Index)):
                raise CompilerError("'&' requires an lvalue (variable or array element)",
                                    t.line, t.col)
            return ast.Unary(t.value, operand, line=t.line)
        return self._parse_postfix()

    def _parse_postfix(self) -> ast.Node:
        node = self._parse_primary()
        while True:
            if self._check("OP", "["):
                lb = self._advance()
                idx = self._parse_expression()
                self._expect("OP", "]")
                node = ast.Index(node, idx, line=lb.line)
            elif self._check("OP") and self.cur.value in ("++", "--"):
                op_tok = self._advance()
                self._require_lvalue(node, op_tok)
                node = ast.IncDec(node, "+" if op_tok.value == "++" else "-",
                                  prefix=False, line=op_tok.line)
            else:
                break
        return node

    def _parse_primary(self) -> ast.Node:
        t = self.cur

        if self._check("NUMBER"):
            self._advance()
            return ast.Number(t.value, line=t.line)

        if self._check("OP", "("):
            self._advance()
            expr = self._parse_expression()
            self._expect("OP", ")")
            return expr

        if self._check("IDENT"):
            self._advance()
            # function call?
            if self._check("OP", "("):
                self._advance()
                args: List[ast.Node] = []
                if not self._check("OP", ")"):
                    while True:
                        args.append(self._parse_expression())
                        if not self._accept("OP", ","):
                            break
                self._expect("OP", ")")
                return ast.Call(t.value, args, line=t.line)
            return ast.Var(t.value, line=t.line)

        # Unsupported literal forms produce a located error.
        desc = repr(t.value) if t.kind != "EOF" else "end of input"
        raise CompilerError(f"unexpected token {desc} in expression",
                            t.line, t.col)


def parse(source: str) -> ast.Program:
    """Tokenize + parse Core-C source into an ast.Program."""
    return Parser(tokenize(source)).parse_program()
