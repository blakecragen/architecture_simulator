"""
Correctness coverage for the OoO and Superscalar execution models — and for the
x86 multicycle / pipeline models — on REAL example programs.

WHY THIS FILE EXISTS (three audited coverage gaps it closes):

  FINDING 1 — test_program_results.py's model-selection policy never schedules
    superscalar for ANY program, and never schedules riscv/ooo. So a regression
    in those configs on a real algorithm/hazard program would slip through. Here
    we run a curated set of KNOWN-CORRECT straight-line + register-hazard example
    programs on riscv/ooo, riscv/superscalar, and arm/superscalar and assert they
    reach the SAME architectural state (registers + nonzero memory) as the
    single_cycle oracle — the same reference-model strategy test_matrix uses.

  FINDING 2 — x86 multicycle / pipeline (which had a documented severe
    "every-other-instruction" variable-length fetch-drop bug) were only ever
    regression-tested on 2-3 instruction snippets, never on a real multi-
    instruction x86 example program. Here a few representative x86 example
    programs run on x86/multicycle and x86/pipeline and must match the
    single_cycle oracle.

ORACLE: single_cycle (the simplest, fully-trusted model), exactly as test_matrix
does. We assert the WHOLE architectural register file and the nonzero data memory
agree — stronger than only checking the cells named in the program's `Expected:`
annotation.

SCOPING (documented known gaps — deliberately NOT asserted here):
  * x86 superscalar reuses the RISC-V decoder on an x86 byte stream
    (illustrative-only) — x86/superscalar correctness is NEVER asserted.
  (The historical OoO load-store disambiguation gap is FIXED — the RS now holds
  loads while an older store is uncommitted — so load_use.asm is back in the
  OoO set below.)
  * Superscalar has residual lane-0-only branch resolution divergence on
    branch/loop-heavy programs — so only straight-line + register-hazard
    programs are used here.

Every (program, model) pair below was empirically verified to AGREE with the
single_cycle oracle before being added (programs that diverge on the known gaps
above were excluded). Cycle budgets are generous so OoO/superscalar fully drain
their in-order commits.

Run from repo root:  python3 -m pytest tests/ -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.harness import simulate

ROOT = os.path.join(os.path.dirname(__file__), "..")


# Cycle budgets: OoO/superscalar need extra cycles to drain in-order commit; the
# in-order x86 models need a large budget at the 4x multicycle cost.
CYCLES = {
    "single_cycle": 120,
    "multicycle": 300,
    "pipeline": 120,
    "ooo": 250,
    "superscalar": 250,
}


def _read(rel_path):
    with open(os.path.join(ROOT, rel_path)) as fh:
        return fh.read()


def _run(isa, model, text):
    """Assemble + simulate via the harness; return (registers, nonzero_memory)."""
    kwargs = {"asm": text, "cycles": CYCLES[model]}
    if model == "superscalar":
        kwargs["num_lanes"] = 2
    r = simulate(isa, model, **kwargs)
    return list(r.registers), r.nonzero_memory()


def _assert_matches_single_cycle(isa, model, rel_path):
    """The model must reach the SAME registers + nonzero memory as single_cycle."""
    text = _read(rel_path)
    ref_regs, ref_mem = _run(isa, "single_cycle", text)
    got_regs, got_mem = _run(isa, model, text)

    assert got_regs == ref_regs, (
        f"{isa}/{model} vs single_cycle on {rel_path}: register file differs at "
        + ", ".join(
            f"r{i}: ref={ref_regs[i]} got={got_regs[i]}"
            for i in range(len(ref_regs))
            if ref_regs[i] != got_regs[i]
        )
    )
    assert got_mem == ref_mem, (
        f"{isa}/{model} vs single_cycle on {rel_path}: nonzero data memory "
        f"differs: ref={ref_mem} got={got_mem}"
    )


# ════════════════════════════════════════════════════════════════════
# FINDING 1 — RISC-V OoO on real straight-line / register-hazard programs.
#   (load_use.asm included since the OoO store->load ordering fix.)
# ════════════════════════════════════════════════════════════════════
RISCV_OOO_PROGRAMS = [
    "programs/riscv/instructions/arithmetic.asm",
    "programs/riscv/instructions/logical.asm",
    "programs/riscv/instructions/memory.asm",
    "programs/riscv/hazards/raw_hazard.asm",
    "programs/riscv/hazards/double_forward.asm",
    "programs/riscv/hazards/load_use.asm",
]


@pytest.mark.parametrize("rel_path", RISCV_OOO_PROGRAMS,
                         ids=[os.path.basename(p) for p in RISCV_OOO_PROGRAMS])
def test_riscv_ooo_matches_single_cycle_on_straightline_programs(rel_path):
    """RISC-V OoO must reach the same architectural state as single_cycle on
    straight-line / register-hazard example programs (including load_use.asm,
    which exercises the store->load ordering fix)."""
    _assert_matches_single_cycle("riscv", "ooo", rel_path)


# ════════════════════════════════════════════════════════════════════
# FINDING 1 — RISC-V Superscalar on real straight-line / hazard programs.
#   (load_use.asm INCLUDED: verified to AGREE on superscalar.)
# ════════════════════════════════════════════════════════════════════
RISCV_SUPERSCALAR_PROGRAMS = [
    "programs/riscv/instructions/arithmetic.asm",
    "programs/riscv/instructions/logical.asm",
    "programs/riscv/instructions/memory.asm",
    "programs/riscv/hazards/raw_hazard.asm",
    "programs/riscv/hazards/double_forward.asm",
    "programs/riscv/hazards/load_use.asm",
]


@pytest.mark.parametrize("rel_path", RISCV_SUPERSCALAR_PROGRAMS,
                         ids=[os.path.basename(p) for p in RISCV_SUPERSCALAR_PROGRAMS])
def test_riscv_superscalar_matches_single_cycle_on_straightline_programs(rel_path):
    """RISC-V Superscalar (2-wide) must reach the same architectural state as
    single_cycle on straight-line / register-hazard example programs."""
    _assert_matches_single_cycle("riscv", "superscalar", rel_path)


# ════════════════════════════════════════════════════════════════════
# FINDING 1 — ARM Superscalar on real straight-line / hazard programs.
# ════════════════════════════════════════════════════════════════════
ARM_SUPERSCALAR_PROGRAMS = [
    "programs/arm/instructions/arithmetic.asm",
    "programs/arm/instructions/logical.asm",
    "programs/arm/instructions/memory.asm",
    "programs/arm/instructions/move.asm",
    "programs/arm/hazards/raw_hazard.asm",
    "programs/arm/hazards/double_forward.asm",
]


@pytest.mark.parametrize("rel_path", ARM_SUPERSCALAR_PROGRAMS,
                         ids=[os.path.basename(p) for p in ARM_SUPERSCALAR_PROGRAMS])
def test_arm_superscalar_matches_single_cycle_on_straightline_programs(rel_path):
    """ARM Superscalar (2-wide) must reach the same architectural state as
    single_cycle on straight-line / register-hazard example programs."""
    _assert_matches_single_cycle("arm", "superscalar", rel_path)


# ════════════════════════════════════════════════════════════════════
# FINDING 2 — x86 multicycle / pipeline on real MULTI-instruction programs.
#   These models had a severe variable-length fetch-drop bug (every-other-
#   instruction skipped), now fixed. Until now it was only regression-tested on
#   2-3 instruction snippets. Run real example programs against the single_cycle
#   oracle. (memory.asm is back in: the old multicycle divergence was the
#   MEMORY-phase controller dropping the register write of a store that also
#   writes a register — x86 PUSH's ESP decrement — now fixed, so PUSH/POP
#   behave identically across the in-order models.)
# ════════════════════════════════════════════════════════════════════
X86_INORDER_PROGRAMS = [
    "programs/x86/instructions/arithmetic.asm",
    "programs/x86/instructions/logical.asm",
    "programs/x86/instructions/memory.asm",
    "programs/x86/hazards/raw_hazard.asm",
    "programs/x86/hazards/double_forward.asm",
    "programs/x86/hazards/load_use.asm",
]


@pytest.mark.parametrize("model", ["multicycle", "pipeline"])
@pytest.mark.parametrize("rel_path", X86_INORDER_PROGRAMS,
                         ids=[os.path.basename(p) for p in X86_INORDER_PROGRAMS])
def test_x86_multicycle_pipeline_match_single_cycle_on_example_programs(model, rel_path):
    """x86 multicycle and pipeline must reach the same architectural state as
    single_cycle on real multi-instruction example programs — a strong guard
    against regression of the variable-length fetch-drop bug (which would skip
    every other instruction and yield wrong register/memory state)."""
    _assert_matches_single_cycle("x86", model, rel_path)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
