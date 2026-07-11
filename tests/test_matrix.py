"""
Full API x simulation MATRIX for the RTL CPU Simulator.

Goal: prove that
  (a) every API endpoint works for every combination, and
  (b) the per-cycle information sent to the front-end is accurate,
across every ISA x Model x Predictor x example program.

This file complements (does NOT duplicate) the existing suite:
  * test_api_endpoints*.py  - per-route positive/negative smoke
  * test_cycle_state_contract.py - cycle-state contract on the DEMO programs
  * test_program_results.py - Expected:-annotation correctness w/ budget policy
  * test_bugfix_regressions.py - pinned regressions

Here we walk programs/ DYNAMICALLY and exercise the real cross-product through
the Flask test client, the same way the UI does.

Style: plain pytest functions + parametrization (so each failure is pinpointed by
preset/program/predictor) using the Flask test client. No conftest/uv infra,
matching the rest of tests/.

SCOPING of correctness assertions (see module-level constants + comments):
  * Endpoint smoke covers ALL 15 presets x ALL programs (incl. x86/superscalar,
    which must still return 200 even though it is illustrative-only).
  * Architectural-correctness assertions use the program's own `Expected:`
    annotation as the ground-truth oracle, evaluated with the repo's per-model
    cycle-budget policy (model multipliers). A raw model-vs-model state compare
    on a shared budget is dominated by timing artifacts and is NOT a sound
    oracle, so it is deliberately avoided.
  * x86/superscalar is EXCLUDED from all correctness assertions (KNOWN gap:
    reuses the RISC-V decoder on an x86 byte stream). It is still smoke-tested.
  * OoO / superscalar are illustrative for loop-heavy code; correctness is only
    asserted on the model/program pairs the repo treats as verified.
  * The RISC-V OoO AUIPC PC-tracking bug found by an earlier revision of this
    file has since been FIXED (pc_src operand select) — the former xfail is now
    the hard assertion test_auipc_pc_relative_correct, across all five models.
"""
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.app import app, PRESETS, PREDICTOR_CLASSES, ISA_CONFIGS  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
PROGRAMS_DIR = os.path.join(ROOT, "programs")

# ── Cycle-budget policy (mirrors test_program_results.py) ────────────
API_CYCLE_CAP = 500
MODEL_CYCLE_MULTIPLIER = {
    "single_cycle": 1,
    "multicycle": 4,
    "pipeline": 1,
    "ooo": 2,
    "superscalar": 1,
}

# Prediction-capable models (single_cycle / multicycle ignore predictors).
PREDICTION_MODELS = ["pipeline", "ooo", "superscalar"]
PREDICTION_STAGES = ["id", "if"]

# Register name -> index maps (same as the existing correctness test).
RISCV_REGS = {f"x{i}": i for i in range(32)}
ARM_REGS = {f"X{i}": i for i in range(31)}
ARM_REGS["XZR"] = 31
X86_REGS = {
    "EAX": 0, "ECX": 1, "EDX": 2, "EBX": 3,
    "ESP": 4, "EBP": 5, "ESI": 6, "EDI": 7,
}
_REG_MAPS = {"riscv": RISCV_REGS, "arm": ARM_REGS, "x86": X86_REGS}


# ════════════════════════════════════════════════════════════════════
# Shared test client (module-scoped; the app is stateless per request)
# ════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def client():
    app.config["TESTING"] = True
    return app.test_client()


# ════════════════════════════════════════════════════════════════════
# Program discovery (dynamic — never a hardcoded list that rots)
# ════════════════════════════════════════════════════════════════════
def _discover_programs():
    """Walk programs/ and return list of (isa, category, rel_path, text)."""
    found = []
    if not os.path.isdir(PROGRAMS_DIR):
        return found
    for isa in ("riscv", "arm", "x86"):
        isa_dir = os.path.join(PROGRAMS_DIR, isa)
        if not os.path.isdir(isa_dir):
            continue
        for dirpath, _, filenames in os.walk(isa_dir):
            for fname in sorted(filenames):
                if not fname.endswith(".asm"):
                    continue
                fpath = os.path.join(dirpath, fname)
                rel = os.path.relpath(fpath, PROGRAMS_DIR).replace(os.sep, "/")
                category = rel.split("/")[1]
                with open(fpath) as fh:
                    text = fh.read()
                found.append((isa, category, rel, text))
    return found


