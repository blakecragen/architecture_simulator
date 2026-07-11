"""Regression tests for correctness + robustness bugs fixed after the
initial audit.

Each test pins behaviour that was previously wrong:

* OoO stores never executed (never entered the ROB) -> now write memory.
* DataMemory dropped a store to byte address 0 -> now honoured.
* Fetch followed branch *prediction* even while a load-use stall was
  asserted -> stall now outranks prediction (but a resolved branch still
  outranks the stall, as the multi-cycle controller relies on).
* Wide superscalar forwarding returned the OLDEST matching lane -> now the
  youngest (program-order-correct) writer.
* x86 pass-1 size estimate disagreed with pass-2 encoding for an explicit
  zero displacement (`[reg+0]`), drifting every later label by one byte.
* API endpoints returned raw 500s on hostile input -> now clean 400s with
  num_lanes / cycles clamped.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.assembler import assemble
from sim.runner_v2 import run_simulation
from sim.components.fetch.simple import SimpleFetch
from sim.components.superscalar.wide_forwarding import WideForwardingUnit
from sim.isa.riscv.presets import ooo as riscv_ooo
from sim.isa.arm.presets import ooo as arm_ooo
from sim.isa.x86.presets import ooo as x86_ooo
from sim.harness import simulate


class TestSignedBranches(unittest.TestCase):
    """ARM/x86 signed conditional branches must compare by SIGN, not the
    parity bit (and JLE/JG / B.LE/B.GT must not be approximated by EQ/NE).
    Verified on the models with correct condition-flag timing: single_cycle,
    multicycle, pipeline (flags pipelined to EX), and arm superscalar.
    OoO is covered separately by TestOoOBranches (committed-flags path)."""

    MODELS = ["single_cycle", "multicycle", "pipeline"]

    def _branch_taken_arm(self, model, a, b, cond, cycles=90):
        # X3 == 1 iff the branch was taken (else 7).
        asm = (f"MOVZ X1,#{a}\nMOVZ X2,#{b}\nMOVZ X3,#7\nCMP X1,X2\n"
               f"{cond} taken\nB done\ntaken:\nMOVZ X3,#1\ndone:\n" + "NOP\n" * 8)
        return simulate("arm", model, asm=asm, cycles=cycles).reg(3) == 1

    def _branch_taken_x86(self, model, a, b, cond):
        asm = (f"MOV EAX,{a}\nMOV EBX,{b}\nMOV ECX,7\nCMP EAX,EBX\n"
               f"{cond} taken\nJMP done\ntaken:\nMOV ECX,1\ndone:\n" + "NOP\n" * 8)
        return simulate("x86", model, asm=asm, cycles=90).reg("ECX") == 1

    def test_arm_signed_conditions(self):
        # (a, b, cond, expected_taken). 5 vs 13 -> diff -8 (even: parity bug);
        # 5 vs 5 -> equal (LE/GE edge).
        cases = [
            (5, 13, "B.LT", True), (13, 5, "B.LT", False),
            (13, 5, "B.GT", True), (5, 13, "B.GT", False),
            (5, 5, "B.LE", True),  (5, 5, "B.GE", True),
            (5, 13, "B.LE", True), (13, 5, "B.LE", False),
        ]
        for model in self.MODELS:
            for a, b, cond, want in cases:
                with self.subTest(model=model, a=a, b=b, cond=cond):
                    self.assertEqual(self._branch_taken_arm(model, a, b, cond), want)

    def test_arm_superscalar_signed_conditions(self):
        # ARM superscalar resolves signed branches via the youngest-lane flags
        # selector (CMP/SUBS can land in any lane) — see WideFlagsSelect. Needs a
        # larger cycle budget than the in-order models.
        cases = [
            (5, 13, "B.LT", True), (13, 5, "B.LT", False),
            (13, 5, "B.GT", True), (5, 13, "B.GT", False),
            (5, 5, "B.LE", True),  (5, 13, "B.LE", True),
        ]
        for lanes in (2, 3):
            for a, b, cond, want in cases:
                with self.subTest(lanes=lanes, a=a, b=b, cond=cond):
                    asm = (f"MOVZ X1,#{a}\nMOVZ X2,#{b}\nMOVZ X3,#7\nCMP X1,X2\n"
                           f"{cond} taken\nB done\ntaken:\nMOVZ X3,#1\ndone:\n" + "NOP\n" * 12)
                    got = simulate("arm", "superscalar", asm=asm, cycles=160,
                                   num_lanes=lanes).reg(3) == 1
                    self.assertEqual(got, want)

    def test_x86_signed_conditions(self):
        cases = [
            (5, 13, "JL", True),  (13, 5, "JL", False),
            (13, 5, "JG", True),  (5, 13, "JG", False),
            (5, 13, "JLE", True), (5, 5, "JLE", True), (13, 5, "JLE", False),
            (13, 5, "JGE", True), (5, 13, "JGE", False),
        ]
        for model in self.MODELS:
            for a, b, cond, want in cases:
                with self.subTest(model=model, a=a, b=b, cond=cond):
                    self.assertEqual(self._branch_taken_x86(model, a, b, cond), want)

    def test_riscv_blt_still_correct(self):
        # RISC-V keeps its SLT-based path (compare_mode='slt'); unchanged.
        for model in ["single_cycle", "multicycle", "pipeline", "ooo"]:
            asm = ("ADDI x1,x0,5\nADDI x2,x0,13\nADDI x3,x0,7\n"
                   "BLT x1,x2,taken\nJAL x0,done\ntaken:\nADDI x3,x0,1\ndone:\n" + "NOP\n" * 6)
            with self.subTest(model=model):
                self.assertEqual(simulate("riscv", model, asm=asm, cycles=80).reg(3), 1)


class TestFetchStallPrecedence(unittest.TestCase):
    def test_stall_holds_pc_over_prediction(self):
        f = SimpleFetch(pc_reset=0x100)
        f["stall"] = 1
        f["predict_taken"] = 1
        f["predict_target"] = 0x200
        f["branch_taken"] = 0
        f.evaluate()
        f.rising_edge()
        f.evaluate()
        self.assertEqual(f["pc_out"], 0x100, "stall must hold PC, not follow prediction")

    def test_resolved_branch_beats_stall(self):
        f = SimpleFetch(pc_reset=0x100)
        f["stall"] = 1
        f["branch_taken"] = 1
        f["next_pc"] = 0x300
        f.evaluate()
        f.rising_edge()
        f.evaluate()
        self.assertEqual(f["pc_out"], 0x300, "resolved branch redirect must beat stall")

    def test_normal_advance(self):
        f = SimpleFetch(pc_reset=0x100)
        f.evaluate()
        f.rising_edge()
        f.evaluate()
        self.assertEqual(f["pc_out"], 0x104)


class TestWideForwardingYoungest(unittest.TestCase):
    def test_youngest_lane_wins_ex_mem(self):
        fw = WideForwardingUnit(num_lanes=2)
        # Both in-flight lanes write rd=5; lane 1 is younger (later in program
        # order) and must be the forwarding source.
        fw["ex_mem_reg_write_0"] = 1
        fw["ex_mem_rd_0"] = 5
        fw["ex_mem_alu_result_0"] = 0xAAAA
        fw["ex_mem_reg_write_1"] = 1
        fw["ex_mem_rd_1"] = 5
        fw["ex_mem_alu_result_1"] = 0xBBBB
        fw["id_ex_rs1_0"] = 5
        fw["rs1_data_in_0"] = 0x1234
        fw.evaluate()
        self.assertEqual(fw["rs1_data_out_0"], 0xBBBB)


class TestOoOStoreExecutes(unittest.TestCase):
    """Stores must reach data memory (previously they never committed)."""

    def _run(self, build, program, cycles=60):
        cpu = build(program)
        run_simulation(cpu, num_cycles=cycles, include_reset=True)
        return cpu.components["dmem"]._mem

    def test_riscv_store_to_addr0_and_addr8(self):
        prog = assemble("riscv", """
            ADDI x1, x0, 42
            ADDI x2, x0, 8
            ADDI x5, x0, 99
            ADDI x6, x0, 0
            ADDI x6, x0, 0
            ADDI x6, x0, 0
            SW   x1, 0(x0)
            SW   x5, 0(x2)
        """)
        mem = self._run(riscv_ooo.build, prog)
        self.assertEqual(mem[0], 42, "store to byte address 0 must be honoured")
        self.assertEqual(mem[2], 99)

    def test_arm_store(self):
        prog = assemble("arm", """
            MOVZ X1, #42
            MOVZ X2, #0
            MOVZ X6, #0
            MOVZ X6, #0
            MOVZ X6, #0
            STR  X1, [X2, #0]
        """)
        mem = self._run(arm_ooo.build, prog)
        self.assertEqual(mem[0], 42)

    def test_x86_store(self):
        prog = assemble("x86", """
            MOV EAX, 42
            MOV ECX, 0
            MOV EDX, 0
            MOV EDX, 0
            MOV EDX, 0
            MOV [ECX], EAX
        """)
        mem = self._run(x86_ooo.build, prog)
        self.assertEqual(mem[0], 42)

    def test_store_data_renamed_not_captured_at_dispatch(self):
        """A store of a value computed *just* before it must store the fresh
        value, not the stale dispatch-time register contents. (OoO reads the
        store data from the regfile at COMMIT, after the producer commits.)"""
        # riscv: x1 produced one instruction before the SW.
        prog = assemble("riscv", """
            ADDI x5, x0, 40
            ADDI x1, x0, 99
            SW   x1, 0(x5)
            NOP
            NOP
            NOP
            NOP
            NOP
        """)
        mem = self._run(riscv_ooo.build, prog, cycles=70)
        self.assertEqual(mem[10], 99, "store captured stale data instead of 99")

        # data produced by an ADD immediately before the store
        prog2 = assemble("riscv", """
            ADDI x1, x0, 30
            ADDI x2, x0, 12
            ADD  x3, x1, x2
            SW   x3, 8(x0)
            NOP
            NOP
            NOP
            NOP
        """)
        mem2 = self._run(riscv_ooo.build, prog2, cycles=70)
        self.assertEqual(mem2[2], 42)


class TestX86ZeroDisplacement(unittest.TestCase):
    def test_zero_disp_encodes_three_bytes(self):
        # [EBX+0] keeps the disp8 byte so pass-1 size == pass-2 length.
        prog = assemble("x86", "MOV [EBX+0], EAX")
        self.assertEqual(len(prog), 3, "explicit +0 must keep the disp8 byte")
        self.assertEqual(prog, [0x89, 0x43, 0x00])

    def test_no_disp_encodes_two_bytes(self):
        prog = assemble("x86", "MOV [ECX], EAX")
        self.assertEqual(len(prog), 2)

    def test_label_after_zero_disp_resolves(self):
        # A backward JMP after a [reg+0] store must land exactly on start.
        prog = assemble("x86", """
        start:
            MOV [EBX+0], EAX
            JMP start
        """)
        self.assertEqual(len(prog), 5)         # 3-byte MOV + 2-byte JMP
        self.assertEqual(prog[-1], 0xFB)       # rel8 == -5 -> back to start


class TestAPIRobustness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from api.app import app
        cls.client = app.test_client()

    def _post(self, path, body):
        return self.client.post(path, data=json.dumps(body),
                                content_type="application/json")

    def _post_raw(self, path, data):
        return self.client.post(path, data=data, content_type="application/json")

    def test_bad_program_entry_is_400_not_500(self):
        self.assertEqual(self._post("/simulate", {"program": ["xyz"]}).status_code, 400)

    def test_non_list_program_is_400(self):
        self.assertEqual(self._post("/simulate", {"program": 5}).status_code, 400)

    def test_non_int_cycles_is_400(self):
        self.assertEqual(self._post("/simulate", {"cycles": "abc"}).status_code, 400)

    def test_null_body_is_400(self):
        self.assertEqual(self._post_raw("/simulate", "null").status_code, 400)
        self.assertEqual(self._post_raw("/assemble", "null").status_code, 400)

    def test_non_dict_body_is_400(self):
        self.assertEqual(self._post_raw("/simulate", "[1,2]").status_code, 400)

    def test_assemble_non_string_text_is_400(self):
        self.assertEqual(self._post("/assemble", {"text": 123}).status_code, 400)

    def test_num_lanes_is_clamped_not_500(self):
        # Negative / huge num_lanes must be clamped and succeed, never 500.
        for n in (-5, 0, 999):
            r = self._post("/simulate", {"preset": "riscv/superscalar",
                                         "num_lanes": n, "cycles": 5})
            self.assertEqual(r.status_code, 200, f"num_lanes={n} should clamp to 200")

    def test_topology_bad_num_lanes_is_400(self):
        r = self.client.get("/topology/riscv/superscalar?num_lanes=abc")
        self.assertEqual(r.status_code, 400)

    def test_examples_traversal_blocked(self):
        r = self.client.get("/examples/riscv/instructions/..%2f..%2f..%2fapi%2fapp.py")
        self.assertIn(r.status_code, (400, 404))


if __name__ == "__main__":
    unittest.main()


# ── OoO conditional branches (control-flow redesign) ─────────────────────────
# OoO conditional branches were previously racy: the branch resolved
# combinationally at decode against the live, out-of-order ALU/flags, and
# ARM/x86 flag-setters (CMP/SUBS) never dispatched, so flags were never
# produced.  The redesign:
#   * Flag-setters now dispatch (gate = reg_write OR mem_write OR write_flags),
#     execute via the RS/ALU, and latch their result into CommittedFlags at ROB
#     commit (i.e. in program order).
#   * A conditional branch is *serialized*: fetch is held until the ROB drains
#     (rob.empty), so by the time the branch resolves its comparison inputs are
#     settled in program order.
#   * The comparison is sourced from settled state — a dedicated in-order
#     comparator over the register file (RISC-V) or CommittedFlags (ARM/x86).
# Every OoO branch outcome must now match the single_cycle reference.

class TestOoOBranches(unittest.TestCase):
    """OoO conditional branches must match the single_cycle reference across
    taken / not-taken directions and inside backward-branch loops, for all
    three ISAs."""

    def _agrees(self, isa, asm, reg, want, cycles=160):
        ref = simulate(isa, "single_cycle", asm=asm, cycles=40).reg(reg)
        ooo = simulate(isa, "ooo", asm=asm, cycles=cycles).reg(reg)
        self.assertEqual(ref, want, f"single_cycle reference wrong for {isa}")
        self.assertEqual(ooo, want, f"ooo {isa} branch mismatch (got {ooo}, want {want})")

    # ── RISC-V (compare via dedicated in-order branch comparator) ──
    def _riscv(self, head, cond, args):
        return (f"{head}\n{cond} {args},t\nJAL x0,d\nt:\nADDI x3,x0,1\nd:\n"
                + "NOP\n" * 10)

    def test_riscv_blt_not_taken(self):
        # 13 < 5 is false -> x3 stays 7
        asm = self._riscv("ADDI x1,x0,13\nADDI x2,x0,5\nADDI x3,x0,7", "BLT", "x1,x2")
        self._agrees("riscv", asm, 3, 7)

    def test_riscv_blt_taken(self):
        asm = self._riscv("ADDI x1,x0,5\nADDI x2,x0,13\nADDI x3,x0,7", "BLT", "x1,x2")
        self._agrees("riscv", asm, 3, 1)

    def test_riscv_beq_taken(self):
        asm = self._riscv("ADDI x1,x0,9\nADDI x2,x0,9\nADDI x3,x0,7", "BEQ", "x1,x2")
        self._agrees("riscv", asm, 3, 1)

    def test_riscv_bne_not_taken(self):
        asm = self._riscv("ADDI x1,x0,9\nADDI x2,x0,9\nADDI x3,x0,7", "BNE", "x1,x2")
        self._agrees("riscv", asm, 3, 7)

    def test_riscv_loop_sums_1_to_5(self):
        asm = ("ADDI x1,x0,0\nADDI x2,x0,1\nADDI x3,x0,6\n"
               "loop:\nADD x1,x1,x2\nADDI x2,x2,1\nBLT x2,x3,loop\n" + "NOP\n" * 5)
        self.assertEqual(simulate("riscv", "ooo", asm=asm, cycles=400).reg(1), 15)

    # ── ARM (compare via committed flags from CMP/SUBS) ──
    def _arm(self, a, b, cond):
        return (f"MOVZ X1,#{a}\nMOVZ X2,#{b}\nMOVZ X3,#7\nCMP X1,X2\n{cond} t\n"
                f"B d\nt:\nMOVZ X3,#1\nd:\n" + "NOP\n" * 12)

    def test_arm_blt_taken(self):
        self._agrees("arm", self._arm(5, 13, "B.LT"), 3, 1)

    def test_arm_blt_not_taken(self):
        self._agrees("arm", self._arm(13, 5, "B.LT"), 3, 7)

    def test_arm_bgt_taken(self):
        self._agrees("arm", self._arm(13, 5, "B.GT"), 3, 1)

    def test_arm_ble_equal_taken(self):
        self._agrees("arm", self._arm(5, 5, "B.LE"), 3, 1)

    def test_arm_beq_not_taken(self):
        self._agrees("arm", self._arm(9, 8, "B.EQ"), 3, 7)

    def test_arm_loop_sums_1_to_5(self):
        asm = ("MOVZ X1,#0\nMOVZ X2,#1\nMOVZ X3,#6\n"
               "loop:\nADD X1,X1,X2\nADD X2,X2,#1\nCMP X2,X3\nB.LT loop\n" + "NOP\n" * 5)
        self.assertEqual(simulate("arm", "ooo", asm=asm, cycles=600).reg(1), 15)

    # ── x86 (compare via committed flags from CMP) ──
    def _x86(self, a, b, cond):
        return (f"MOV EAX,{a}\nMOV EBX,{b}\nMOV ECX,7\nCMP EAX,EBX\n{cond} t\n"
                f"JMP d\nt:\nMOV ECX,1\nd:\n" + "NOP\n" * 12)

    def test_x86_jl_taken(self):
        self._agrees("x86", self._x86(5, 13, "JL"), "ECX", 1)

    def test_x86_jl_not_taken(self):
        self._agrees("x86", self._x86(13, 5, "JL"), "ECX", 7)

    def test_x86_jg_taken(self):
        self._agrees("x86", self._x86(13, 5, "JG"), "ECX", 1)

    def test_x86_jle_equal_taken(self):
        self._agrees("x86", self._x86(5, 5, "JLE"), "ECX", 1)

    def test_x86_jne_not_taken(self):
        self._agrees("x86", self._x86(9, 9, "JNE"), "ECX", 7)

    def test_x86_loop_sums_1_to_5(self):
        asm = ("MOV EAX,0\nMOV EBX,1\nMOV EDX,6\n"
               "loop:\nADD EAX,EBX\nADD EBX,1\nCMP EBX,EDX\nJL loop\n" + "NOP\n" * 5)
        self.assertEqual(simulate("x86", "ooo", asm=asm, cycles=600).reg("EAX"), 15)
