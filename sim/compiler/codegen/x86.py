"""
x86 IA-32 code generator for Core-C.

Emits the project's own x86 mnemonics (consumed unchanged by
``sim/assembler/x86.py``) in Intel syntax (dst, src). The assembler / decoder
model exposes MOV, the ALU ops (ADD/OR/AND/SUB/XOR/CMP) in reg,reg and reg,imm8
forms, and JMP/Jcc (rel8) — with **no shift, multiply, divide instruction and
no modelled CALL/RET stack**.

Consequences (documented v1 limits):
  * x86 programs must be **single-function and non-recursive** (base.py raises a
    CompilerError otherwise). ``main`` takes no parameters.
  * ``*`` / ``/`` / ``%`` are emitted as **inline** repeated-add / repeated-sub
    loops (no runtime helper, since there is no CALL).
  * ALU immediates are imm8 [-128,127]; larger constants are materialized into a
    scratch register with ``MOV r32, imm32`` then combined reg-reg.
  * Frame slots are addressed ``[EBP + disp8]`` (disp8 is signed, so ≤ 31 slots).

Register / frame convention:
  * ``EBP``  reserved frame pointer (fixed base; frame does not move — single
             function, no nested frames).
  * ``EAX``  accumulator + return value.
  * ``ECX EDX``  scratch.
  * ``EBX ESI EDI``  additional scratch for the inline mul/div loops.
"""
from __future__ import annotations

import re

from .base import CodeGenBase, FunctionContext, PRINT_ADDR
from .. import ast
from ..errors import CompilerError

ACC = "EAX"
T1 = "ECX"
T2 = "EDX"
FP = "EBP"
_REGS = {"EAX", "ECX", "EDX", "EBX", "ESP", "EBP", "ESI", "EDI"}
# Fixed frame base (byte). Data-memory word index = (base + slot*4) >> 2.
X86_FRAME_BASE = 256
MAX_SLOT_DISP = 124          # [EBP + disp8], disp8 signed -> keep <= 124 (31 slots)