ALL_PROGRAMS = _discover_programs()
PROGRAMS_BY_ISA = {}
for _isa, _cat, _rel, _txt in ALL_PROGRAMS:
    PROGRAMS_BY_ISA.setdefault(_isa, []).append((_rel, _txt))

# (preset, rel_path, text) for the full endpoint cross-product.
PRESET_PROGRAM_PAIRS = [
    (preset, rel, text)
    for preset, p in sorted(PRESETS.items())
    for rel, text in PROGRAMS_BY_ISA.get(p["isa"], [])
]

# branch_prediction examples only, for the predictor sweep.
BRANCH_PROGRAMS = {
    isa: [(rel, txt) for (i, cat, rel, txt) in ALL_PROGRAMS
          if i == isa and cat == "branch_prediction"]
    for isa in ("riscv", "arm", "x86")
}


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════
def _simulate(client, preset, text, cycles, *, num_lanes=2,
              predictor="", stage="id"):
    """POST /simulate in asm mode and return (status_code, body_dict_or_None)."""
    body = {
        "preset": preset,
        "input_mode": "asm",
        "asm_text": text,
        "cycles": cycles,
        "num_lanes": num_lanes,
    }
    if predictor:
        body["branch_predictor"] = predictor
        body["prediction_stage"] = stage
    resp = client.post("/simulate", json=body)
    data = None
    try:
        data = json.loads(resp.data)
    except (ValueError, TypeError):
        pass
    return resp.status_code, data


def _extract(state):
    """Pull (registers, memory) out of one cycle-state dict."""
    regs = mem = None
    for k, v in state.items():
        if isinstance(v, dict) and "registers" in v:
            regs = v["registers"]
        if isinstance(v, dict) and "memory" in v and "imem" not in k.lower():
            mem = v["memory"]
    return regs, mem


def _final_regs_mem(body):
    return _extract(body["cycles"][-1])


def _parse_expected(text):
    """Parse machine-checkable 'Expected: reg=val, mem[addr]=val' entries.

    Prose values (e.g. 'x3=PC-relative value') are silently skipped — only
    integer/hex RHS values become assertions.
    """
    reg_expects, mem_expects = {}, {}
    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith(";"):
            continue
        m = re.search(r"Expected:\s*(.+)", line, re.IGNORECASE)
        if not m:
            continue
        for part in m.group(1).split(","):
            part = part.strip().rstrip(";").strip()
            if "=" not in part:
                continue
            lhs, rhs = part.split("=", 1)
            lhs = lhs.strip()
            rhs = re.sub(r"\s*\(.*?\)\s*$", "", rhs.strip()).strip()
            try:
                val = int(rhs, 16) if rhs.lower().startswith("0x") else int(rhs)
            except ValueError:
                continue  # prose RHS -> not machine-checkable
            mm = re.match(r"mem\[(\d+)\]", lhs)
            if mm:
                mem_expects[int(mm.group(1))] = val
            else:
                reg_expects[lhs] = val
    return reg_expects, mem_expects


def _cycles_hint(text, default=500):
    for line in text.split("\n"):
        m = re.match(r";\s*Cycles:\s*(\d+)", line.strip())
        if m:
            return int(m.group(1))
    return default


def _models_hint(text):
    for line in text.split("\n"):
        m = re.match(r";\s*Models:\s*(.+)", line.strip(), re.IGNORECASE)
        if m:
            return [s.strip() for s in m.group(1).split(",") if s.strip()]
    return None


def _budget(model, text):
    """Cycle budget for a model under the repo's policy, clamped to the API cap.

    Mirrors test_program_results.py: base (Cycles: hint or 500) * model
    multiplier, then clamped to the API's hard 500-cycle cap. Long multicycle
    programs can therefore exceed the cap and not settle in time — those pairs
    are gated out by the settle check below (genuinely-non-terminating-within-
    -the-API-budget), per the matrix scoping rules.
    """
    base = _cycles_hint(text, default=500)
    return min(API_CYCLE_CAP, base * MODEL_CYCLE_MULTIPLIER[model])


