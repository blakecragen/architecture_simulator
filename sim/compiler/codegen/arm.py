"""
ARM AArch64 (A64) code generator for Core-C.

Emits the project's own ARM mnemonics (consumed unchanged by
``sim/assembler/arm.py``). The assembler exposes a deliberately small subset —
ADD/SUB/AND/ORR/EOR (register), ADD/SUB #imm12, MOVZ, CMP/SUBS, LDR/STR,
B/BL/B.cond/CBZ/CBNZ, RET — and notably **no shift or set-less-than
instructions**, so this backend works entirely with those.

Register / calling convention:
  * ``X28``      reserved frame pointer; frames grow DOWN (no usable HW SP —
                 SP aliases XZR in this simulator).
  * ``X9``       accumulator (expression result).
  * ``X10 X11``  scratch.
  * ``X0..X7``   argument passing; ``X0`` is the return value.
  * ``X30``      link register (saved/restored per frame; BL sets it).
  * ``XZR`` (31) reads zero — used to synthesize MOV (``ADD Xd,Xn,XZR``) and
                 negation (``SUB Xd,XZR,Xn``).

Frame slots are 8 bytes wide (LDR/STR scaled offset must be a multiple of 8).
There is no hardware multiply/divide and no shift instruction, so ``*`` is
repeated addition, ``/`` and ``%`` are repeated subtraction (both sign-correct),
and array index scaling uses ADD-doubling.
"""
from __future__ import annotations

from .base import (CodeGenBase, FunctionContext, PRINT_ADDR, STACK_TOP,
                   STACK_LIMIT)
from .. import ast
from ..errors import CompilerError

FP = "X28"       # frame pointer
ACC = "X9"       # accumulator
T1 = "X10"
T2 = "X11"
ZR = "XZR"
MAX_ARGS = 8

# ARM condition mnemonics for each comparison operator (left OP right).
_COND = {"<": "LT", ">": "GT", "<=": "LE", ">=": "GE", "==": "EQ", "!=": "NE"}


