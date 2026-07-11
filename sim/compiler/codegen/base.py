"""
Shared Core-C code generator (frame model + AST walk).

This base class owns everything that is ISA-independent:

  * The **software call stack**. There is no hardware stack in the simulator's
    modelled ISAs (RISC-V sp is a plain GPR we reserve; ARM SP aliases XZR; x86
    CALL/RET push nothing), so we implement one ourselves. A reserved *frame
    register* holds the current frame base. The stack grows DOWN from a high
    byte address (``STACK_BASE``) and every function gets a fixed-size frame
    holding: saved caller frame pointer, saved return address, one slot per
    parameter, one slot per local, and a pool of temporary slots.

  * A per-frame collision **guard**: if a single function's frame would start
    at/below ``STACK_LIMIT`` (i.e. one frame alone is too big for the stack
    region) compilation raises ``CompilerError``. NOTE: recursion *depth* is
    data-dependent and is NOT statically bounded — a *very* deeply recursive
    program can still exhaust the ~61 KB stack region at run time and wrap. The
    64 KB simulated data memory gives generous headroom, though: the
    ``factorial_recursive`` demo uses depth 5, but hundreds of frames now fit
    before any wrap (the old 1 KB memory overflowed after a handful).

  * A naive **stack-machine** expression evaluator: the left operand of a binary
    op is spilled to a temp frame slot, the right operand is evaluated into the
    accumulator, then the ISA is asked to combine ``slot OP acc -> acc``. This
    favours obviously-correct code over register allocation.

  * Label-based **control flow** only — never hand-computed offsets — so the
    project assembler validates branch range/alignment for us.

  * A **source map** (asm line -> C line) accumulated as lines are emitted.

Concrete subclasses (riscv/arm/x86) implement the small set of ``emit_*``
primitives declared at the bottom and set the register/immediate policy knobs.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .. import ast
from ..errors import CompilerError

# ── Memory layout (bytes) ───────────────────────────────────────────────
# DataMemory is 16384 words / 64 KB, byte addressed; the effective index wraps
# at (addr>>2) % 16384, so everything must stay inside [0, 65536).
DATA_MEM_BYTES = 65536
# Reserved low region for globals; the software stack lives high and grows DOWN
# from near the top of memory, so recursion has ~61 KB of frame headroom.
GLOBAL_REGION_TOP = 2032     # reserved global/array data region [0, 2032)
STACK_TOP = 65528            # first stack frame's base (near the top of memory)
STACK_LIMIT = 4096           # stack must not grow at/below this (collision guard)
# print() console word: the builtin print(expr) statement compiles to a store of
# the value at this byte address. It sits in the unused gap between the globals
# region and STACK_LIMIT, so no frame or global ever writes it. Kept low and
# 8-aligned so RISC-V can store it with a single SW off x0 (12-bit immediate,
# <= 2047) and ARM with one MOVZ; the UI terminal replays the per-cycle stores
# to this address as console output.
PRINT_ADDR = 2040            # word 510


class FunctionContext:
    """Per-function frame bookkeeping."""

    def __init__(self, name: str, params: List[str], slot_size: int):
        self.name = name
        self.params = params
        self.slot_size = slot_size          # 4 (riscv/x86) or 8 (arm)
        # slot index (0-based, counting up from frame base) -> role
        # slot 0 = saved old frame pointer, slot 1 = saved return address
        self.next_slot = 2
        self.var_slots: Dict[str, int] = {}       # scalar/local var -> slot index
        self.array_slots: Dict[str, Tuple[int, int]] = {}  # name -> (slot, size)
        self.temp_slots: List[int] = []           # reusable temp slot pool
        self.temp_in_use = 0
        self.max_temps = 0

    # -- slot allocation --------------------------------------------------
    def alloc_var(self, name: str) -> int:
        if name in self.var_slots or name in self.array_slots:
            return self.var_slots.get(name, -1)
        s = self.next_slot
        self.next_slot += 1
        self.var_slots[name] = s
        return s

    def alloc_array(self, name: str, size: int) -> int:
        s = self.next_slot
        self.next_slot += size
        self.array_slots[name] = (s, size)
        return s

    def push_temp(self) -> int:
        if self.temp_in_use < len(self.temp_slots):
            slot = self.temp_slots[self.temp_in_use]
        else:
            slot = self.next_slot + len(self.temp_slots)
            self.temp_slots.append(slot)
        self.temp_in_use += 1
        self.max_temps = max(self.max_temps, self.temp_in_use)
        return slot

    def pop_temp(self) -> None:
        self.temp_in_use -= 1

    def frame_slots(self) -> int:
        """Total slots in the frame (fixed layout + temps)."""
        return self.next_slot + self.max_temps

    def frame_bytes(self) -> int:
        return self.frame_slots() * self.slot_size


class CodeGenBase:
    # ── ISA policy knobs (overridden by subclasses) ─────────────────────
    isa_name = "base"
    slot_size = 4                # frame slot width in bytes
    frame_reg = ""               # reserved frame-pointer register name
    scratch_regs: List[str] = []  # scratch registers (acc + helpers)
    return_reg = ""              # ABI return-value register
    supports_recursion = True    # x86 overrides to False (no modelled stack)
    supports_multiple_functions = True

    # RV32I / this simulator has NO hardware multiply or divide. Subclasses
    # that lack them advertise it here; codegen then emits a software routine
    # for '*' and rejects '/' and '%' (documented limitation) unless the
    # subclass provides emit_mul/emit_div.
    has_hw_mul = False
    has_hw_div = False

    # Upper bound (bytes) for the file-scope global region. Defaults to the
    # reserved low region; x86 lowers it so globals can't collide with its
    # fixed frame base (EBP), which lives inside that region.
    global_region_limit = GLOBAL_REGION_TOP

    def __init__(self):
        self.lines: List[str] = []            # emitted asm lines (no labels stripped)
        self.source_map: List[dict] = []      # {asm_line, c_line}
        self._label_counter = 0
        self.funcs: Dict[str, ast.Function] = {}
        self.ctx: Optional[FunctionContext] = None
        self.main_ctx: Optional[FunctionContext] = None   # kept for symbols()
        self._cur_c_line = 0
        # File-scope globals: name -> byte address (slot_size stride so array
        # indexing, which scales by slot_size, lines up). Locals shadow these.
        self.global_scalars: Dict[str, int] = {}
        self.global_arrays: Dict[str, Tuple[int, int]] = {}   # name -> (addr, size)
        self._globals: List[ast.VarDecl] = []
        # Stack of (continue_label, break_label) for the enclosing loops.
        self._loop_stack: List[Tuple[str, str]] = []

    # ── emission plumbing ───────────────────────────────────────────────
    def emit(self, text: str, c_line: Optional[int] = None) -> None:
        """Append one asm line and record its source-map entry.

        ``text`` may be an instruction or a bare ``label:``. The 1-based asm
        line number is ``len(self.lines)`` after appending.
        """
        self.lines.append(text)
        cl = c_line if c_line is not None else self._cur_c_line
        if cl:
            self.source_map.append({"asm_line": len(self.lines), "c_line": cl})

    def comment(self, text: str) -> None:
        self.lines.append(f"; {text}")

    def new_label(self, base: str) -> str:
        # The project assembler only accepts labels matching [A-Za-z_]\w*, so
        # we use an 'L' prefix (no leading dot) to stay valid.
        self._label_counter += 1
        return f"L_{base}_{self._label_counter}"

    # ── top-level driver ────────────────────────────────────────────────
    def generate(self, program: ast.Program) -> str:
        self.funcs = {f.name: f for f in program.functions}
        if "main" not in self.funcs:
            raise CompilerError("program must define an 'int main()' function")

        if not self.supports_multiple_functions and len(self.funcs) > 1:
            raise CompilerError(
                f"the {self.isa_name} backend supports only a single function "
                f"(no CALL/RET stack is modelled); found "
                f"{len(self.funcs)} functions")

        self._detect_recursion(program)
        self._layout_globals(program)

        self.emit_program_prologue()
        # Emit main first, then the rest (deterministic order).
        ordered = [self.funcs["main"]] + [f for n, f in self.funcs.items()
                                          if n != "main"]
        for fn in ordered:
            self._gen_function(fn)
        # Runtime helpers (__mul/__divmod) are compiler plumbing, not user
        # source — untag them (0 is falsy, so emit() skips the source-map
        # entry) rather than let them inherit the last statement's stale
        # _cur_c_line. This keeps them invisible to source-level stepping:
        # their CALL SITE (inside a function body) still carries the real
        # C line, but stepping into a '*' or '/' won't wander into the
        # helper's internals — matches the UI's line-by-line debugger.
        self._cur_c_line = 0
        self.emit_runtime()
        self._postprocess()
        return "\n".join(self.lines) + "\n"

    def _postprocess(self) -> None:
        """Optional ISA-specific peephole over the emitted lines.

        Subclasses may rewrite ``self.lines`` in place (e.g. inserting hazard
        NOPs). If lines are inserted/removed, they MUST also rebuild
        ``self.source_map`` — use :meth:`_rebuild_source_map_from` with a list
        of (new_line_index, c_line) pairs, or leave both untouched.
        """
        return

    def _reindex_source_map(self, insert_map) -> None:
        """Rebuild source_map after inserting lines.

        ``insert_map`` maps each ORIGINAL 1-based asm line number to the number
        of NOP lines inserted immediately BEFORE it. Every source-map entry's
        ``asm_line`` is shifted by the cumulative count of insertions at or
        before it.
        """
        # cumulative insertions before each original line
        shifted = []
        for entry in self.source_map:
            orig = entry["asm_line"]
            shift = sum(cnt for ln, cnt in insert_map.items() if ln <= orig)
            shifted.append({"asm_line": orig + shift, "c_line": entry["c_line"]})
        self.source_map = shifted

    def _detect_recursion(self, program: ast.Program) -> None:
        """Reject recursion for backends that cannot model a call stack."""
        if self.supports_recursion:
            return

        def calls_in(node) -> set:
            found = set()
            self._walk_calls(node, found)
            return found

        for fn in program.functions:
            callees = calls_in(fn.body)
            if fn.name in callees:
                raise CompilerError(
                    f"recursion is not supported on the {self.isa_name} backend "
                    f"(function '{fn.name}' calls itself; no CALL/RET stack is "
                    f"modelled)", fn.line, 1)
            if callees & set(self.funcs):
                # any inter-function call on a no-stack backend is unsupported
                other = sorted(callees & set(self.funcs))
                raise CompilerError(
                    f"function calls are not supported on the {self.isa_name} "
                    f"backend (function '{fn.name}' calls {other}); no CALL/RET "
                    f"stack is modelled", fn.line, 1)

    def _walk_calls(self, node, found: set) -> None:
        if isinstance(node, ast.Call):
            found.add(node.name)
        for child in self._children(node):
            self._walk_calls(child, found)

    def _layout_globals(self, program: ast.Program) -> None:
        """Assign each file-scope global a fixed byte address in the low global
        region. Addresses use the ISA slot_size stride so array indexing (which
        scales by slot_size) resolves correctly."""
        off = 0
        for g in program.globals:
            if g.name in self.global_scalars or g.name in self.global_arrays:
                raise CompilerError(f"redeclaration of global '{g.name}'", g.line)
            if g.is_array:
                self.global_arrays[g.name] = (off, g.size)
                off += g.size * self.slot_size
            else:
                self.global_scalars[g.name] = off
                off += self.slot_size
        if off > self.global_region_limit:
            raise CompilerError(
                f"global data ({off} bytes) exceeds the {self.global_region_limit}"
                f"-byte global region for the {self.isa_name} backend; "
                f"use fewer/smaller globals")
        self._globals = list(program.globals)

    def _emit_global_inits(self) -> None:
        """Emit initializers for file-scope globals at the top of main. Data
        memory starts zeroed, so only explicit initializers need stores."""
        if not self._globals:
            return
        self.comment("initialize globals")
        for g in self._globals:
            if g.is_array:
                if not g.init_list:
                    continue
                for i, elem in enumerate(g.init_list):
                    self._gen_assign(ast.Assign(
                        ast.Index(ast.Var(g.name, line=g.line),
                                  ast.Number(i, line=g.line), line=g.line),
                        elem, line=g.line))
            elif g.init is not None:
                self._gen_assign(ast.Assign(ast.Var(g.name, line=g.line),
                                            g.init, line=g.line))

    @staticmethod
    def _children(node) -> list:
        out = []
        for attr in ("functions", "statements", "args", "init_list"):
            if hasattr(node, attr) and getattr(node, attr) is not None:
                out.extend(getattr(node, attr))
        for attr in ("body", "then_body", "else_body", "cond", "value", "init",
                     "step", "left", "right", "operand", "array", "index",
                     "target", "expr", "then_expr", "else_expr"):
            v = getattr(node, attr, None)
            if v is not None and hasattr(v, "to_dict"):
                out.append(v)
        return out

    # ── per-function codegen ────────────────────────────────────────────
    def _gen_function(self, fn: ast.Function) -> None:
        ctx = FunctionContext(fn.name, fn.params, self.slot_size)
        if fn.name == "main":
            self.main_ctx = ctx               # symbols() reads it post-generate
        # Pre-scan to allocate slots for params, locals and arrays so the frame
        # size is known before we place them; params first, in order.
        for p in fn.params:
            ctx.alloc_var(p)
        self._prescan_decls(fn.body, ctx)
        self.ctx = ctx

        # Temp slots are allocated on demand during the body walk, so the final
        # frame size (which the prologue/epilogue bake into sp adjustments and
        # slot offsets) is not known until the whole body has been generated.
        # Do a throwaway "dry run" first to discover ctx.max_temps, then emit
        # for real with a stable frame size. Both passes hit the same ctx so
        # slot assignments are identical; only max_temps carries over.
        saved_lines, saved_map = self.lines, self.source_map
        self.lines, self.source_map = [], []
        self._emit_function_body(fn, ctx)      # dry run (discarded)
        self.lines, self.source_map = saved_lines, saved_map

        self._emit_function_body(fn, ctx)      # real emission

    def _emit_function_body(self, fn: ast.Function, ctx: FunctionContext) -> None:
        # reset transient temp bookkeeping (max_temps is preserved across the
        # dry run so the frame size is stable, but the in-use counter resets).
        ctx.temp_in_use = 0

        self._cur_c_line = fn.line
        self.emit(f"{self._func_label(fn.name)}:", fn.line)
        self.emit_prologue(ctx)
        # Move incoming argument registers into their param frame slots.
        self.emit_store_params(ctx)

        # Globals are initialized once, at the start of main (execution begins
        # there, so this runs before any function body / call).
        if fn.name == "main":
            self._emit_global_inits()

        self._gen_block(fn.body)

        # Fallthrough return (return 0 by convention for main / void).
        self.emit_epilogue_return_zero(ctx)

    def _prescan_decls(self, block: ast.Block, ctx: FunctionContext) -> None:
        """Allocate frame slots for every declared local/array in the function.

        Declarations are function-scoped here (no block shadowing) which keeps
        the frame flat and the codegen transparent.
        """
        for stmt in self._iter_decls(block):
            if isinstance(stmt, ast.VarDecl):
                if stmt.is_array:
                    if stmt.name in ctx.array_slots or stmt.name in ctx.var_slots:
                        raise CompilerError(f"redeclaration of '{stmt.name}'",
                                            stmt.line, 1)
                    ctx.alloc_array(stmt.name, stmt.size)
                else:
                    if stmt.name in ctx.var_slots or stmt.name in ctx.array_slots:
                        # redeclare is harmless for a scalar (same slot reused)
                        continue
                    ctx.alloc_var(stmt.name)

    def _iter_decls(self, node):
        """Yield every VarDecl anywhere in the function body."""
        if isinstance(node, ast.VarDecl):
            yield node
        for child in self._children(node):
            yield from self._iter_decls(child)

    # ── statements ──────────────────────────────────────────────────────
    def _gen_block(self, block: ast.Block) -> None:
        for stmt in block.statements:
            self._gen_stmt(stmt)

    def _gen_stmt(self, stmt) -> None:
        self._cur_c_line = getattr(stmt, "line", self._cur_c_line)

        if isinstance(stmt, ast.VarDecl):
            if stmt.is_array:
                # Slot already reserved in prescan. Emit an initializer if one
                # was given: store each element, zero-filling the tail (C
                # semantics: any initializer zeroes the remaining elements).
                if stmt.init_list is not None:
                    name = stmt.name
                    for i in range(stmt.size):
                        elem = (stmt.init_list[i] if i < len(stmt.init_list)
                                else ast.Number(0, line=stmt.line))
                        self._gen_assign(ast.Assign(
                            ast.Index(ast.Var(name, line=stmt.line),
                                      ast.Number(i, line=stmt.line), line=stmt.line),
                            elem, line=stmt.line))
                return
            if stmt.init is not None:
                self._gen_expr(stmt.init)        # -> accumulator
                slot = self.ctx.var_slots[stmt.name]
                self.emit_store_slot(slot)       # acc -> slot
            return

        if isinstance(stmt, ast.Break):
            if not self._loop_stack:
                raise CompilerError("'break' outside a loop", stmt.line)
            self.emit_jump(self._loop_stack[-1][1])
            return

        if isinstance(stmt, ast.Continue):
            if not self._loop_stack:
                raise CompilerError("'continue' outside a loop", stmt.line)
            self.emit_jump(self._loop_stack[-1][0])
            return

        if isinstance(stmt, ast.ExprStmt):
            self._gen_expr(stmt.expr)
            return

        if isinstance(stmt, ast.Block):
            self._gen_block(stmt)
            return

        if isinstance(stmt, ast.Return):
            if stmt.value is not None:
                self._gen_expr(stmt.value)       # -> accumulator
                self.emit_move_acc_to_return()
            else:
                self.emit_zero_return()
            self.emit_epilogue(self.ctx)
            self.emit_return()
            return

        if isinstance(stmt, ast.If):
            self._gen_if(stmt)
            return

        if isinstance(stmt, ast.While):
            self._gen_while(stmt)
            return

        if isinstance(stmt, ast.For):
            self._gen_for(stmt)
            return

        raise CompilerError(f"unsupported statement {type(stmt).__name__}",
                            getattr(stmt, "line", None))

    def _gen_if(self, stmt: ast.If) -> None:
        else_label = self.new_label("else")
        end_label = self.new_label("endif")
        # Evaluate condition; branch to else/end when false (acc == 0).
        self._gen_expr(stmt.cond)
        self.emit_branch_if_false(else_label if stmt.else_body else end_label)
        self._gen_block(stmt.then_body)
        if stmt.else_body:
            self.emit_jump(end_label)
            self.emit(f"{else_label}:")
            self._gen_block(stmt.else_body)
        self.emit(f"{end_label}:")

    def _gen_while(self, stmt: ast.While) -> None:
        top = self.new_label("while")
        end = self.new_label("endwhile")
        self.emit(f"{top}:")
        self._gen_expr(stmt.cond)
        self.emit_branch_if_false(end)
        self._loop_stack.append((top, end))   # continue -> re-test the condition
        self._gen_block(stmt.body)
        self._loop_stack.pop()
        self.emit_jump(top)
        self.emit(f"{end}:")

    def _gen_for(self, stmt: ast.For) -> None:
        top = self.new_label("for")
        step_lbl = self.new_label("forstep")
        end = self.new_label("endfor")
        if stmt.init is not None:
            self._gen_stmt(stmt.init if isinstance(stmt.init, ast.VarDecl)
                           else stmt.init)
        self.emit(f"{top}:")
        if stmt.cond is not None:
            self._gen_expr(stmt.cond)
            self.emit_branch_if_false(end)
        self._loop_stack.append((step_lbl, end))  # continue -> run the step first
        self._gen_block(stmt.body)
        self._loop_stack.pop()
        self.emit(f"{step_lbl}:")
        if stmt.step is not None:
            self._gen_expr(stmt.step)
        self.emit_jump(top)
        self.emit(f"{end}:")

    # ── expressions -> accumulator register ─────────────────────────────
    def _gen_expr(self, expr) -> None:
        self._cur_c_line = getattr(expr, "line", self._cur_c_line)

        if isinstance(expr, ast.Number):
            self.emit_load_const(expr.value)
            return

        if isinstance(expr, ast.Var):
            self._gen_load_var(expr)
            return

        if isinstance(expr, ast.Index):
            self._gen_load_index(expr)
            return

        if isinstance(expr, ast.Assign):
            self._gen_assign(expr)
            return

        if isinstance(expr, ast.Unary):
            self._gen_unary(expr)
            return

        if isinstance(expr, ast.Binary):
            self._gen_binary(expr)
            return

        if isinstance(expr, ast.Call):
            self._gen_call(expr)
            return

        if isinstance(expr, ast.Ternary):
            self._gen_ternary(expr)
            return

        if isinstance(expr, ast.IncDec):
            self._gen_incdec(expr)
            return

        raise CompilerError(f"unsupported expression {type(expr).__name__}",
                            getattr(expr, "line", None))

    def _gen_ternary(self, expr: ast.Ternary) -> None:
        else_lbl = self.new_label("tern_else")
        end_lbl = self.new_label("tern_end")
        self._gen_expr(expr.cond)
        self.emit_branch_if_false(else_lbl)
        self._gen_expr(expr.then_expr)       # -> accumulator
        self.emit_jump(end_lbl)
        self.emit(f"{else_lbl}:")
        self._gen_expr(expr.else_expr)       # -> accumulator
        self.emit(f"{end_lbl}:")

    def _gen_incdec(self, expr: ast.IncDec) -> None:
        # ++x / --x reuse the assignment lowering: x = x (+/-) 1. Assign leaves
        # the new value in the accumulator (prefix result). For postfix we save
        # the old value first and restore it as the expression's result.
        one = ast.Number(1, line=expr.line)
        update = ast.Assign(expr.target,
                            ast.Binary(expr.op, expr.target, one, line=expr.line),
                            line=expr.line)
        if expr.prefix:
            self._gen_assign(update)         # acc = new value
        else:
            self._gen_expr(expr.target)      # acc = old value
            t = self.ctx.push_temp()
            self.emit_store_slot(t)
            self._gen_assign(update)         # perform the update
            self.emit_load_slot(t)           # acc = old value
            self.ctx.pop_temp()

    def _gen_load_var(self, expr: ast.Var) -> None:
        name = expr.name
        if name in self.ctx.var_slots:
            self.emit_load_slot(self.ctx.var_slots[name])
        elif name in self.ctx.array_slots:
            # bare local array name decays to its base address
            slot, _ = self.ctx.array_slots[name]
            self.emit_load_slot_address(slot)
        elif name in self.global_scalars:
            self.emit_load_const(self.global_scalars[name])   # acc = &global
            self.emit_load_at_acc()                           # acc = *global
        elif name in self.global_arrays:
            # global array name decays to its (constant) base address
            self.emit_load_const(self.global_arrays[name][0])
        else:
            raise CompilerError(f"use of undeclared variable '{name}'", expr.line)

    def _gen_load_index(self, expr: ast.Index) -> None:
        # Compute the element ADDRESS, then load a word from it.
        self._gen_element_address(expr)          # acc = &elem
        self.emit_load_at_acc()                  # acc = mem[acc]

    def _gen_element_address(self, expr: ast.Index) -> None:
        """Leave the byte address of array element in the accumulator."""
        # base address
        tmp = self.ctx.push_temp()
        self._gen_expr(expr.array)               # acc = base address (pointer/array)
        self.emit_store_slot(tmp)                # spill base
        self._gen_expr(expr.index)               # acc = index
        self.emit_scale_index_word()             # acc = index * slot_size(word=4)
        self.emit_add_slot_to_acc(tmp)           # acc = base + index*4
        self.ctx.pop_temp()

    def _gen_assign(self, expr: ast.Assign) -> None:
        target = expr.target
        if isinstance(target, ast.Var):
            name = target.name
            if name in self.ctx.var_slots:
                self._gen_expr(expr.value)
                self.emit_store_slot(self.ctx.var_slots[name])
                return
            if name in self.global_scalars:
                # store acc at the global's fixed address (via a temp holding it)
                addr_tmp = self.ctx.push_temp()
                self.emit_load_const(self.global_scalars[name])
                self.emit_store_slot(addr_tmp)
                self._gen_expr(expr.value)
                self.emit_store_at_slot_addr(addr_tmp)
                self.ctx.pop_temp()
                return
            if name in self.ctx.array_slots or name in self.global_arrays:
                raise CompilerError(f"cannot assign to array '{name}'",
                                    target.line)
            raise CompilerError(f"assignment to undeclared variable '{name}'",
                                target.line)

        if isinstance(target, ast.Index):
            # addr = &elem (spill), val = value, store val at addr
            addr_tmp = self.ctx.push_temp()
            self._gen_element_address(target)
            self.emit_store_slot(addr_tmp)
            self._gen_expr(expr.value)           # acc = value
            self.emit_store_at_slot_addr(addr_tmp)  # mem[[addr_tmp]] = acc
            self.ctx.pop_temp()
            return

        if isinstance(target, ast.Unary) and target.op == "*":
            addr_tmp = self.ctx.push_temp()
            self._gen_expr(target.operand)       # acc = pointer
            self.emit_store_slot(addr_tmp)
            self._gen_expr(expr.value)
            self.emit_store_at_slot_addr(addr_tmp)
            self.ctx.pop_temp()
            return

        raise CompilerError("invalid assignment target", expr.line)

    def _gen_unary(self, expr: ast.Unary) -> None:
        op = expr.op
        if op == "-":
            self._gen_expr(expr.operand)
            self.emit_negate()
            return
        if op == "!":
            self._gen_expr(expr.operand)
            self.emit_logical_not()
            return
        if op == "*":
            self._gen_expr(expr.operand)         # acc = address
            self.emit_load_at_acc()              # acc = mem[acc]
            return
        if op == "&":
            self._gen_address_of(expr.operand)
            return
        raise CompilerError(f"unsupported unary operator '{op}'", expr.line)

    def _gen_address_of(self, operand) -> None:
        if isinstance(operand, ast.Var):
            name = operand.name
            if name in self.ctx.var_slots:
                self.emit_load_slot_address(self.ctx.var_slots[name])
                return
            if name in self.ctx.array_slots:
                slot, _ = self.ctx.array_slots[name]
                self.emit_load_slot_address(slot)
                return
            if name in self.global_scalars:
                self.emit_load_const(self.global_scalars[name])
                return
            if name in self.global_arrays:
                self.emit_load_const(self.global_arrays[name][0])
                return
            raise CompilerError(f"cannot take address of undeclared '{name}'",
                                operand.line)
        if isinstance(operand, ast.Index):
            self._gen_element_address(operand)
            return
        raise CompilerError("'&' requires a variable or array element",
                            getattr(operand, "line", None))

    def _gen_binary(self, expr: ast.Binary) -> None:
        op = expr.op

        # Short-circuit logical operators.
        if op == "&&":
            self._gen_logical_and(expr)
            return
        if op == "||":
            self._gen_logical_or(expr)
            return

        # Evaluate left, spill to temp, evaluate right into acc, combine.
        tmp = self.ctx.push_temp()
        self._gen_expr(expr.left)
        self.emit_store_slot(tmp)
        self._gen_expr(expr.right)               # acc = right
        # acc = (slot=left) OP (acc=right)
        self._emit_binary_op(op, tmp, expr)
        self.ctx.pop_temp()

    def _emit_binary_op(self, op: str, left_slot: int, expr) -> None:
        if op == "+":
            self.emit_add_slot_to_acc(left_slot)
        elif op == "-":
            self.emit_sub_acc_from_slot(left_slot)   # acc = slot - acc
        elif op == "*":
            self._emit_mul(left_slot, expr)
        elif op == "/":
            self._emit_div(left_slot, expr, want_rem=False)
        elif op == "%":
            self._emit_div(left_slot, expr, want_rem=True)
        elif op in ("<", "<=", ">", ">=", "==", "!="):
            self.emit_compare(op, left_slot)
        elif op == "<<":
            self.emit_shift("<<", left_slot)
        elif op == ">>":
            self.emit_shift(">>", left_slot)
        elif op in ("&", "|", "^"):
            self.emit_bitwise(op, left_slot)
        else:
            raise CompilerError(f"unsupported binary operator '{op}'",
                                getattr(expr, "line", None))

    def _emit_mul(self, left_slot: int, expr) -> None:
        if self.has_hw_mul:
            self.emit_mul(left_slot)
        else:
            self.emit_soft_mul(left_slot)

    def _emit_div(self, left_slot: int, expr, want_rem: bool) -> None:
        if self.has_hw_div:
            self.emit_div(left_slot, want_rem)
        else:
            self.emit_soft_div(left_slot, want_rem)

    def _gen_logical_and(self, expr: ast.Binary) -> None:
        false_lbl = self.new_label("and_false")
        end_lbl = self.new_label("and_end")
        self._gen_expr(expr.left)
        self.emit_branch_if_false(false_lbl)
        self._gen_expr(expr.right)
        self.emit_branch_if_false(false_lbl)
        self.emit_load_const(1)
        self.emit_jump(end_lbl)
        self.emit(f"{false_lbl}:")
        self.emit_load_const(0)
        self.emit(f"{end_lbl}:")

    def _gen_logical_or(self, expr: ast.Binary) -> None:
        true_lbl = self.new_label("or_true")
        end_lbl = self.new_label("or_end")
        self._gen_expr(expr.left)
        self.emit_branch_if_true(true_lbl)
        self._gen_expr(expr.right)
        self.emit_branch_if_true(true_lbl)
        self.emit_load_const(0)
        self.emit_jump(end_lbl)
        self.emit(f"{true_lbl}:")
        self.emit_load_const(1)
        self.emit(f"{end_lbl}:")

    def _gen_call(self, expr: ast.Call) -> None:
        # Builtin: print(expr) — evaluate into the accumulator and store it at
        # PRINT_ADDR (the UI terminal replays those stores as console output).
        # A user-defined function named 'print' shadows the builtin.
        if expr.name == "print" and expr.name not in self.funcs:
            if len(expr.args) != 1:
                raise CompilerError("print() takes exactly one argument",
                                    expr.line)
            self._gen_expr(expr.args[0])      # value stays in the accumulator
            self.emit_print()
            return
        if expr.name not in self.funcs:
            raise CompilerError(f"call to undefined function '{expr.name}'",
                                expr.line)
        callee = self.funcs[expr.name]
        if len(expr.args) != len(callee.params):
            raise CompilerError(
                f"function '{expr.name}' expects {len(callee.params)} "
                f"argument(s), got {len(expr.args)}", expr.line)
        self.emit_call(expr, callee)

    # ── label helpers subclasses share ──────────────────────────────────
    def _func_label(self, name: str) -> str:
        return f"func_{name}"

    # ── debugger symbol table ───────────────────────────────────────────
    def symbols(self) -> List[dict]:
        """Static symbol table for MAIN's frame, for the UI debugger.

        Only main is covered: its frame base is statically known on every
        backend (the first frame off STACK_TOP, or x86's fixed EBP), so each
        local has a fixed byte address for the whole run. Callee frames move
        with the call depth and are not tracked. Call after generate().
        """
        ctx = self.main_ctx
        out = []
        # File-scope globals have fixed addresses on every backend.
        for name, addr in sorted(self.global_scalars.items(), key=lambda kv: kv[1]):
            out.append({"name": name, "kind": "global", "addr": addr,
                        "size": 1, "stride": self.slot_size, "location": "global"})
        for name, (addr, size) in sorted(self.global_arrays.items(),
                                         key=lambda kv: kv[1][0]):
            out.append({"name": name, "kind": "global-array", "addr": addr,
                        "size": size, "stride": self.slot_size, "location": "global"})
        if ctx is None:
            return out
        base = self.main_frame_base(ctx)
        if base is None:
            return out
        for name, slot in sorted(ctx.var_slots.items(), key=lambda kv: kv[1]):
            out.append({
                "name": name,
                "kind": "param" if name in ctx.params else "var",
                "addr": base + slot * ctx.slot_size,
                "size": 1,
                "stride": ctx.slot_size,
                "location": self.slot_location(slot),
            })
        for name, (slot, size) in sorted(ctx.array_slots.items(),
                                         key=lambda kv: kv[1][0]):
            out.append({
                "name": name,
                "kind": "array",
                "addr": base + slot * ctx.slot_size,
                "size": size,
                "stride": ctx.slot_size,
                "location": self.slot_location(slot),
            })
        return out

    def main_frame_base(self, ctx: FunctionContext) -> Optional[int]:
        """Absolute byte address of main's frame base (None = unknown)."""
        return None

    def slot_location(self, slot: int) -> str:
        """Human-readable operand for a frame slot (e.g. '8(sp)')."""
        return ""

    # =====================================================================
    # ISA primitives — subclasses MUST implement all of these.
    # The "accumulator" is scratch_regs[0]. "slot N" is frame slot N,
    # addressed off the frame register.
    # =====================================================================
    def emit_program_prologue(self) -> None:
        raise NotImplementedError

    def emit_runtime(self) -> None:
        raise NotImplementedError

    def emit_prologue(self, ctx: FunctionContext) -> None:
        raise NotImplementedError

    def emit_store_params(self, ctx: FunctionContext) -> None:
        raise NotImplementedError

    def emit_epilogue(self, ctx: FunctionContext) -> None:
        raise NotImplementedError

    def emit_epilogue_return_zero(self, ctx: FunctionContext) -> None:
        raise NotImplementedError

    def emit_return(self) -> None:
        raise NotImplementedError

    def emit_call(self, expr: ast.Call, callee: ast.Function) -> None:
        raise NotImplementedError

    def emit_load_const(self, value: int) -> None:
        raise NotImplementedError

    def emit_load_slot(self, slot: int) -> None:
        raise NotImplementedError

    def emit_store_slot(self, slot: int) -> None:
        raise NotImplementedError

    def emit_load_slot_address(self, slot: int) -> None:
        raise NotImplementedError

    def emit_load_at_acc(self) -> None:
        raise NotImplementedError

    def emit_store_at_slot_addr(self, addr_slot: int) -> None:
        raise NotImplementedError

    def emit_scale_index_word(self) -> None:
        raise NotImplementedError

    def emit_add_slot_to_acc(self, slot: int) -> None:
        raise NotImplementedError

    def emit_sub_acc_from_slot(self, slot: int) -> None:
        raise NotImplementedError

    def emit_negate(self) -> None:
        raise NotImplementedError

    def emit_logical_not(self) -> None:
        raise NotImplementedError

    def emit_compare(self, op: str, left_slot: int) -> None:
        raise NotImplementedError

    def emit_shift(self, op: str, left_slot: int) -> None:
        raise NotImplementedError

    def emit_bitwise(self, op: str, left_slot: int) -> None:
        raise NotImplementedError

    def emit_branch_if_false(self, label: str) -> None:
        raise NotImplementedError

    def emit_branch_if_true(self, label: str) -> None:
        raise NotImplementedError

    def emit_jump(self, label: str) -> None:
        raise NotImplementedError

    def emit_move_acc_to_return(self) -> None:
        raise NotImplementedError

    def emit_zero_return(self) -> None:
        raise NotImplementedError

    def emit_print(self) -> None:
        """Store the accumulator at PRINT_ADDR (the console word)."""
        raise NotImplementedError

    # multiply / divide — default to software; HW backends override
    def emit_mul(self, left_slot: int) -> None:
        raise NotImplementedError

    def emit_div(self, left_slot: int, want_rem: bool) -> None:
        raise NotImplementedError

    def emit_soft_mul(self, left_slot: int) -> None:
        raise NotImplementedError

    def emit_soft_div(self, left_slot: int, want_rem: bool) -> None:
        raise NotImplementedError