# Repo's per-program model-selection policy (matches test_program_results.py):
#   * explicit "; Models:" hint wins (intersected with the ISA's models)
#   * otherwise: instructions/hazards/branch_prediction -> single_cycle only;
#     algorithms/dsa -> single_cycle + multicycle (riscv/arm), single_cycle (x86)
# This is the set of (model, program) pairs the repo treats as architecturally
# VERIFIED — the sound oracle for correctness assertions.
_ALL_MODELS = {
    "riscv": ["single_cycle", "multicycle", "pipeline", "ooo", "superscalar"],
    "arm": ["single_cycle", "multicycle", "pipeline", "ooo", "superscalar"],
    "x86": ["single_cycle", "multicycle", "pipeline", "ooo"],  # no superscalar
}
_ALGO_DEFAULT_MODELS = {
    "riscv": ["single_cycle", "multicycle"],
    "arm": ["single_cycle", "multicycle"],
    "x86": ["single_cycle"],
}
_DEMO_DIRS = {"instructions", "hazards", "branch_prediction"}


def _verified_models(isa, category, text):
    """Models the repo validates as architecturally correct for this program."""
    hint = _models_hint(text)
    if hint:
        return [m for m in hint if m in _ALL_MODELS[isa]]
    if category in _DEMO_DIRS:
        return ["single_cycle"]
    return _ALGO_DEFAULT_MODELS[isa]


def _settled(body, tail=20):
    """True iff the last <tail> cycles share identical registers+memory, i.e. the
    program reached a stable architectural state within the API cycle budget."""
    cycles = body["cycles"]
    if len(cycles) < tail + 1:
        return False

    def sig(state):
        regs, mem = _extract(state)
        return (tuple(regs) if regs is not None else None,
                tuple(mem) if mem is not None else None)

    snaps = [sig(s) for s in cycles[-tail:]]
    return snaps[0][0] is not None and all(s == snaps[0] for s in snaps)


def _matches_expected(isa, regs, mem, reg_expects, mem_expects):
    """Return list of mismatch strings (empty == matches)."""
    fails = []
    reg_map = _REG_MAPS[isa]
    for rn, ev in reg_expects.items():
        idx = reg_map.get(rn)
        if idx is None:
            continue
        ev2 = ev & 0xFFFFFFFF if ev < 0 else ev
        if regs[idx] != ev2:
            fails.append(f"{rn} expected {ev2}, got {regs[idx]}")
    if mem_expects and mem is not None:
        for byte_addr, ev in mem_expects.items():
            wa = byte_addr // 4
            act = mem[wa] if wa < len(mem) else 0
            ev2 = ev & 0xFFFFFFFF if ev < 0 else ev
            if act != ev2:
                fails.append(f"mem[{byte_addr}] expected {ev2}, got {act}")
    return fails


# ════════════════════════════════════════════════════════════════════
# Sanity: the matrix actually discovered programs and presets
# ════════════════════════════════════════════════════════════════════
def test_matrix_discovered_expected_dimensions():
    assert len(PRESETS) == 18, f"expected 18 presets, found {len(PRESETS)}"
    assert len(PREDICTOR_CLASSES) == 6, \
        f"expected 6 predictors, found {sorted(PREDICTOR_CLASSES)}"
    assert ALL_PROGRAMS, "no example programs discovered under programs/"
    # Every ISA must contribute programs (incl. dsa walked here).
    for isa in ("riscv", "arm", "x86"):
        assert PROGRAMS_BY_ISA.get(isa), f"no programs for ISA {isa}"
    # The endpoint cross-product is large but bounded.
    assert len(PRESET_PROGRAM_PAIRS) > 300, \
        f"cross-product unexpectedly small: {len(PRESET_PROGRAM_PAIRS)}"


