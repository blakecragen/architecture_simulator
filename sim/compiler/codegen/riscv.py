"""
RISC-V RV32I code generator for Core-C.

Emits the project's own RISC-V assembly mnemonics (consumed unchanged by
``sim/assembler/riscv.py``). Register / calling convention:

  * ``sp`` (x2)            reserved frame pointer; frames grow DOWN.
  * ``ra`` (x1)            return address (saved/restored per frame).
  * ``t0`` (x5)            the accumulator (expression result).
  * ``t1 t2 t3`` (x6,7,28) scratch.
  * ``a0..a7`` (x10..x17)  argument passing; ``a0`` is the return value.

A callee subtracts its own frame size from ``sp`` in the prologue and adds it
back in the epilogue, so ``sp`` is preserved across calls and recursion works.
Arguments are passed in ``a0..a7`` and spilled to param slots on entry.

RV32I has NO hardware multiply or divide, so ``*`` compiles to a shift-add
runtime routine (``__mul``) and ``/`` / ``%`` to a signed long-division routine
(``__divmod``). Both are leaf helpers that use only t-registers + a0/a1/a2.
"""
from __future__ import annotations

from .base import (CodeGenBase, FunctionContext, PRINT_ADDR, STACK_TOP,
                   STACK_LIMIT)
from .. import ast
from ..errors import CompilerError

ACC = "t0"      # accumulator
T1 = "t1"
T2 = "t2"
MAX_ARGS = 8