class ARMCodeGen(CodeGenBase):
    isa_name = "arm"
    slot_size = 8                # LDR/STR scaled offset must be multiple of 8
    frame_reg = FP
    return_reg = "X0"
    supports_recursion = True
    supports_multiple_functions = True
    has_hw_mul = False
    has_hw_div = False

    def __init__(self):
        super().__init__()
        self._need_mul = False
        self._need_divmod = False

    # ── slot addressing ─────────────────────────────────────────────────
    def _slot_off(self, slot: int) -> int:
        return slot * self.slot_size

    def _check_frame(self, ctx: FunctionContext) -> None:
        if STACK_TOP - ctx.frame_bytes() < STACK_LIMIT:
            raise CompilerError(
                f"function '{ctx.name}' frame ({ctx.frame_bytes()} bytes) exceeds "
                f"the software stack region; reduce locals/arrays")

    # ── constant materialization ────────────────────────────────────────
    def emit_load_imm_reg(self, reg: str, value: int) -> None:
        """Load a 32-bit constant into ``reg`` using MOVZ (+ chained high half),
        negating afterwards for negative values (MOVZ is non-negative only)."""
        neg = value < 0
        v = (-value if neg else value) & 0xFFFFFFFF
        low = v & 0xFFFF
        high = (v >> 16) & 0xFFFF
        self.emit(f"MOVZ {reg}, #{low}")
        if high:
            # MOVZ can't OR in a high half; build it in a scratch and add.
            self.emit(f"MOVZ {T2}, #{high << 16}")
            self.emit(f"ADD {reg}, {reg}, {T2}")
        if neg:
            self.emit(f"SUB {reg}, {ZR}, {reg}")

    def emit_load_const(self, value: int) -> None:
        self.emit_load_imm_reg(ACC, value)

    # ── program prologue / runtime ──────────────────────────────────────
    def emit_program_prologue(self) -> None:
        self.comment("Core-C -> ARM AArch64 (compiled)")
        self.comment(f"software stack base X28 = {STACK_TOP}")
        self.emit_load_imm_reg(FP, STACK_TOP)
        self.emit("BL func_main")
        self.emit("halt:")
        self.emit("B halt")

    def emit_runtime(self) -> None:
        if self._need_mul:
            self._emit_mul_routine()
        if self._need_divmod:
            self._emit_divmod_routine()

    # ── prologue / epilogue ─────────────────────────────────────────────
    def emit_prologue(self, ctx: FunctionContext) -> None:
        self._check_frame(ctx)
        fb = ctx.frame_bytes()
        # X28 -= frame_bytes (SUB #imm needs non-negative -> ok) ; save X30
        self.emit(f"SUB {FP}, {FP}, #{fb}")
        self.emit(f"STR X30, [{FP}, #8]")        # slot 1 = return address

    def emit_store_params(self, ctx: FunctionContext) -> None:
        if len(ctx.params) > MAX_ARGS:
            raise CompilerError(
                f"function '{ctx.name}' has {len(ctx.params)} params; the "
                f"ARM backend supports at most {MAX_ARGS}")
        for i, p in enumerate(ctx.params):
            slot = ctx.var_slots[p]
            self.emit(f"STR X{i}, [{FP}, #{self._slot_off(slot)}]")

    def emit_epilogue(self, ctx: FunctionContext) -> None:
        fb = ctx.frame_bytes()
        self.emit(f"LDR X30, [{FP}, #8]")
        self.emit(f"ADD {FP}, {FP}, #{fb}")

    def emit_epilogue_return_zero(self, ctx: FunctionContext) -> None:
        self.emit(f"ADD X0, {ZR}, {ZR}")         # X0 = 0
        self.emit_epilogue(ctx)
        self.emit_return()

    def emit_return(self) -> None:
        self.emit("RET")

    # ── calls ────────────────────────────────────────────────────────────
    def emit_call(self, expr: ast.Call, callee: ast.Function) -> None:
        if len(expr.args) > MAX_ARGS:
            raise CompilerError(
                f"call to '{expr.name}' passes {len(expr.args)} args; max "
                f"{MAX_ARGS}", expr.line)
        arg_slots = []
        for a in expr.args:
            self._gen_expr(a)
            t = self.ctx.push_temp()
            self.emit(f"STR {ACC}, [{FP}, #{self._slot_off(t)}]")
            arg_slots.append(t)
        for i, t in enumerate(arg_slots):
            self.emit(f"LDR X{i}, [{FP}, #{self._slot_off(t)}]")
        for _ in arg_slots:
            self.ctx.pop_temp()
        self.emit(f"BL func_{expr.name}")
        self.emit(f"ADD {ACC}, X0, {ZR}")         # acc = result

    # ── slot load/store ─────────────────────────────────────────────────
    def emit_load_slot(self, slot: int) -> None:
        self.emit(f"LDR {ACC}, [{FP}, #{self._slot_off(slot)}]")

    def emit_store_slot(self, slot: int) -> None:
        self.emit(f"STR {ACC}, [{FP}, #{self._slot_off(slot)}]")

    def emit_load_slot_address(self, slot: int) -> None:
        # acc = FP + off (off is non-negative -> ADD #imm ok)
        self.emit(f"ADD {ACC}, {FP}, #{self._slot_off(slot)}")

    def emit_load_at_acc(self) -> None:
        # acc = mem[acc]; LDR needs a base register + #0
        self.emit(f"ADD {T1}, {ACC}, {ZR}")
        self.emit(f"LDR {ACC}, [{T1}, #0]")

    def emit_store_at_slot_addr(self, addr_slot: int) -> None:
        self.emit(f"LDR {T1}, [{FP}, #{self._slot_off(addr_slot)}]")
        self.emit(f"STR {ACC}, [{T1}, #0]")

    # ── address arithmetic (no shifts -> ADD-doubling) ──────────────────
    def emit_scale_index_word(self) -> None:
        # Array element stride is one 8-byte slot -> acc = index * 8.
        self.emit(f"ADD {ACC}, {ACC}, {ACC}")     # *2
        self.emit(f"ADD {ACC}, {ACC}, {ACC}")     # *4
        self.emit(f"ADD {ACC}, {ACC}, {ACC}")     # *8

    def emit_add_slot_to_acc(self, slot: int) -> None:
        self.emit(f"LDR {T1}, [{FP}, #{self._slot_off(slot)}]")
        self.emit(f"ADD {ACC}, {T1}, {ACC}")

    def emit_sub_acc_from_slot(self, slot: int) -> None:
        self.emit(f"LDR {T1}, [{FP}, #{self._slot_off(slot)}]")
        self.emit(f"SUB {ACC}, {T1}, {ACC}")      # acc = slot - acc

    # ── unary ─────────────────────────────────────────────────────────────
    def emit_negate(self) -> None:
        self.emit(f"SUB {ACC}, {ZR}, {ACC}")

    def emit_logical_not(self) -> None:
        # acc = (acc == 0) ? 1 : 0
        false_lbl = self.new_label("not0")
        end_lbl = self.new_label("notend")
        self.emit(f"CBZ {ACC}, {false_lbl}")      # acc==0 -> jump set-1
        self.emit(f"MOVZ {ACC}, #0")              # nonzero -> 0
        self.emit(f"B {end_lbl}")
        self.emit(f"{false_lbl}:")
        self.emit(f"MOVZ {ACC}, #1")
        self.emit(f"{end_lbl}:")

    # ── comparison (no SLT -> CMP + B.cond materialize 0/1) ─────────────
    def emit_compare(self, op: str, left_slot: int) -> None:
        cond = _COND[op]
        true_lbl = self.new_label("cmp_t")
        end_lbl = self.new_label("cmp_e")
        # T1 = left, T2 = right (acc). CMP T1, T2 sets flags for left OP right.
        self.emit(f"LDR {T1}, [{FP}, #{self._slot_off(left_slot)}]")
        self.emit(f"ADD {T2}, {ACC}, {ZR}")
        self.emit(f"CMP {T1}, {T2}")
        self.emit(f"B.{cond} {true_lbl}")
        self.emit(f"MOVZ {ACC}, #0")
        self.emit(f"B {end_lbl}")
        self.emit(f"{true_lbl}:")
        self.emit(f"MOVZ {ACC}, #1")
        self.emit(f"{end_lbl}:")

    # ── shifts: unsupported by the ARM assembler subset ─────────────────
    def emit_shift(self, op: str, left_slot: int) -> None:
        raise CompilerError(
            "shift operators (<< >>) are not supported on the ARM backend "
            "(the assembler exposes no shift instruction)")

    # ── bitwise: acc = slot OP acc ──────────────────────────────────────
    def emit_bitwise(self, op: str, left_slot: int) -> None:
        instr = {"&": "AND", "|": "ORR", "^": "EOR"}[op]
        self.emit(f"LDR {T1}, [{FP}, #{self._slot_off(left_slot)}]")
        self.emit(f"{instr} {ACC}, {T1}, {ACC}")

    # ── control flow ─────────────────────────────────────────────────────
    def emit_branch_if_false(self, label: str) -> None:
        self.emit(f"CBZ {ACC}, {label}")

    def emit_branch_if_true(self, label: str) -> None:
        self.emit(f"CBNZ {ACC}, {label}")

    def emit_jump(self, label: str) -> None:
        self.emit(f"B {label}")

    def emit_move_acc_to_return(self) -> None:
        self.emit(f"ADD X0, {ACC}, {ZR}")

    def emit_zero_return(self) -> None:
        self.emit(f"ADD X0, {ZR}, {ZR}")

    def emit_print(self) -> None:
        # STR needs a register base; materialize the console address in T1
        # (PRINT_ADDR is a multiple of 8, satisfying the scaled-offset rule).
        self.emit(f"MOVZ {T1}, #{PRINT_ADDR}")
        self.emit(f"STR {ACC}, [{T1}, #0]")

    # ── debugger symbols ─────────────────────────────────────────────────
    def main_frame_base(self, ctx: FunctionContext):
        return STACK_TOP - ctx.frame_bytes()

    def slot_location(self, slot: int) -> str:
        return f"[{FP}, #{self._slot_off(slot)}]"

    # ── multiply / divide via runtime routines ──────────────────────────
    def emit_soft_mul(self, left_slot: int) -> None:
        self._need_mul = True
        self.emit(f"LDR X0, [{FP}, #{self._slot_off(left_slot)}]")
        self.emit(f"ADD X1, {ACC}, {ZR}")
        self.emit("BL __mul")
        self.emit(f"ADD {ACC}, X0, {ZR}")

    def emit_soft_div(self, left_slot: int, want_rem: bool) -> None:
        self._need_divmod = True
        self.emit(f"LDR X0, [{FP}, #{self._slot_off(left_slot)}]")
        self.emit(f"ADD X1, {ACC}, {ZR}")
        self.emit("BL __divmod")
        src = "X1" if want_rem else "X0"
        self.emit(f"ADD {ACC}, {src}, {ZR}")

    # ── runtime routines (leaf; no frame, only X0..X6) ──────────────────
    def _emit_mul_routine(self) -> None:
        """__mul: X0 = X0 * X1 (low 32 bits) via repeated addition.

        Adds |X1| copies of X0, then negates if X1 was negative. No shifts.
        """
        self.comment("runtime: multiply via repeated addition")
        self.emit("__mul:")
        # X2 = product = 0 ; X3 = multiplicand = X0 ; X4 = |multiplier|
        self.emit(f"ADD X2, {ZR}, {ZR}")
        self.emit(f"ADD X3, X0, {ZR}")
        self.emit(f"ADD X4, X1, {ZR}")
        self.emit("MOVZ X5, #0")                  # X5 = negate flag
        # if multiplier < 0: X4 = -X4, X5 = 1
        self.emit(f"CMP X4, {ZR}")
        self.emit("B.GE __mul_loop")
        self.emit(f"SUB X4, {ZR}, X4")
        self.emit("MOVZ X5, #1")
        self.emit("__mul_loop:")
        self.emit("CBZ X4, __mul_done")
        self.emit("ADD X2, X2, X3")               # product += multiplicand
        self.emit("MOVZ X6, #1")
        self.emit("SUB X4, X4, X6")               # counter--
        self.emit("B __mul_loop")
        self.emit("__mul_done:")
        self.emit(f"ADD X0, X2, {ZR}")
        self.emit("CBZ X5, __mul_ret")
        self.emit(f"SUB X0, {ZR}, X0")            # apply sign
        self.emit("__mul_ret:")
        self.emit("RET")

    def _emit_divmod_routine(self) -> None:
        """__divmod: signed division via repeated subtraction.

        X0/X1 -> X0=quotient, X1=remainder. Truncates toward zero; remainder
        takes the dividend's sign (C semantics). Uses X0..X7, no frame, no
        shifts. Division by zero yields quotient 0, remainder 0.
        """
        self.comment("runtime: divide/modulo via repeated subtraction")
        self.emit("__divmod:")
        self.emit("CBZ X1, __dm_byzero")
        # X6 = dividend<0 flag, X7 = divisor<0 flag
        self.emit("MOVZ X6, #0")
        self.emit("MOVZ X7, #0")
        self.emit(f"CMP X0, {ZR}")
        self.emit("B.GE __dm_dd_pos")
        self.emit("MOVZ X6, #1")
        self.emit("__dm_dd_pos:")
        self.emit(f"CMP X1, {ZR}")
        self.emit("B.GE __dm_dv_pos")
        self.emit("MOVZ X7, #1")
        self.emit("__dm_dv_pos:")
        # X2 = |dividend|, X3 = |divisor|
        self.emit(f"ADD X2, X0, {ZR}")
        self.emit("CBZ X6, __dm_abs_dd")
        self.emit(f"SUB X2, {ZR}, X2")
        self.emit("__dm_abs_dd:")
        self.emit(f"ADD X3, X1, {ZR}")
        self.emit("CBZ X7, __dm_abs_dv")
        self.emit(f"SUB X3, {ZR}, X3")
        self.emit("__dm_abs_dv:")
        # X4 = quotient = 0 ; loop while X2 >= X3: X2 -= X3; X4++
        self.emit(f"ADD X4, {ZR}, {ZR}")
        self.emit("__dm_loop:")
        self.emit("CMP X2, X3")
        self.emit("B.LT __dm_done")               # |dividend| < |divisor| -> stop
        self.emit("SUB X2, X2, X3")
        self.emit("MOVZ X5, #1")
        self.emit("ADD X4, X4, X5")
        self.emit("B __dm_loop")
        self.emit("__dm_done:")
        # quotient = X4 (sign = X6 xor X7), remainder = X2 (sign = X6)
        self.emit(f"ADD X0, X4, {ZR}")
        self.emit(f"ADD X1, X2, {ZR}")
        # quotient sign
        self.emit("EOR X5, X6, X7")
        self.emit("CBZ X5, __dm_qpos")
        self.emit(f"SUB X0, {ZR}, X0")
        self.emit("__dm_qpos:")
        self.emit("CBZ X6, __dm_rpos")
        self.emit(f"SUB X1, {ZR}, X1")
        self.emit("__dm_rpos:")
        self.emit("RET")
        self.emit("__dm_byzero:")
        self.emit(f"ADD X0, {ZR}, {ZR}")
        self.emit(f"ADD X1, {ZR}, {ZR}")
        self.emit("RET")