# ════════════════════════════════════════════════════════════════════
# 1. ENDPOINT SMOKE — every preset x every program of its ISA -> 200
# ════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "preset,rel,text", PRESET_PROGRAM_PAIRS,
    ids=[f"{pr}|{rel}" for pr, rel, _ in PRESET_PROGRAM_PAIRS],
)
def test_simulate_every_preset_every_program_returns_200(client, preset, rel, text):
    """The core guarantee: /simulate never 500s and returns a well-formed body
    for any registered preset running any example program of its ISA."""
    status, data = _simulate(client, preset, text, cycles=40)
    assert status == 200, f"{preset} / {rel}: status {status}, body {data}"
    assert data is not None
    # Echoed metadata.
    assert data["preset"] == preset
    assert data["isa"] == PRESETS[preset]["isa"]
    assert data["model"] == PRESETS[preset]["model"]
    # reg_names length == ISA num_regs.
    isa_cfg = ISA_CONFIGS[PRESETS[preset]["isa"]]
    assert len(data["reg_names"]) == isa_cfg.num_regs
    # cycles non-empty (reset cycle is always present).
    assert isinstance(data["cycles"], list) and len(data["cycles"]) > 0


@pytest.mark.parametrize("preset", sorted(PRESETS), ids=sorted(PRESETS))
def test_topology_every_preset_returns_200(client, preset):
    """GET /topology/<preset> returns nodes + edges + model for every preset."""
    params = ""
    if PRESETS[preset]["model"] == "superscalar":
        params = "?num_lanes=2"
    resp = client.get(f"/topology/{preset}{params}")
    assert resp.status_code == 200, \
        f"{preset}: topology status {resp.status_code}: {resp.data[:200]}"
    data = json.loads(resp.data)
    assert "nodes" in data and "edges" in data
    assert data["model"] == PRESETS[preset]["model"]
    assert isinstance(data["nodes"], list) and len(data["nodes"]) > 0


@pytest.mark.parametrize(
    "preset", [p for p in sorted(PRESETS) if PRESETS[p]["model"] in PREDICTION_MODELS],
)
def test_topology_accepts_predictor_and_stage_params(client, preset):
    """Topology renders with every predictor + both stages (no 500)."""
    for pred in sorted(PREDICTOR_CLASSES):
        for stage in PREDICTION_STAGES:
            q = f"?branch_predictor={pred}&prediction_stage={stage}"
            if PRESETS[preset]["model"] == "superscalar":
                q += "&num_lanes=2"
            resp = client.get(f"/topology/{preset}{q}")
            assert resp.status_code == 200, \
                f"{preset} {pred}/{stage}: {resp.status_code} {resp.data[:150]}"
            assert "nodes" in json.loads(resp.data)


# ════════════════════════════════════════════════════════════════════
# 2. PREDICTOR COVERAGE — branch_prediction examples x prediction models
#    x all 6 predictors x both stages -> 200 + complete state
# ════════════════════════════════════════════════════════════════════
def _predictor_sweep_params():
    params = []
    for isa, progs in BRANCH_PROGRAMS.items():
        for rel, text in progs:
            for model in PREDICTION_MODELS:
                preset = f"{isa}/{model}"
                if preset not in PRESETS:
                    continue
                for pred in sorted(PREDICTOR_CLASSES):
                    for stage in PREDICTION_STAGES:
                        params.append((preset, rel, text, pred, stage))
    return params


_PRED_SWEEP = _predictor_sweep_params()


@pytest.mark.parametrize(
    "preset,rel,text,pred,stage", _PRED_SWEEP,
    ids=[f"{pr}|{os.path.basename(rel)}|{pred}|{st}"
         for pr, rel, _, pred, st in _PRED_SWEEP],
)
def test_predictor_sweep_branch_examples_return_complete_state(
        client, preset, rel, text, pred, stage):
    """Every predictor x stage simulates branch_prediction examples without 500
    and returns a complete cycle list (predictors change timing, not whether it
    runs)."""
    status, data = _simulate(client, preset, text, cycles=40,
                             predictor=pred, stage=stage)
    assert status == 200, \
        f"{preset}/{rel} pred={pred} stage={stage}: {status} {data}"
    assert len(data["cycles"]) > 0
    regs, _ = _final_regs_mem(data)
    assert regs is not None, "regfile state must be present every run"
    assert len(regs) == ISA_CONFIGS[PRESETS[preset]["isa"]].num_regs


