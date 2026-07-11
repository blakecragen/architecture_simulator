"""
Direct (build-level) ISA x model x predictor correctness matrix.

Complements test_matrix.py, which exercises the same cross-product through the
Flask API on the examples in programs/. Here we build CPUs directly from the
presets and assert ARCHITECTURAL CORRECTNESS of the final state on small
canonical programs assembled in-test, so a failure pinpoints the exact
(preset, program) or (preset, predictor, stage) cell without HTTP in the way.

This file closes three coverage gaps:
  1. ARM multicycle/pipeline/ooo/superscalar and x86 multicycle/pipeline/ooo
     previously had NO direct tests (only riscv had per-model suites).
  2. Predictor final-state invariance was only asserted for riscv/pipeline;
     here every prediction-capable preset x all predictors x both stages is
     asserted (predictors may change timing, never architectural results).
  3. Predictor classes get a uniform unit-level contract sweep.

Known gaps:
  * x86/superscalar reuses the RISC-V decoder on an x86 byte stream and is
    illustrative-only; it is excluded from every correctness assertion here.
  * x86 POP cannot restore ESP (single-write-port datapath / one-rd decoder
    contract) — pinned by the strict xfail test_x86_pop_restores_esp_GAP.

Regressions pinned here (all found by this file, then FIXED):
  * The OoO CDB used to broadcast alu.result even for loads, so instructions
    DEPENDENT on a load captured the load's ADDRESS instead of its data
    (fixed via CdbValueSelect; the "mem" program on the ooo presets covers it
    — its final ADD consumes two load results off the CDB).
  * OoO store->load ordering: a load could EXECUTE before an older store to
    the same address COMMITTED and read stale memory (fixed: the ROB exposes
    store_pending_mask/head_ptr and the RS holds loads while an older store
    is uncommitted — see test_ooo_tight_store_load_ordering).
  * ARM/x86 pipeline flags-clobber: branches read the flags register LIVE at
    resolve time (MEM), so a younger flag-writing instruction in EX clobbered
    the condition — an IF-stage predicted-taken loop then never exited (fixed:
    flags are captured into EX/MEM and travel WITH the branch).
  * Superscalar IF-stage fetch steering was unsound (lane-0-only resolution +
    cross-lane partial squashes + no same-group squash after a predicted-taken
    branch => unrecoverable false paths). IF-stage predictors on superscalar
    are now informational-only (train + display, no steering — the same policy
    the OoO presets use), so every predictor/stage combination is
    architecturally correct and asserted below.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.harness import PRESETS, PREDICTOR_CLASSES  # noqa: E402
from sim.assembler import assemble  # noqa: E402
from sim.runner_v2 import run_simulation  # noqa: E402
from sim.components.branch.predictors.base import BranchPredictorBase  # noqa: E402

RISCV_REGS = {f"x{i}": i for i in range(32)}
ARM_REGS = {f"X{i}": i for i in range(31)}
ARM_REGS["XZR"] = 31
X86_REGS = {
    "EAX": 0, "ECX": 1, "EDX": 2, "EBX": 3,
    "ESP": 4, "EBP": 5, "ESI": 6, "EDI": 7,
}
REG_MAPS = {"riscv": RISCV_REGS, "arm": ARM_REGS, "x86": X86_REGS}

# Cycle budgets per model, sized so every canonical program below settles
# (multicycle needs ~4x; ooo drains the ROB across branches).
CYCLES = {"single_cycle": 60, "multicycle": 250, "configurable": 60,
          "pipeline": 150, "ooo": 250, "superscalar": 150}

# x86/superscalar reuses the RISC-V decoder on an x86 byte stream — documented
# illustrative-only preset, excluded from every correctness assertion (it is
# still smoke-tested by test_matrix.py).
EXCLUDED_PRESETS = {"x86/superscalar"}

# ════════════════════════════════════════════════════════════════════
# Canonical programs: (name, asm, expected_regs, expected_mem_by_byte_addr)
# Branches deliberately use equality forms (BEQ/BNE, CBZ/CBNZ, JE/JNE):
# ARM/x86 signed-compare branches are a documented limitation.
# ════════════════════════════════════════════════════════════════════
PROGRAMS = {
    "riscv": {
        "alu": ("""
            ADDI x1, x0, 12
            ADDI x2, x0, 10
            ADD  x3, x1, x2
            SUB  x4, x1, x2
            AND  x5, x1, x2
            OR   x6, x1, x2
            XOR  x7, x1, x2
            NOP
        """, {"x1": 12, "x2": 10, "x3": 22, "x4": 2, "x5": 8, "x6": 14, "x7": 6}, {}),
        "mem": ("""
            ADDI x1, x0, 42
            SW   x1, 0(x0)
            ADDI x2, x0, 7
            SW   x2, 4(x0)
            LW   x3, 0(x0)
            LW   x4, 4(x0)
            ADD  x5, x3, x4
            NOP
        """, {"x3": 42, "x4": 7, "x5": 49}, {0: 42, 4: 7}),
        "branch_taken": ("""
            ADDI x1, x0, 5
            BEQ  x0, x0, skip
            ADDI x1, x0, 99
            skip:
            ADDI x2, x0, 7
            NOP
        """, {"x1": 5, "x2": 7}, {}),
        "branch_not_taken": ("""
            ADDI x1, x0, 5
            BEQ  x1, x0, skip
            ADDI x2, x0, 7
            skip:
            NOP
        """, {"x1": 5, "x2": 7}, {}),
        "loop": ("""
            ADDI x1, x0, 5
            ADDI x2, x0, 0
            loop:
            ADD  x2, x2, x1
            ADDI x1, x1, -1
            BNE  x1, x0, loop
            NOP
        """, {"x1": 0, "x2": 15}, {}),
    },
    "arm": {
        "alu": ("""
            MOVZ X1, #12
            MOVZ X2, #10
            ADD  X3, X1, X2
            SUB  X4, X1, X2
            AND  X5, X1, X2
            ORR  X6, X1, X2
            EOR  X7, X1, X2
            NOP
        """, {"X1": 12, "X2": 10, "X3": 22, "X4": 2, "X5": 8, "X6": 14, "X7": 6}, {}),
        "mem": ("""
            MOVZ X1, #0
            MOVZ X2, #42
            STR  X2, [X1, #0]
            MOVZ X3, #7
            STR  X3, [X1, #8]
            LDR  X4, [X1, #0]
            LDR  X5, [X1, #8]
            ADD  X6, X4, X5
            NOP
        """, {"X4": 42, "X5": 7, "X6": 49}, {0: 42, 8: 7}),
        "branch_taken": ("""
            MOVZ X1, #5
            CBZ  X2, skip
            MOVZ X1, #99
            skip:
            MOVZ X3, #7
            NOP
        """, {"X1": 5, "X3": 7}, {}),
        "branch_not_taken": ("""
            MOVZ X1, #5
            CBZ  X1, skip
            MOVZ X4, #7
            skip:
            NOP
        """, {"X1": 5, "X4": 7}, {}),
        "loop": ("""
            MOVZ X1, #5
            MOVZ X2, #0
            loop:
            ADD  X2, X2, X1
            SUB  X1, X1, #1
            CBNZ X1, loop
            NOP
        """, {"X1": 0, "X2": 15}, {}),
    },
    "x86": {
        "alu": ("""
            MOV EAX, 12
            MOV ECX, 10
            MOV EDX, EAX
            ADD EDX, ECX
            MOV EBX, EAX
            SUB EBX, ECX
            MOV ESI, EAX
            AND ESI, ECX
            MOV EDI, EAX
            OR  EDI, ECX
            NOP
        """, {"EAX": 12, "ECX": 10, "EDX": 22, "EBX": 2, "ESI": 8, "EDI": 14}, {}),
        "mem": ("""
            MOV EAX, 42
            MOV ECX, 0
            MOV [ECX], EAX
            MOV EBX, [ECX]
            MOV EDX, 7
            MOV [ECX+4], EDX
            MOV ESI, [ECX+4]
            NOP
        """, {"EBX": 42, "ESI": 7}, {0: 42, 4: 7}),
        "branch_taken": ("""
            MOV EAX, 5
            CMP EAX, 5
            JE skip
            MOV EBX, 99
            skip:
            MOV ECX, 7
            NOP
        """, {"EBX": 0, "ECX": 7}, {}),
        "branch_not_taken": ("""
            MOV EAX, 5
            CMP EAX, 3
            JE skip
            MOV EBX, 7
            skip:
            NOP
        """, {"EBX": 7}, {}),
        "loop": ("""
            MOV EAX, 0
            MOV ECX, 5
            loop:
            ADD EAX, 1
            CMP EAX, ECX
            JNE loop
            MOV EBX, EAX
            NOP
        """, {"EAX": 5, "EBX": 5}, {}),
    },
}


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════
def _build(preset, asm, branch_predictor=None, num_lanes=2):
    p = PRESETS[preset]
    program = assemble(p["isa"], asm)
    kwargs = {}
    if branch_predictor is not None:
        kwargs["branch_predictor"] = branch_predictor
    if p["model"] == "superscalar":
        kwargs["num_lanes"] = num_lanes
    return p["build"](program, **kwargs)


def _extract(state):
    regs = state["regfile"]["registers"]
    mem = None
    for k, v in state.items():
        if isinstance(v, dict) and "memory" in v and "imem" not in k.lower():
            mem = v["memory"]
    return regs, mem


def _run(preset, asm, branch_predictor=None, num_lanes=2, cycles=None):
    cpu = _build(preset, asm, branch_predictor, num_lanes)
    n = cycles if cycles is not None else CYCLES[PRESETS[preset]["model"]]
    return run_simulation(cpu, num_cycles=n)


def _settled(states, tail=10):
    """Last <tail> cycles share identical regs+mem => program terminated."""
    snaps = [_extract(s) for s in states[-tail:]]
    return len(states) >= tail and all(s == snaps[0] for s in snaps)


def _assert_final_state(preset, states, exp_regs, exp_mem, ctx=""):
    isa = PRESETS[preset]["isa"]
    regs, mem = _extract(states[-1])
    assert _settled(states), \
        f"{preset}{ctx}: did not settle within {len(states)} cycles"
    fails = []
    for rn, ev in exp_regs.items():
        idx = REG_MAPS[isa][rn]
        if regs[idx] != ev:
            fails.append(f"{rn}={regs[idx]} expected {ev}")
    for ba, ev in exp_mem.items():
        wa = ba // 4
        act = mem[wa] if mem and wa < len(mem) else None
        if act != ev:
            fails.append(f"mem[{ba}]={act} expected {ev}")
    assert not fails, f"{preset}{ctx}: " + "; ".join(fails)


# ════════════════════════════════════════════════════════════════════
# 1. ISA x MODEL correctness matrix
# ════════════════════════════════════════════════════════════════════
def _matrix_params():
    params = []
    for preset, p in sorted(PRESETS.items()):
        if preset in EXCLUDED_PRESETS:
            continue
        for name in PROGRAMS[p["isa"]]:
            params.append(pytest.param(preset, name, id=f"{preset}|{name}"))
    return params


@pytest.mark.parametrize("preset,name", _matrix_params())
def test_final_state_correct(preset, name):
    """Every (non-excluded) preset must reach the architecturally-correct
    final registers/memory on each canonical program of its ISA."""
    asm, exp_regs, exp_mem = PROGRAMS[PRESETS[preset]["isa"]][name]
    states = _run(preset, asm)
    _assert_final_state(preset, states, exp_regs, exp_mem, f" [{name}]")


# ════════════════════════════════════════════════════════════════════
# 2. Superscalar lane-width sweep (riscv + arm; x86/superscalar excluded)
# ════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("preset", ["riscv/superscalar", "arm/superscalar"])
@pytest.mark.parametrize("num_lanes", [1, 2, 4])
@pytest.mark.parametrize("name", ["alu", "loop"])
def test_superscalar_lane_widths(preset, num_lanes, name):
    """Correct final state regardless of issue width."""
    asm, exp_regs, exp_mem = PROGRAMS[PRESETS[preset]["isa"]][name]
    states = _run(preset, asm, num_lanes=num_lanes)
    _assert_final_state(preset, states, exp_regs, exp_mem,
                        f" [{name}, lanes={num_lanes}]")


# ════════════════════════════════════════════════════════════════════
# 3. OoO store->load ordering (regression, formerly a pinned gap)
#    Stores write memory at ROB commit; the RS must therefore hold a load
#    while any OLDER store is uncommitted, so the tightest possible
#    store->load sequence still reads the freshly stored value.
# ════════════════════════════════════════════════════════════════════
_TIGHT_STORE_LOAD = {
    "riscv": ("ADDI x1, x0, 42\nSW x1, 0(x0)\nLW x3, 0(x0)\nNOP\n", "x3"),
    "arm": ("MOVZ X1, #42\nSTR X1, [X0, #0]\nLDR X3, [X0, #0]\nNOP\n", "X3"),
    "x86": ("MOV EAX, 42\nMOV ECX, 0\nMOV [ECX], EAX\nMOV EBX, [ECX]\nNOP\n", "EBX"),
}


@pytest.mark.parametrize("isa", ["riscv", "arm", "x86"])
def test_ooo_tight_store_load_ordering(isa):
    asm, reg = _TIGHT_STORE_LOAD[isa]
    states = _run(f"{isa}/ooo", asm)
    regs, _ = _extract(states[-1])
    assert regs[REG_MAPS[isa][reg]] == 42, \
        f"{isa}/ooo: load after tight store read stale memory"


# ════════════════════════════════════════════════════════════════════
# 3b. x86 stack ops (PUSH/POP)
#     PUSH is fully modelled: mem[ESP-4] <- reg AND ESP <- ESP-4 (the
#     multicycle controller formerly dropped the ESP write for stores that
#     also write a register — regression-pinned here).
#     POP loads the value but CANNOT restore ESP: the datapath has a single
#     register write port and the decoder contract one rd, so POP's second
#     write (ESP <- ESP+4) is inexpressible — strict xfail documents it.
# ════════════════════════════════════════════════════════════════════
_PUSH_POP = "MOV ESP, 64\nMOV EAX, 99\nPUSH EAX\nMOV EAX, 0\nPOP EBX\nNOP\n"
_X86_INORDER = ["x86/single_cycle", "x86/multicycle", "x86/pipeline"]


@pytest.mark.parametrize("preset", _X86_INORDER)
def test_x86_push_updates_esp_and_pop_loads_value(preset):
    """PUSH writes mem[60]=99 and decrements ESP to 60; POP then reads that
    slot back. Identical across all in-order x86 models."""
    states = _run(preset, _PUSH_POP)
    regs, mem = _extract(states[-1])
    assert regs[X86_REGS["EBX"]] == 99, f"{preset}: POP loaded wrong value"
    assert regs[X86_REGS["ESP"]] == 60, f"{preset}: PUSH did not update ESP"
    assert mem[60 // 4] == 99, f"{preset}: PUSH did not write the stack slot"


@pytest.mark.parametrize("preset", _X86_INORDER)
@pytest.mark.xfail(reason="POP cannot restore ESP: single-write-port datapath "
                          "/ one-rd decoder contract cannot express POP's "
                          "second register write (ESP += 4)", strict=True)
def test_x86_pop_restores_esp_GAP(preset):
    states = _run(preset, _PUSH_POP)
    regs, _ = _extract(states[-1])
    assert regs[X86_REGS["ESP"]] == 64


# ════════════════════════════════════════════════════════════════════
# 4. PREDICTOR x MODEL x ISA matrix
#    Predictors change timing, never architectural results: every
#    prediction-capable preset must reach the same correct final state on the
#    canonical loop under every predictor at both stages.
# ════════════════════════════════════════════════════════════════════
PREDICTION_PRESETS = sorted(
    p for p, cfg in PRESETS.items()
    if cfg["model"] in ("pipeline", "ooo", "superscalar")
    and p not in EXCLUDED_PRESETS
)
PREDICTION_STAGES = ["id", "if"]

@pytest.mark.parametrize("stage", PREDICTION_STAGES)
@pytest.mark.parametrize("pred_name", sorted(PREDICTOR_CLASSES))
@pytest.mark.parametrize("preset", PREDICTION_PRESETS)
def test_predictor_loop_final_state(preset, pred_name, stage):
    isa = PRESETS[preset]["isa"]
    asm, exp_regs, exp_mem = PROGRAMS[isa]["loop"]
    predictor = PREDICTOR_CLASSES[pred_name](prediction_stage=stage)
    states = _run(preset, asm, branch_predictor=predictor)
    _assert_final_state(preset, states, exp_regs, exp_mem,
                        f" [loop, {pred_name}/{stage}]")


@pytest.mark.parametrize("preset", PREDICTION_PRESETS)
def test_predictor_invariance_full_regfile(preset):
    """Stronger than the named-register check above: the ENTIRE final register
    file must be identical across all predictor x stage combinations."""
    isa = PRESETS[preset]["isa"]
    asm, _, _ = PROGRAMS[isa]["loop"]
    finals = {}
    for pred_name in sorted(PREDICTOR_CLASSES):
        for stage in PREDICTION_STAGES:
            predictor = PREDICTOR_CLASSES[pred_name](prediction_stage=stage)
            states = _run(preset, asm, branch_predictor=predictor)
            regs, _ = _extract(states[-1])
            finals[(pred_name, stage)] = tuple(regs)
    unique = set(finals.values())
    assert len(unique) == 1, (
        f"{preset}: predictors changed the final architectural state — "
        f"{len(unique)} variants across {sorted(finals)}"
    )


# ════════════════════════════════════════════════════════════════════
# 5. Predictor unit contract (parameterized over the discovered registry, so
#    future predictors are swept automatically)
# ════════════════════════════════════════════════════════════════════
REQUIRED_PORTS = {"pc", "is_branch", "is_jal", "imm", "prediction",
                  "predict_target", "update_en", "update_pc", "actual",
                  "update_target"}

# Direction each predictor must produce at ID-stage for (a fresh table):
#   on a conditional branch, and on a JAL.
FRESH_DIRECTION = {
    "always_taken": (1, 1),
    "never_taken": (0, 1),
    "no_prediction": (0, 0),
    "bimodal": (1, 1),       # counters init weakly-taken (2)
    "gshare": (1, 1),        # counters init weakly-taken (2)
    "btb": (1, 1),           # bimodal shim
}


def _predict_at(pred, pc, is_branch=0, is_jal=0, imm=0):
    pred._ports["pc"] = pc
    pred._ports["is_branch"] = is_branch
    pred._ports["is_jal"] = is_jal
    pred._ports["imm"] = imm
    pred.evaluate()
    return pred["prediction"], pred["predict_target"]


def _train(pred, pc, taken, target=0, times=1):
    pred._ports["update_en"] = 1
    pred._ports["update_pc"] = pc
    pred._ports["actual"] = 1 if taken else 0
    pred._ports["update_target"] = target
    for _ in range(times):
        pred.rising_edge()
    pred._ports["update_en"] = 0


@pytest.mark.parametrize("stage", PREDICTION_STAGES)
@pytest.mark.parametrize("pred_name", sorted(PREDICTOR_CLASSES))
def test_predictor_contract(pred_name, stage):
    """Every registered predictor: subclasses the base, exposes the full port
    contract, honours prediction_stage, emits a binary prediction, and its
    get_state() is JSON-serialisable (the UI renders it every cycle)."""
    pred = PREDICTOR_CLASSES[pred_name](prediction_stage=stage)
    assert isinstance(pred, BranchPredictorBase)
    assert pred.prediction_stage == stage
    assert REQUIRED_PORTS <= set(pred.ports_spec.keys())
    for is_branch, is_jal in ((0, 0), (1, 0), (0, 1)):
        prediction, _ = _predict_at(pred, 0x40, is_branch, is_jal, imm=8)
        assert prediction in (0, 1), f"{pred_name}: non-binary prediction"
    json.dumps(pred.get_state())


@pytest.mark.parametrize("pred_name", sorted(PREDICTOR_CLASSES))
def test_predictor_fresh_direction_id_stage(pred_name):
    """Documented cold-start direction at ID-stage (fresh tables)."""
    if pred_name not in FRESH_DIRECTION:
        pytest.skip(f"no documented fresh direction for {pred_name}")
    exp_branch, exp_jal = FRESH_DIRECTION[pred_name]
    pred = PREDICTOR_CLASSES[pred_name](prediction_stage="id")
    prediction, _ = _predict_at(pred, 0x100, is_branch=1)
    assert prediction == exp_branch, f"{pred_name}: branch direction"
    prediction, _ = _predict_at(pred, 0x100, is_jal=1)
    assert prediction == exp_jal, f"{pred_name}: JAL direction"
    # A non-branch, non-jump instruction is never predicted taken.
    prediction, _ = _predict_at(pred, 0x100)
    assert prediction == 0, f"{pred_name}: predicted taken on a non-branch"


@pytest.mark.parametrize("pred_name", ["bimodal", "gshare"])
def test_dynamic_predictor_learns_both_directions(pred_name):
    """2-bit-counter predictors converge: repeated not-taken training drives
    the prediction to 0, repeated taken training back to 1 (ID-stage, where
    the direction table alone decides)."""
    pred = PREDICTOR_CLASSES[pred_name](prediction_stage="id")
    pc = 0x100
    _train(pred, pc, taken=False, times=4)
    prediction, target = _predict_at(pred, pc, is_branch=1, imm=16)
    assert prediction == 0, f"{pred_name}: did not learn not-taken"
    assert target == 0, f"{pred_name}: target must be 0 when not-taken"
    _train(pred, pc, taken=True, times=4)
    prediction, target = _predict_at(pred, pc, is_branch=1, imm=16)
    assert prediction == 1, f"{pred_name}: did not re-learn taken"
    assert target == pc + 16, f"{pred_name}: ID-stage target is pc+imm"


@pytest.mark.parametrize("pred_name", sorted(PREDICTOR_CLASSES))
def test_if_stage_btb_target_contract(pred_name):
    """At IF-stage the decoder ports are not wired, so a taken prediction must
    carry the BTB-cached target (never pc+imm). Predictors whose direction
    logic says not-taken must stay 0 even on a strong BTB hit."""
    pred = PREDICTOR_CLASSES[pred_name](prediction_stage="if")
    pc, target = 0x100, 0x40

    # Cold BTB: everything predicts not-taken at IF (no target known).
    prediction, ptarget = _predict_at(pred, pc)
    assert (prediction, ptarget) == (0, 0), f"{pred_name}: cold-BTB miss"

    _train(pred, pc, taken=True, target=target, times=3)
    prediction, ptarget = _predict_at(pred, pc)
    if pred_name in ("never_taken", "no_prediction"):
        assert prediction == 0, f"{pred_name}: must never predict taken"
    else:
        assert prediction == 1, f"{pred_name}: strong BTB hit must predict taken"
        assert ptarget == target, \
            f"{pred_name}: taken IF-stage prediction must use the BTB target"

    # An untrained PC (different BTB set) still predicts not-taken.
    prediction, ptarget = _predict_at(pred, pc + 8)
    assert (prediction, ptarget) == (0, 0), f"{pred_name}: untrained PC"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