class X86CodeGen(CodeGenBase):
    isa_name = "x86"
    slot_size = 4
    frame_reg = FP
    return_reg = "EAX"
    supports_recursion = False
    supports_multiple_functions = False
    has_hw_mul = False
    has_hw_div = False
    # x86's frame lives at the fixed EBP base, which is inside the global
    # region; cap globals below it so they can't collide with the frame.
    global_region_limit = X86_FRAME_BASE

    # ── slot addressing ─────────────────────────────────────────────────
    def _slot_off(self, slot: int) -> int:
        off = slot * self.slot_size
        if off > MAX_SLOT_DISP:
            raise CompilerError(
                f"x86 frame slot offset {off} exceeds the disp8 range "
                f"({MAX_SLOT_DISP}); reduce locals/arrays/temporaries")
        return off

    def _mem(self, slot: int) -> str:
        off = self._slot_off(slot)
        return f"[{FP}+{off}]" if off else f"[{FP}+0]"

    # ── load-use hazard peephole ────────────────────────────────────────
    # The shared x86 5-stage pipeline does not interlock/forward a memory load
    # (MOV reg,[mem]) into the very next instruction that reads that register,
    # so codegen inserts a NOP between such a load and its dependent use. This
    # is x86-only (RISC-V/ARM pipelines forward correctly) and keeps
    # single_cycle / multicycle / pipeline in agreement.
    _MEM_RE = re.compile(r"\[")

    @staticmethod
    def _instr_parts(line: str):
        """(mnemonic, [operand,...]) for a real instruction, or (None, []) for
        a label / comment / blank."""
        s = line.strip()
        if not s or s.startswith(";") or s.endswith(":"):
            return None, []
        head = s.split(None, 1)
        mn = head[0].upper()
        ops = [o.strip() for o in head[1].split(",")] if len(head) > 1 else []
        return mn, ops

    @classmethod
    def _load_dest(cls, line: str):
        """If ``line`` is a memory load (MOV reg,[mem]), return its dest reg."""
        mn, ops = cls._instr_parts(line)
        if mn == "MOV" and len(ops) == 2 and ops[0] in _REGS and "[" in ops[1]:
            return ops[0]
        return None

    @classmethod
    def _reads_reg(cls, line: str, reg: str) -> bool:
        """Does ``line`` read register ``reg`` (as a source or [base])?"""
        mn, ops = cls._instr_parts(line)
        if mn is None:
            return False
        for i, op in enumerate(ops):
            if "[" in op:
                # base register inside brackets is read
                if re.search(rf"\b{reg}\b", op):
                    return True
                continue
            if op == reg:
                # For 2-operand ALU/MOV, operand 0 is dst (written) unless it's
                # also read. MOV dst,src: dst is write-only. ALU dst,src: dst is
                # read+write. CMP reads both.
                if i == 0 and mn == "MOV":
                    continue
                return True
        return False

    def _postprocess(self) -> None:
        new_lines = []
        insert_before = {}          # original 1-based line -> NOP count inserted
        n = len(self.lines)
        for idx, line in enumerate(self.lines):
            new_lines.append(line)
            dest = self._load_dest(line)
            if dest is None:
                continue
            # find the next *instruction* (skip labels/comments)
            j = idx + 1
            while j < n:
                mn, _ = self._instr_parts(self.lines[j])
                if mn is not None:
                    break
                j += 1
            if j < n and self._reads_reg(self.lines[j], dest):
                new_lines.append("NOP")
                # NOP is inserted BEFORE original line (idx+1)+... ; record it
                insert_before[idx + 2] = insert_before.get(idx + 2, 0) + 1
        self.lines = new_lines
        self._reindex_source_map(insert_before)

    # ── program prologue / runtime ──────────────────────────────────────
    def emit_program_prologue(self) -> None:
        self.comment("Core-C -> x86 IA-32 (compiled, single-function)")
        self.comment(f"frame base EBP = {X86_FRAME_BASE}")
        self.emit(f"MOV {FP}, {X86_FRAME_BASE}")
        # No CALL stack: main is emitted inline right after; fall through to it.

    def emit_runtime(self) -> None:
        # After main returns it JMPs to 'halt'; park there.
        self.emit("halt:")
        self.emit("JMP halt")

    # ── prologue / epilogue (single frame, EBP fixed) ───────────────────
    def emit_prologue(self, ctx: FunctionContext) -> None:
        # Validate the whole frame fits the disp8 window up front.
        self._slot_off(ctx.frame_slots() - 1 if ctx.frame_slots() else 0)

    def emit_store_params(self, ctx: FunctionContext) -> None:
        if ctx.params:
            raise CompilerError(
                "x86 backend functions take no parameters (no CALL/RET stack)")

    def emit_epilogue(self, ctx: FunctionContext) -> None:
        pass  # nothing to restore (fixed EBP, no saved ra)

    def emit_epilogue_return_zero(self, ctx: FunctionContext) -> None:
        self.emit(f"MOV {ACC}, 0")
        self.emit_return()

    def emit_return(self) -> None:
        # No RET stack — jump to the halt loop with the value already in EAX.
        self.emit("JMP halt")

    # ── calls: unsupported ──────────────────────────────────────────────
    def emit_call(self, expr: ast.Call, callee: ast.Function) -> None:
        raise CompilerError(
            "function calls are not supported on the x86 backend "
            "(no CALL/RET stack is modelled)", expr.line)

    # ── constants ─────────────────────────────────────────────────────────
    def emit_load_const(self, value: int) -> None:
        self.emit(f"MOV {ACC}, {value & 0xFFFFFFFF if value >= 0 else value}")

    def _load_imm(self, reg: str, value: int) -> None:
        self.emit(f"MOV {reg}, {value}")

    # ── slot load/store ─────────────────────────────────────────────────
    def emit_load_slot(self, slot: int) -> None:
        self.emit(f"MOV {ACC}, {self._mem(slot)}")

    def emit_store_slot(self, slot: int) -> None:
        self.emit(f"MOV {self._mem(slot)}, {ACC}")

    def emit_load_slot_address(self, slot: int) -> None:
        # acc = EBP + off  (materialize base in acc, add offset)
        self.emit(f"MOV {ACC}, {FP}")
        off = self._slot_off(slot)
        if off:
            self._add_imm_to_acc(off)

    def emit_load_at_acc(self) -> None:
        # acc = mem[acc]; move address to a base reg then MOV [base]
        self.emit(f"MOV {T1}, {ACC}")
        self.emit(f"MOV {ACC}, [{T1}+0]")

    def emit_store_at_slot_addr(self, addr_slot: int) -> None:
        self.emit(f"MOV {T1}, {self._mem(addr_slot)}")
        self.emit(f"MOV [{T1}+0], {ACC}")

    # ── immediate helpers (imm8 ALU only -> scratch for big) ────────────
    def _add_imm_to_acc(self, value: int) -> None:
        if -128 <= value <= 127:
            self.emit(f"ADD {ACC}, {value}")
        else:
            self._load_imm(T2, value)
            self.emit(f"ADD {ACC}, {T2}")

    # ── address arithmetic ──────────────────────────────────────────────
    def emit_scale_index_word(self) -> None:
        # acc = index * 4  (no shift/mul -> two self-adds)
        self.emit(f"ADD {ACC}, {ACC}")            # *2
        self.emit(f"ADD {ACC}, {ACC}")            # *4

    def emit_add_slot_to_acc(self, slot: int) -> None:
        # ALU has no reg,[mem] form -> load slot into a scratch reg first.
        self.emit(f"MOV {T1}, {self._mem(slot)}")
        self.emit(f"ADD {ACC}, {T1}")

    def emit_sub_acc_from_slot(self, slot: int) -> None:
        # acc = slot - acc  -> T1 = slot; T1 -= acc; acc = T1
        self.emit(f"MOV {T1}, {self._mem(slot)}")
        self.emit(f"SUB {T1}, {ACC}")
        self.emit(f"MOV {ACC}, {T1}")

    # ── unary ─────────────────────────────────────────────────────────────
    def emit_negate(self) -> None:
        # acc = 0 - acc  -> T1=0; T1-=acc; acc=T1
        self.emit(f"MOV {T1}, 0")
        self.emit(f"SUB {T1}, {ACC}")
        self.emit(f"MOV {ACC}, {T1}")

    def emit_logical_not(self) -> None:
        # acc = (acc == 0) ? 1 : 0
        t = self.new_label("not_t")
        e = self.new_label("not_e")
        self.emit(f"CMP {ACC}, 0")
        self.emit(f"JE {t}")
        self.emit(f"MOV {ACC}, 0")
        self.emit(f"JMP {e}")
        self.emit(f"{t}:")
        self.emit(f"MOV {ACC}, 1")
        self.emit(f"{e}:")

    # ── comparison: acc = (slot OP acc) via CMP + Jcc ───────────────────
    def emit_compare(self, op: str, left_slot: int) -> None:
        jcc = {"<": "JL", ">": "JG", "<=": "JLE", ">=": "JGE",
               "==": "JE", "!=": "JNE"}[op]
        t = self.new_label("cmp_t")
        e = self.new_label("cmp_e")
        # T1 = left, T2 = right (acc). CMP T1, T2 -> flags for left OP right.
        self.emit(f"MOV {T1}, {self._mem(left_slot)}")
        self.emit(f"MOV {T2}, {ACC}")
        self.emit(f"CMP {T1}, {T2}")
        self.emit(f"{jcc} {t}")
        self.emit(f"MOV {ACC}, 0")
        self.emit(f"JMP {e}")
        self.emit(f"{t}:")
        self.emit(f"MOV {ACC}, 1")
        self.emit(f"{e}:")

    # ── shifts: unsupported by the x86 assembler subset ─────────────────
    def emit_shift(self, op: str, left_slot: int) -> None:
        raise CompilerError(
            "shift operators (<< >>) are not supported on the x86 backend "
            "(the assembler exposes no shift instruction)")

    # ── bitwise: acc = slot OP acc ──────────────────────────────────────
    def emit_bitwise(self, op: str, left_slot: int) -> None:
        instr = {"&": "AND", "|": "OR", "^": "XOR"}[op]
        self.emit(f"MOV {T1}, {self._mem(left_slot)}")
        self.emit(f"{instr} {T1}, {ACC}")
        self.emit(f"MOV {ACC}, {T1}")

    # ── control flow ─────────────────────────────────────────────────────
    def emit_branch_if_false(self, label: str) -> None:
        self.emit(f"CMP {ACC}, 0")
        self.emit(f"JE {label}")

    def emit_branch_if_true(self, label: str) -> None:
        self.emit(f"CMP {ACC}, 0")
        self.emit(f"JNE {label}")

    def emit_jump(self, label: str) -> None:
        self.emit(f"JMP {label}")

    def emit_move_acc_to_return(self) -> None:
        pass  # result already in EAX (the accumulator)

    def emit_zero_return(self) -> None:
        self.emit(f"MOV {ACC}, 0")

    def emit_print(self) -> None:
        # No absolute-address MOV form in the modelled subset; go through T1.
        self.emit(f"MOV {T1}, {PRINT_ADDR}")
        self.emit(f"MOV [{T1}+0], {ACC}")

    # ── debugger symbols ─────────────────────────────────────────────────
    def main_frame_base(self, ctx: FunctionContext):
        return X86_FRAME_BASE

    def slot_location(self, slot: int) -> str:
        return self._mem(slot)

    # ── inline multiply / divide (no CALL) ──────────────────────────────
    def emit_soft_mul(self, left_slot: int) -> None:
        """acc = slot * acc via inline repeated addition (low 32 bits).

        Multiplies by |acc| copies of the multiplicand, negating the result if
        the multiplier was negative. Uses EBX (product), ESI (multiplicand),
        EDI (counter/sign) so EAX/ECX/EDX stay free for the loop control.
        """
        loop = self.new_label("mul_loop")
        done = self.new_label("mul_done")
        pos = self.new_label("mul_pos")
        ret = self.new_label("mul_ret")
        self.emit(f"MOV ESI, {self._mem(left_slot)}")   # multiplicand
        self.emit(f"MOV EDI, {ACC}")                    # multiplier
        self.emit("MOV EBX, 0")                         # product
        self.emit("MOV ECX, 0")                         # negate flag
        # if multiplier < 0: multiplier = -multiplier; flag = 1
        self.emit("CMP EDI, 0")
        self.emit(f"JGE {loop}")
        self.emit("MOV EDX, 0")
        self.emit("SUB EDX, EDI")
        self.emit("MOV EDI, EDX")
        self.emit("MOV ECX, 1")
        self.emit(f"{loop}:")
        self.emit("CMP EDI, 0")
        self.emit(f"JE {done}")
        self.emit("ADD EBX, ESI")                       # product += multiplicand
        self.emit("SUB EDI, 1")                         # counter--
        self.emit(f"JMP {loop}")
        self.emit(f"{done}:")
        self.emit(f"MOV {ACC}, EBX")
        self.emit("CMP ECX, 0")
        self.emit(f"JE {ret}")
        self.emit("MOV EDX, 0")
        self.emit(f"SUB EDX, {ACC}")
        self.emit(f"MOV {ACC}, EDX")
        self.emit(f"{ret}:")
        self.emit(f"{pos}:")

    def emit_soft_div(self, left_slot: int, want_rem: bool) -> None:
        """acc = slot / acc  or  slot % acc  via inline repeated subtraction.

        Signed: works on absolute values then fixes signs (quotient sign =
        XOR of operand signs; remainder sign = dividend sign). Division by zero
        yields 0. Uses EBX,ESI,EDI + ECX,EDX as scratch.
        """
        loop = self.new_label("div_loop")
        done = self.new_label("div_done")
        byzero = self.new_label("div_bz")
        end = self.new_label("div_end")
        ddpos = self.new_label("div_ddp")
        dvpos = self.new_label("div_dvp")
        absdd = self.new_label("div_absdd")
        absdv = self.new_label("div_absdv")
        qpos = self.new_label("div_qpos")
        rpos = self.new_label("div_rpos")

        # ESI = dividend (slot), EDI = divisor (acc)
        self.emit(f"MOV ESI, {self._mem(left_slot)}")
        self.emit(f"MOV EDI, {ACC}")
        self.emit("CMP EDI, 0")
        self.emit(f"JE {byzero}")
        # sign flags: EBX = dividend<0, ECX = divisor<0 (store to temp slots via regs)
        # Use EAX/EDX transiently; keep flags in EBX(dd sign) and a temp slot.
        # dividend sign -> EBX
        self.emit("MOV EBX, 0")
        self.emit("CMP ESI, 0")
        self.emit(f"JGE {ddpos}")
        self.emit("MOV EBX, 1")
        self.emit(f"{ddpos}:")
        # divisor sign -> EAX (temp)
        self.emit(f"MOV {ACC}, 0")
        self.emit("CMP EDI, 0")
        self.emit(f"JGE {dvpos}")
        self.emit(f"MOV {ACC}, 1")
        self.emit(f"{dvpos}:")
        # quotient-sign flag = EBX XOR EAX  -> store in EDX
        self.emit("MOV EDX, EBX")
        self.emit(f"XOR EDX, {ACC}")            # EDX = quotient negate flag
        # abs(dividend) in ESI
        self.emit("CMP EBX, 0")
        self.emit(f"JE {absdd}")
        self.emit(f"MOV {ACC}, 0")
        self.emit(f"SUB {ACC}, ESI")
        self.emit(f"MOV ESI, {ACC}")
        self.emit(f"{absdd}:")
        # abs(divisor) in EDI
        self.emit(f"MOV {ACC}, EDI")           # test original divisor sign via EDI
        self.emit(f"CMP {ACC}, 0")
        self.emit(f"JGE {absdv}")
        self.emit(f"MOV {ACC}, 0")
        self.emit(f"SUB {ACC}, EDI")
        self.emit(f"MOV EDI, {ACC}")
        self.emit(f"{absdv}:")
        # quotient in ECX = 0; while ESI >= EDI: ESI -= EDI; ECX++
        self.emit("MOV ECX, 0")
        self.emit(f"{loop}:")
        self.emit("CMP ESI, EDI")
        self.emit(f"JL {done}")
        self.emit("SUB ESI, EDI")
        self.emit("ADD ECX, 1")
        self.emit(f"JMP {loop}")
        self.emit(f"{done}:")
        # quotient=ECX (negate if EDX), remainder=ESI (negate if EBX)
        if want_rem:
            self.emit(f"MOV {ACC}, ESI")
            self.emit("CMP EBX, 0")
            self.emit(f"JE {rpos}")
            self.emit("MOV EDX, 0")
            self.emit(f"SUB EDX, {ACC}")
            self.emit(f"MOV {ACC}, EDX")
            self.emit(f"{rpos}:")
            self.emit(f"JMP {end}")
        else:
            self.emit(f"MOV {ACC}, ECX")
            self.emit("CMP EDX, 0")
            self.emit(f"JE {qpos}")
            self.emit(f"MOV EDX, 0")           # reuse (EDX flag already consumed)
            self.emit(f"SUB EDX, {ACC}")
            self.emit(f"MOV {ACC}, EDX")
            self.emit(f"{qpos}:")
            self.emit(f"JMP {end}")
        self.emit(f"{byzero}:")
        self.emit(f"MOV {ACC}, 0")
        self.emit(f"{end}:")