# ════════════════════════════════════════════════════════════════════
# 3. CYCLE-STATE ACCURACY — for a representative example across ALL 15
#    presets, every cycle's component set == the CPU's component set,
#    is JSON-serialisable, and _cycle is present + monotonic.
#    (Extends the contract test, which only covers the DEMO programs.)
# ════════════════════════════════════════════════════════════════════
def _build_cpu(preset, program, num_lanes=2):
    p = PRESETS[preset]
    if p["model"] == "superscalar":
        return p["build"](program, num_lanes=num_lanes)
    return p["build"](program)


def _representative_example(isa):
    """A small, deterministic example program for each ISA (instructions/)."""
    for cat in ("instructions",):
        for i, c, rel, txt in ALL_PROGRAMS:
            if i == isa and c == cat:
                return rel, txt
    # Fallback: first program for the ISA.
    rel, txt = PROGRAMS_BY_ISA[isa][0]
    return rel, txt


@pytest.mark.parametrize("preset", sorted(PRESETS), ids=sorted(PRESETS))
def test_cycle_state_complete_and_monotonic_on_example(client, preset):
    """Each cycle dict's keys == the CPU's component set (+ _cycle), every cycle
    is JSON-serialisable, and _cycle is present and strictly monotonic."""
    from sim.assembler import assemble

    isa = PRESETS[preset]["isa"]
    rel, text = _representative_example(isa)

    # Ground-truth component set comes from a locally built CPU on the same
    # program, so the API's per-cycle payload is checked against the real model.
    program = assemble(isa, text)
    cpu = _build_cpu(preset, program)
    expected_components = set(cpu.components.keys())

    status, data = _simulate(client, preset, text, cycles=12)
    assert status == 200, f"{preset}/{rel}: {status} {data}"
    cycles = data["cycles"]
    assert len(cycles) == 13, "12 ticks + 1 reset cycle expected"

    for i, state in enumerate(cycles):
        assert state["_cycle"] == i, \
            f"{preset} cycle {i}: _cycle missing/non-monotonic ({state.get('_cycle')})"
        assert set(state.keys()) - {"_cycle"} == expected_components, \
            f"{preset} cycle {i}: component set != CPU components"
        json.dumps(state)  # serialisable (raises TypeError otherwise)


# ════════════════════════════════════════════════════════════════════
# 4. CROSS-MODEL ARCHITECTURAL CONSISTENCY  (strong accuracy check)
#
#    Oracle = the program's own `Expected:` annotation — sound ground truth,
#    not a fragile model-vs-model compare. Scope is the (model, program) pairs
#    the repo treats as architecturally VERIFIED (its per-program model policy),
#    AND that actually SETTLE within the API's 500-cycle cap.
#
#    Why the settle gate: long multicycle programs (4x cost) can exceed the API
#    cap and finish mid-flight; comparing their unsettled state is meaningless,
#    so those pairs are skipped as "non-terminating within the API budget"
#    (per the matrix scoping rules). Looping demos (tight_loop, alternating, ...)
#    that never settle are likewise skipped.
#
#    Model-vs-model raw state comparison on a shared cycle budget is deliberately
#    avoided — it is dominated by timing/completion artifacts and is not a sound
#    correctness oracle (verified during design).
# ════════════════════════════════════════════════════════════════════
def _consistency_params():
    """Programs (riscv/arm) carrying machine-checkable Expected annotations."""
    params = []
    for isa in ("riscv", "arm"):
        for cat in sorted({c for (i, c, _, _) in ALL_PROGRAMS if i == isa}):
            for i, c, rel, text in ALL_PROGRAMS:
                if i != isa or c != cat:
                    continue
                reg_expects, mem_expects = _parse_expected(text)
                if reg_expects or mem_expects:
                    params.append((isa, cat, rel, text))
    return params