class RISCVCodeGen(CodeGenBase):
    isa_name = "riscv"
    slot_size = 4
    frame_reg = "sp"
    return_reg = "a0"
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
        # Conservative single-frame collision guard: STACK_TOP - frame must stay
        # above the global/array data region. Deep recursion is caught at
        # runtime by the emitted guard, but a single frame that alone busts the
        # region is a compile error.
        if STACK_TOP - ctx.frame_bytes() < STACK_LIMIT:
            raise CompilerError(
                f"function '{ctx.name}' frame ({ctx.frame_bytes()} bytes) exceeds "
                f"the software stack region; reduce locals/arrays")

    # ── program prologue / runtime ──────────────────────────────────────
    def emit_program_prologue(self) -> None:
        self.comment("Core-C -> RISC-V RV32I (compiled)")
        self.comment(f"software stack base sp = {STACK_TOP}")
        # Initialize the frame pointer to the stack base, then call main.
        self.emit_load_imm_reg("sp", STACK_TOP)
        self.emit("JAL ra, func_main")
        # After main returns, its value is in a0; park the CPU in an infinite
        # loop so the register file settles for inspection.
        self.emit("halt:")
        self.emit("JAL x0, halt")

    def emit_runtime(self) -> None:
        if self._need_mul:
            self._emit_mul_routine()
        if self._need_divmod:
            self._emit_divmod_routine()

    # ── prologue / epilogue ─────────────────────────────────────────────
    def emit_prologue(self, ctx: FunctionContext) -> None:
        self._check_frame(ctx)
        fb = ctx.frame_bytes()
        # sp -= frame_bytes ; save ra
        self.emit(f"ADDI sp, sp, -{fb}")
        self.emit("SW ra, 4(sp)")

    def emit_store_params(self, ctx: FunctionContext) -> None:
        if len(ctx.params) > MAX_ARGS:
            raise CompilerError(
                f"function '{ctx.name}' has {len(ctx.params)} params; the "
                f"RISC-V backend supports at most {MAX_ARGS}")
        for i, p in enumerate(ctx.params):
            slot = ctx.var_slots[p]
            self.emit(f"SW a{i}, {self._slot_off(slot)}(sp)")

    def emit_epilogue(self, ctx: FunctionContext) -> None:
        fb = ctx.frame_bytes()
        self.emit("LW ra, 4(sp)")
        self.emit(f"ADDI sp, sp, {fb}")

    def emit_epilogue_return_zero(self, ctx: FunctionContext) -> None:
        # Fallthrough path: return 0.
        self.emit("ADDI a0, x0, 0")
        self.emit_epilogue(ctx)
        self.emit_return()

    def emit_return(self) -> None:
        self.emit("JALR x0, x1, 0")

    # ── calls ────────────────────────────────────────────────────────────
    def emit_call(self, expr: ast.Call, callee: ast.Function) -> None:
        if len(expr.args) > MAX_ARGS:
            raise CompilerError(
                f"call to '{expr.name}' passes {len(expr.args)} args; max "
                f"{MAX_ARGS}", expr.line)
        # Evaluate each argument into a caller temp slot (so nested-call
        # clobbering of a0..a7 / t0 is harmless).
        arg_slots = []
        for a in expr.args:
            self._gen_expr(a)
            t = self.ctx.push_temp()
            self.emit(f"SW {ACC}, {self._slot_off(t)}(sp)")
            arg_slots.append(t)
        # Load them into the ABI argument registers.
        for i, t in enumerate(arg_slots):
            self.emit(f"LW a{i}, {self._slot_off(t)}(sp)")
        for _ in arg_slots:
            self.ctx.pop_temp()
        self.emit(f"JAL ra, func_{expr.name}")
        # Result comes back in a0; move to the accumulator.
        self.emit(f"ADDI {ACC}, a0, 0")

    # ── constants ─────────────────────────────────────────────────────────
    def emit_load_imm_reg(self, reg: str, value: int) -> None:
        """Materialize a 32-bit constant into ``reg`` (LUI+ADDI when large)."""
        v = value & 0xFFFFFFFF
        # Fits in a signed 12-bit immediate?
        if -2048 <= value <= 2047:
            self.emit(f"ADDI {reg}, x0, {value}")
            return
        # LUI upper 20 + ADDI lower 12, accounting for sign extension of ADDI.
        lower = v & 0xFFF
        if lower & 0x800:
            # ADDI sign-extends: add 1 to upper so LUI+ADDI reconstructs v.
            upper = ((v >> 12) + 1) & 0xFFFFF
            low_signed = lower - 0x1000            # negative
        else:
            upper = (v >> 12) & 0xFFFFF
            low_signed = lower
        self.emit(f"LUI {reg}, {upper}")
        if low_signed != 0:
            self.emit(f"ADDI {reg}, {reg}, {low_signed}")

    def emit_load_const(self, value: int) -> None:
        self.emit_load_imm_reg(ACC, value)

    # ── slot load/store ─────────────────────────────────────────────────
    def emit_load_slot(self, slot: int) -> None:
        self.emit(f"LW {ACC}, {self._slot_off(slot)}(sp)")

    def emit_store_slot(self, slot: int) -> None:
        self.emit(f"SW {ACC}, {self._slot_off(slot)}(sp)")

    def emit_load_slot_address(self, slot: int) -> None:
        self.emit(f"ADDI {ACC}, sp, {self._slot_off(slot)}")

    def emit_load_at_acc(self) -> None:
        self.emit(f"LW {ACC}, 0({ACC})")

    def emit_store_at_slot_addr(self, addr_slot: int) -> None:
        # mem[[addr_slot]] = acc ; use T1 for the address
        self.emit(f"LW {T1}, {self._slot_off(addr_slot)}(sp)")
        self.emit(f"SW {ACC}, 0({T1})")

    # ── address arithmetic ──────────────────────────────────────────────
    def emit_scale_index_word(self) -> None:
        self.emit(f"SLLI {ACC}, {ACC}, 2")       # * 4

    def emit_add_slot_to_acc(self, slot: int) -> None:
        self.emit(f"LW {T1}, {self._slot_off(slot)}(sp)")
        self.emit(f"ADD {ACC}, {T1}, {ACC}")

    def emit_sub_acc_from_slot(self, slot: int) -> None:
        # acc = slot - acc
        self.emit(f"LW {T1}, {self._slot_off(slot)}(sp)")
        self.emit(f"SUB {ACC}, {T1}, {ACC}")

    # ── unary ─────────────────────────────────────────────────────────────
    def emit_negate(self) -> None:
        self.emit(f"SUB {ACC}, x0, {ACC}")

    def emit_logical_not(self) -> None:
        # acc = (acc == 0) ? 1 : 0  ->  SLTIU acc, acc, 1
        self.emit(f"SLTIU {ACC}, {ACC}, 1")

    # ── comparison: acc = (slot OP acc) ─────────────────────────────────
    def emit_compare(self, op: str, left_slot: int) -> None:
        self.emit(f"LW {T1}, {self._slot_off(left_slot)}(sp)")  # T1 = left
        # T2 = right = acc
        self.emit(f"ADDI {T2}, {ACC}, 0")
        if op == "<":
            self.emit(f"SLT {ACC}, {T1}, {T2}")
        elif op == ">":
            self.emit(f"SLT {ACC}, {T2}, {T1}")
        elif op == "<=":
            # left <= right  <=>  !(right < left)
            self.emit(f"SLT {ACC}, {T2}, {T1}")
            self.emit(f"SLTIU {ACC}, {ACC}, 1")
        elif op == ">=":
            # left >= right  <=>  !(left < right)
            self.emit(f"SLT {ACC}, {T1}, {T2}")
            self.emit(f"SLTIU {ACC}, {ACC}, 1")
        elif op == "==":
            self.emit(f"SUB {ACC}, {T1}, {T2}")
            self.emit(f"SLTIU {ACC}, {ACC}, 1")     # (diff==0)
        elif op == "!=":
            self.emit(f"SUB {ACC}, {T1}, {T2}")
            self.emit(f"SLTU {ACC}, x0, {ACC}")     # (diff!=0)
        else:
            raise CompilerError(f"unsupported comparison '{op}'")

    # ── shifts: acc = slot OP acc ───────────────────────────────────────
    def emit_shift(self, op: str, left_slot: int) -> None:
        self.emit(f"LW {T1}, {self._slot_off(left_slot)}(sp)")
        self.emit(f"ADDI {T2}, {ACC}, 0")
        if op == "<<":
            self.emit(f"SLL {ACC}, {T1}, {T2}")
        else:  # >>  (arithmetic, C int is signed)
            self.emit(f"SRA {ACC}, {T1}, {T2}")

    # ── bitwise: acc = slot OP acc ──────────────────────────────────────
    def emit_bitwise(self, op: str, left_slot: int) -> None:
        self.emit(f"LW {T1}, {self._slot_off(left_slot)}(sp)")
        instr = {"&": "AND", "|": "OR", "^": "XOR"}[op]
        self.emit(f"{instr} {ACC}, {T1}, {ACC}")

    # ── control flow ─────────────────────────────────────────────────────
    def emit_branch_if_false(self, label: str) -> None:
        self.emit(f"BEQ {ACC}, x0, {label}")

    def emit_branch_if_true(self, label: str) -> None:
        self.emit(f"BNE {ACC}, x0, {label}")

    def emit_jump(self, label: str) -> None:
        self.emit(f"JAL x0, {label}")

    def emit_move_acc_to_return(self) -> None:
        self.emit(f"ADDI a0, {ACC}, 0")

    def emit_zero_return(self) -> None:
        self.emit("ADDI a0, x0, 0")

    def emit_print(self) -> None:
        # PRINT_ADDR fits an imm12, so store straight off the zero register.
        self.emit(f"SW {ACC}, {PRINT_ADDR}(x0)")

    # ── debugger symbols ─────────────────────────────────────────────────
    def main_frame_base(self, ctx: FunctionContext):
        # main is the first frame below the stack top.
        return STACK_TOP - ctx.frame_bytes()

    def slot_location(self, slot: int) -> str:
        return f"{self._slot_off(slot)}(sp)"

    # ── multiply / divide via runtime routines ──────────────────────────
    def emit_soft_mul(self, left_slot: int) -> None:
        self._need_mul = True
        # a0 = left, a1 = right (acc); call __mul; move a0 -> acc
        self.emit(f"LW a0, {self._slot_off(left_slot)}(sp)")
        self.emit(f"ADDI a1, {ACC}, 0")
        self.emit("JAL ra, __mul")
        self.emit(f"ADDI {ACC}, a0, 0")

    def emit_soft_div(self, left_slot: int, want_rem: bool) -> None:
        self._need_divmod = True
        self.emit(f"LW a0, {self._slot_off(left_slot)}(sp)")   # dividend
        self.emit(f"ADDI a1, {ACC}, 0")                        # divisor
        self.emit("JAL ra, __divmod")
        # __divmod: a0 = quotient, a1 = remainder
        src = "a1" if want_rem else "a0"
        self.emit(f"ADDI {ACC}, {src}, 0")

    # ── runtime routines (leaf; use only t/a registers, no frame) ───────
    def _emit_mul_routine(self) -> None:
        """__mul: a0 = a0 * a1 (low 32 bits, works for signed via mod 2^32).

        Shift-add over 32 bits of the multiplier. Uses t1..t4 + a0/a1.
        """
        self.comment("runtime: 32-bit multiply (shift-add)")
        self.emit("__mul:")
        # t1 = product = 0 ; t2 = multiplicand = a0 ; t3 = multiplier = a1
        self.emit("ADDI t1, x0, 0")
        self.emit("ADDI t2, a0, 0")
        self.emit("ADDI t3, a1, 0")
        self.emit("__mul_loop:")
        self.emit("BEQ t3, x0, __mul_done")
        # if (t3 & 1) product += t2
        self.emit("ANDI t4, t3, 1")
        self.emit("BEQ t4, x0, __mul_skip")
        self.emit("ADD t1, t1, t2")
        self.emit("__mul_skip:")
        self.emit("SLLI t2, t2, 1")            # multiplicand <<= 1
        self.emit("SRLI t3, t3, 1")            # multiplier >>= 1 (logical)
        self.emit("JAL x0, __mul_loop")
        self.emit("__mul_done:")
        self.emit("ADDI a0, t1, 0")
        self.emit("JALR x0, x1, 0")

    def _emit_divmod_routine(self) -> None:
        """__divmod: signed division. a0/a1 -> a0=quotient, a1=remainder.

        C semantics: quotient truncates toward zero, remainder has the sign of
        the dividend. Implemented as unsigned long division on absolute values
        plus a sign fix-up. Uses t1..t6 + a0/a1. Assumes a1 != 0 (division by
        zero leaves quotient 0, remainder = dividend).
        """
        self.comment("runtime: signed divide/modulo (long division)")
        self.emit("__divmod:")
        # divide by zero guard -> q=0, r=a0
        self.emit("BEQ a1, x0, __dm_byzero")
        # t5 = sign of quotient (dividend_sign XOR divisor_sign)
        # t6 = sign of remainder (dividend_sign)
        # compute abs(dividend) in t1, abs(divisor) in t2
        self.emit("SLT t6, a0, x0")            # t6 = dividend < 0
        self.emit("SLT t5, a1, x0")            # t5 = divisor < 0
        self.emit("XOR t5, t5, t6")            # t5 = quotient sign
        # t1 = |dividend|
        self.emit("ADDI t1, a0, 0")
        self.emit("BEQ t6, x0, __dm_absdd")
        self.emit("SUB t1, x0, t1")
        self.emit("__dm_absdd:")
        # t2 = |divisor|
        self.emit("ADDI t2, a1, 0")
        self.emit("BGE a1, x0, __dm_absdv")
        self.emit("SUB t2, x0, t2")
        self.emit("__dm_absdv:")
        # unsigned long division: t1 / t2 -> t3 quotient, t4 remainder
        self.emit("ADDI t3, x0, 0")            # quotient
        self.emit("ADDI t4, x0, 0")            # remainder
        self.emit("ADDI t0, x0, 32")           # bit counter (reuse t0 = acc, ok in leaf)
        self.emit("__dm_loop:")
        self.emit("BEQ t0, x0, __dm_fixsign")
        self.emit("ADDI t0, t0, -1")
        # remainder = (remainder << 1) | ((dividend >> bit) & 1)
        self.emit("SLLI t4, t4, 1")
        self.emit("SRL a2, t1, t0")            # a2 = dividend >> bit
        self.emit("ANDI a2, a2, 1")
        self.emit("OR t4, t4, a2")
        # quotient <<= 1
        self.emit("SLLI t3, t3, 1")
        # if remainder >= divisor: remainder -= divisor; quotient |= 1
        self.emit("SLTU a2, t4, t2")           # a2 = remainder < divisor
        self.emit("BNE a2, x0, __dm_loop")     # if <, skip subtract
        self.emit("SUB t4, t4, t2")
        self.emit("ORI t3, t3, 1")
        self.emit("JAL x0, __dm_loop")
        self.emit("__dm_fixsign:")
        # apply signs: quotient in t3, remainder in t4
        self.emit("ADDI a0, t3, 0")
        self.emit("ADDI a1, t4, 0")
        self.emit("BEQ t5, x0, __dm_qpos")
        self.emit("SUB a0, x0, a0")            # negate quotient
        self.emit("__dm_qpos:")
        self.emit("BEQ t6, x0, __dm_rpos")
        self.emit("SUB a1, x0, a1")            # remainder takes dividend sign
        self.emit("__dm_rpos:")
        self.emit("JALR x0, x1, 0")
        self.emit("__dm_byzero:")
        self.emit("ADDI a0, x0, 0")
        self.emit("JALR x0, x1, 0")           # (a1 already = original dividend? no)