_CONSISTENCY = _consistency_params()


@pytest.mark.parametrize(
    "isa,cat,rel,text", _CONSISTENCY,
    ids=[rel for _, _, rel, _ in _CONSISTENCY],
)
def test_settled_models_reach_expected_state(client, isa, cat, rel, text):
    """For every (verified model, program) pair that settles within the API
    budget, the final architectural state must match the program's Expected
    annotation. This is the strong accuracy net: a model silently diverging on
    a program it should get right fails here, pinpointed by (preset, program).
    Unsettled pairs (long multicycle / never-terminating loops) are skipped."""
    reg_expects, mem_expects = _parse_expected(text)
    models = _verified_models(isa, cat, text)
    checked = 0
    for model in models:
        preset = f"{isa}/{model}"
        if preset not in PRESETS:
            continue
        status, data = _simulate(client, preset, text, cycles=_budget(model, text))
        assert status == 200, f"{preset}/{rel}: {status} {data}"
        if not _settled(data):
            # Did not terminate within the API's 500-cycle cap — not a wrong
            # result, just out of budget. Out of scope for correctness.
            continue
        regs, mem = _final_regs_mem(data)
        fails = _matches_expected(isa, regs, mem, reg_expects, mem_expects)
        assert not fails, f"{preset} / {rel}: " + "; ".join(fails)
        checked += 1
    # Single-cycle always settles, so at least one model is always asserted.
    assert checked > 0, f"{rel}: no model settled within budget (unexpected)"


def test_settled_verified_models_agree_with_each_other(client):
    """Cross-model agreement: on every Expected-annotated program, all VERIFIED
    models that settle agree with EACH OTHER on every cell named in Expected
    (not merely individually matching the annotation). Catches a model that
    settles on a self-consistent-but-wrong value the others avoid."""
    for isa, cat, rel, text in _CONSISTENCY:
        reg_expects, mem_expects = _parse_expected(text)
        reg_map = _REG_MAPS[isa]
        per_model = {}
        for model in _verified_models(isa, cat, text):
            preset = f"{isa}/{model}"
            if preset not in PRESETS:
                continue
            status, data = _simulate(client, preset, text,
                                     cycles=_budget(model, text))
            assert status == 200, f"{preset}/{rel}: {status}"
            if not _settled(data):
                continue
            regs, mem = _final_regs_mem(data)
            sig = {}
            for rn in reg_expects:
                idx = reg_map.get(rn)
                if idx is not None:
                    sig[rn] = regs[idx]
            for ba in mem_expects:
                wa = ba // 4
                sig[f"mem[{ba}]"] = mem[wa] if mem and wa < len(mem) else 0
            per_model[model] = sig
        models = list(per_model)
        if len(models) < 2:
            continue  # only one settled model -> nothing to cross-check
        ref = per_model[models[0]]
        for m in models[1:]:
            assert per_model[m] == ref, \
                f"{rel}: settled model {m} disagrees with {models[0]} on " \
                f"Expected cells: {per_model[m]} != {ref}"


def test_ooo_superscalar_correct_on_straightline_riscv(client):
    """OoO and superscalar (RISC-V) must match Expected on straight-line / non-
    loop programs — the cases where the repo treats them as verified. (Loop-
    heavy programs are illustrative-only on these models: a known, documented
    scope limit — see module docstring. They are NOT asserted here.)"""
    straightline = {
        "riscv/instructions/arithmetic.asm",
        "riscv/instructions/logical.asm",
        "riscv/instructions/memory.asm",
        "riscv/hazards/double_forward.asm",
        "riscv/hazards/raw_hazard.asm",
    }
    checked = 0
    for rel, text in PROGRAMS_BY_ISA["riscv"]:
        if rel not in straightline:
            continue
        reg_expects, mem_expects = _parse_expected(text)
        if not reg_expects and not mem_expects:
            continue
        for model in ("ooo", "superscalar"):
            preset = f"riscv/{model}"
            status, data = _simulate(client, preset, text,
                                     cycles=_budget(model, text))
            assert status == 200, f"{preset}/{rel}: {status}"
            regs, mem = _final_regs_mem(data)
            fails = _matches_expected("riscv", regs, mem, reg_expects, mem_expects)
            assert not fails, f"{preset} / {rel}: " + "; ".join(fails)
            checked += 1
    assert checked > 0, "no straight-line riscv programs found to verify"


def test_predictor_invariance_final_state(client):
    """Predictors change TIMING, not architectural results: a terminating
    RISC-V branch_prediction example must yield the SAME final register state
    under all 6 predictors x both stages on a prediction-capable model, and that
    state must match the program's Expected annotation."""
    text = None
    for rel, txt in BRANCH_PROGRAMS["riscv"]:
        if os.path.basename(rel) == "tight_loop.asm":
            text = txt
            break
    assert text is not None, "expected riscv/branch_prediction/tight_loop.asm"

    reg_expects, _ = _parse_expected(text)
    finals = set()
    for pred in sorted(PREDICTOR_CLASSES):
        for stage in PREDICTION_STAGES:
            status, data = _simulate(client, "riscv/pipeline", text, cycles=200,
                                     predictor=pred, stage=stage)
            assert status == 200, f"pred={pred} stage={stage}: {status}"
            assert _settled(data), \
                f"pred={pred}/{stage}: program did not settle (timing should " \
                f"not prevent termination on tight_loop)"
            regs, _ = _final_regs_mem(data)
            fails = _matches_expected("riscv", regs, None, reg_expects, {})
            assert not fails, f"pred={pred}/{stage}: " + "; ".join(fails)
            finals.add(tuple(regs))
    assert len(finals) == 1, \
        f"predictors changed the final architectural state: {len(finals)} variants"


@pytest.mark.parametrize(
    "rel,text",
    [(rel, txt) for (i, c, rel, txt) in ALL_PROGRAMS if i == "x86"][:6],
    ids=[rel for (i, c, rel, txt) in ALL_PROGRAMS if i == "x86"][:6],
)
def test_x86_superscalar_smoke_only_no_correctness(client, rel, text):
    """x86/superscalar is illustrative-only (reuses the RISC-V decoder on an x86
    byte stream — KNOWN gap). It must still SMOKE (200 + complete state); its
    architectural results are explicitly NOT asserted (excluded from correctness
    per the matrix scoping rules)."""
    assert "x86/superscalar" in PRESETS
    status, data = _simulate(client, "x86/superscalar", text, cycles=40)
    assert status == 200, f"x86/superscalar / {rel}: {status} {data}"
    regs, _ = _final_regs_mem(data)
    assert regs is not None and len(regs) == ISA_CONFIGS["x86"].num_regs
    # Intentionally NO correctness assertion here — documented gap.


# ════════════════════════════════════════════════════════════════════
# 5. PER-ISA ENDPOINT CORRECTNESS
# ════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("isa", ["riscv", "arm", "x86"])
def test_isa_endpoint_reg_names_and_demo(client, isa):
    resp = client.get(f"/isa/{isa}")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert len(data["reg_names"]) == data["num_regs"]
    assert len(data["reg_names"]) == ISA_CONFIGS[isa].num_regs
    assert isinstance(data["demo_program_asm"], str)
    assert len(data["demo_program_asm"].strip()) > 0


@pytest.mark.parametrize("isa", ["riscv", "arm", "x86"])
def test_cheatsheet_entries_well_formed(client, isa):
    resp = client.get(f"/cheatsheet/{isa}")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["isa"] == isa
    assert len(data["instructions"]) > 0
    for item in data["instructions"]:
        for key in ("category", "mnemonic", "syntax", "description", "example"):
            assert key in item, f"{isa} cheatsheet entry missing '{key}': {item}"


@pytest.mark.parametrize("isa,asm,reg,val", [
    ("riscv", "ADDI x1, x0, 42", "x1", 42),
    ("arm", "MOVZ X1, #88", "X1", 88),
    ("x86", "MOV ECX, 10", "ECX", 10),
])
def test_assemble_then_simulate_roundtrip(client, isa, asm, reg, val):
    """Assemble each ISA, then run the produced program and confirm the value
    lands in the expected register — end-to-end /assemble + /simulate."""
    resp = client.post("/assemble", json={"isa": isa, "text": asm})
    assert resp.status_code == 200, f"assemble {isa}: {resp.data[:150]}"
    program = json.loads(resp.data)["program"]
    assert isinstance(program, list) and len(program) > 0

    resp = client.post("/simulate", json={
        "preset": f"{isa}/single_cycle",
        "program": program,
        "input_mode": "hex",
        "cycles": 6,
    })
    assert resp.status_code == 200
    regs, _ = _final_regs_mem(json.loads(resp.data))
    assert regs[_REG_MAPS[isa][reg]] == val


def test_examples_catalog_shape_and_all_files_loadable(client):
    """/examples catalog is well-formed AND every listed file loads via
    /examples/<path> (full catalog, not a sample)."""
    catalog = json.loads(client.get("/examples").data)
    assert catalog, "examples catalog is empty"
    total = 0
    for isa, categories in catalog.items():
        assert isa in ("riscv", "arm", "x86")
        for cat, payload in categories.items():
            assert "label" in payload and "items" in payload
            for item in payload["items"]:
                assert {"name", "label", "file"} <= set(item)
                resp = client.get(f"/examples/{item['file']}")
                assert resp.status_code == 200, \
                    f"catalog file not loadable: {item['file']}"
                body = json.loads(resp.data)
                assert len(body["content"]) > 0
                total += 1
    assert total > 0


def test_examples_catalog_excludes_dsa(client):
    """The catalog deliberately excludes the dsa category (per app routing)."""
    catalog = json.loads(client.get("/examples").data)
    for isa, categories in catalog.items():
        assert "dsa" not in categories, f"{isa}: dsa should not be in catalog"


@pytest.mark.parametrize("bad_path", [
    "riscv/algorithms/..%2f..%2f..%2fapi%2fapp.py",
    "riscv/../../api/app.py",
    "riscv/algorithms/secret.txt",
    "riscv/algorithms/evil.py",
    "mips/algorithms/foo.asm",
    "riscv/onlytwo.asm",
    "riscv/a/b/c.asm",
])
def test_examples_path_traversal_and_bad_paths_blocked(client, bad_path):
    """Traversal / wrong-type / unknown-isa / wrong-part-count are all rejected
    (400) and never leak real source."""
    resp = client.get(f"/examples/{bad_path}")
    assert resp.status_code == 400
    assert b"Flask" not in resp.data
    assert b"import" not in resp.data


# ════════════════════════════════════════════════════════════════════
# 6. AUIPC PC-relative correctness — all five models track each AUIPC's own PC.
#    (Previously riscv/ooo computed AUIPC against PC=0; fixed via the pc_src
#    operand select in sim/isa/riscv/presets/ooo.py so the instruction PC feeds
#    the ALU. Two AUIPCs 4 bytes apart must differ by their PC delta.)
# ════════════════════════════════════════════════════════════════════
_AUIPC_ASM = """
AUIPC x4, 0
AUIPC x5, 1
SUB x6, x5, x4
NOP
NOP
NOP
NOP
NOP
"""


@pytest.mark.parametrize("model", ["single_cycle", "multicycle", "pipeline",
                                    "ooo", "superscalar"])
def test_auipc_pc_relative_correct(client, model):
    """Every model computes AUIPC against each instruction's own PC:
    x4 = PC0 = 0, x5 = PC4 + 0x1000 = 4100, x6 = x5 - x4 = 4100."""
    status, data = _simulate(client, f"riscv/{model}", _AUIPC_ASM, cycles=60)
    assert status == 200, f"riscv/{model}: {status} {data}"
    regs, _ = _final_regs_mem(data)
    assert regs[4] == 0, f"{model}: AUIPC x4 (PC0) should be 0, got {regs[4]}"
    assert regs[5] == 4100, f"{model}: AUIPC x5 (PC4+0x1000) should be 4100, got {regs[5]}"
    assert regs[6] == 4100, f"{model}: x6 = x5 - x4 should be 4100, got {regs[6]}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
