"""
RTL CPU Simulator API.

GET  /topology/<preset>   -> nodes + edges for the UI block diagram
POST /simulate            -> per-cycle state for every component
GET  /presets             -> structured list of ISAs and execution models
GET  /isa/<name>          -> register names, description, demo program
POST /assemble            -> assemble text to hex program
POST /compile             -> compile Core-C source to assembly + program
GET  /compiler/examples   -> catalog of Core-C sample programs
GET  /compiler/examples/<name> -> content of a single Core-C sample
GET  /cheatsheet/<isa>    -> instruction cheatsheet data
GET  /examples            -> catalog of loadable example programs
GET  /examples/<path>     -> content of a single example file
"""
from flask import Flask, request, jsonify, send_from_directory
try:
    from flask_cors import CORS
except ImportError:
    CORS = None

import sys
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from sim.component.topology import generate_topology
from sim.runner_v2 import run_simulation, _arch_signature

# ── Simulator registry — single source of truth lives in sim.harness ──
from sim.harness import PRESETS, ISA_CONFIGS, PREDICTOR_CLASSES

# ── ISA-specific preset imports ──────────────────────────────────
# (build functions + ISA configs now come from sim.harness, imported above)

# ── Assembler ────────────────────────────────────────────────────
from sim.assembler import assemble
from sim.assembler.cheatsheet import get_cheatsheet

# ── Core-C compiler ──────────────────────────────────────────────
from sim.compiler import compile_c
from sim.compiler.errors import CompilerError
from sim.components.multicycle.budget_controller import (
    clock_period as _clock_period, CLASSES as _CYCLE_CLASSES, WORK as _CYCLE_WORK,
    DEFAULT_COSTS as _DEFAULT_COSTS)

UI_DIR = os.path.join(ROOT, "ui")
PROGRAMS_DIR = os.path.join(ROOT, "programs")

# ── Request-input limits (DoS / robustness guards) ───────────────
MAX_CYCLES = 2000  # raised from 500: compiled Core-C is verbose (see /compile)
MAX_AUTO_CYCLES = 10000  # cap for run_to_completion (settle-detected) runs
MAX_LANES = 8
MAX_PROGRAM_WORDS = 4096


def _coerce_int(value, default):
    """Coerce a request value to int.

    Returns ``default`` when ``value`` is None, or ``None`` when the value
    is present but not convertible (the caller turns that into a 400).
    """
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


app = Flask(__name__, static_folder=os.path.join(UI_DIR, "static"))
if CORS:
    CORS(app)


# ISA_CONFIGS, PRESETS, and PREDICTOR_CLASSES are imported from sim.harness
# (the standalone backend simulator — single source of truth for the registry).


# ── Demo-program text formatters ────────────────────────────────
def _format_demo_text_words(isa_cfg):
    """Format word-format demo programs (RISC-V, ARM) for the textarea."""
    program = isa_cfg.demo_program()
    comments = _get_demo_comments(isa_cfg.name)
    lines = []
    for i, word in enumerate(program):
        hex_str = f"0x{word:08X}"
        comment = comments[i] if i < len(comments) else ""
        if comment:
            lines.append(f"{hex_str}  # {comment}")
        else:
            lines.append(hex_str)
    return "\n".join(lines)


def _format_demo_text_bytes(isa_cfg):
    """Format byte-format demo programs (x86) for the textarea."""
    annotations = _get_x86_demo_annotations()
    lines = []
    for ann in annotations:
        byte_str = " ".join(f"{b:02X}" for b in ann["bytes"])
        lines.append(f"{byte_str}  # {ann['comment']}")
    if not annotations:
        for b in isa_cfg.demo_program():
            lines.append(f"{b:02X}")
    return "\n".join(lines)


def _get_demo_comments(isa_name):
    if isa_name == "riscv":
        return [
            "ADDI  x1, x0, 10   ; N = 10",
            "ADDI  x2, x0, 0    ; fib_prev = 0",
            "ADDI  x3, x0, 1    ; fib_curr = 1",
            "ADD   x4, x2, x3   ; temp = prev + curr",
            "ADDI  x2, x3, 0    ; prev = curr",
            "ADDI  x3, x4, 0    ; curr = temp",
            "ADDI  x1, x1, -1   ; N--",
            "BNE   x1, x0, loop ; if N != 0 goto loop",
        ]
    elif isa_name == "arm":
        return [
            "MOVZ X1, #10       ; N = 10",
            "MOVZ X2, #0        ; fib_prev = 0",
            "MOVZ X3, #1        ; fib_curr = 1",
            "ADD  X4, X2, X3    ; temp = prev + curr",
            "ADD  X2, X3, XZR   ; prev = curr",
            "ADD  X3, X4, XZR   ; curr = temp",
            "SUB  X1, X1, #1    ; N--",
            "CMP  X1, XZR       ; set flags",
            "B.NE loop          ; if N != 0 goto loop",
        ]
    return []


def _get_x86_demo_annotations():
    return [
        {"bytes": [0xB9, 0x0A, 0x00, 0x00, 0x00], "comment": "MOV ECX, 10  ; N = 10"},
        {"bytes": [0xB8, 0x00, 0x00, 0x00, 0x00], "comment": "MOV EAX, 0   ; fib_prev = 0"},
        {"bytes": [0xBB, 0x01, 0x00, 0x00, 0x00], "comment": "MOV EBX, 1   ; fib_curr = 1"},
        {"bytes": [0x89, 0xC2],                     "comment": "MOV EDX, EAX ; temp = prev"},
        {"bytes": [0x01, 0xDA],                     "comment": "ADD EDX, EBX ; temp += curr"},
        {"bytes": [0x89, 0xD8],                     "comment": "MOV EAX, EBX ; prev = curr"},
        {"bytes": [0x89, 0xD3],                     "comment": "MOV EBX, EDX ; curr = temp"},
        {"bytes": [0x83, 0xE9, 0x01],               "comment": "SUB ECX, 1   ; N--"},
        {"bytes": [0x83, 0xF9, 0x00],               "comment": "CMP ECX, 0   ; set flags"},
        {"bytes": [0x75, 0xF0],                     "comment": "JNE loop     ; if N != 0"},
    ]


# ── Routes ───────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(os.path.join(UI_DIR, "templates"), "cpu_simulator.html")


@app.route("/lab")
def program_lab():
    """Program Lab — the compiler-first Translation Bench page."""
    return send_from_directory(os.path.join(UI_DIR, "templates"), "program_lab.html")


@app.route("/presets")
def list_presets():
    """Return structured preset data grouped by ISA and model."""
    isas = {}
    for name, isa_cfg in ISA_CONFIGS.items():
        isas[name] = {
            "display_name": isa_cfg.display_name,
            "description": isa_cfg.description,
            "program_format": isa_cfg.program_format,
        }

    presets = {}
    for name, p in PRESETS.items():
        presets[name] = {
            "label": p["label"],
            "isa": p["isa"],
            "model": p["model"],
        }

    models = {
        "single_cycle": "Single Cycle",
        "multicycle": "FetDecExe",
        "pipeline": "Pipeline",
        "ooo": "Out-of-Order",
        "superscalar": "Superscalar",
    }

    return jsonify({
        "isas": isas,
        "models": models,
        "presets": presets,
    })


@app.route("/isa/<name>")
def isa_info(name: str):
    """Return ISA info including demo programs in both hex and assembly."""
    if name not in ISA_CONFIGS:
        return jsonify({"error": f"Unknown ISA '{name}'"}), 404

    isa_cfg = ISA_CONFIGS[name]
    reg_names = isa_cfg.register_names()
    program = isa_cfg.demo_program()

    if isa_cfg.program_format == "bytes":
        demo_text = _format_demo_text_bytes(isa_cfg)
    else:
        demo_text = _format_demo_text_words(isa_cfg)

    return jsonify({
        "name": isa_cfg.name,
        "display_name": isa_cfg.display_name,
        "description": isa_cfg.description,
        "num_regs": isa_cfg.num_regs,
        "reg_names": reg_names,
        "program_format": isa_cfg.program_format,
        "demo_program": program,
        "demo_program_text": demo_text,
        "demo_program_asm": isa_cfg.demo_program_asm(),
    })


@app.route("/predictors")
def list_predictors():
    """Return available branch predictor options (dynamically discovered)."""
    result = []
    for name, cls in sorted(PREDICTOR_CLASSES.items()):
        result.append({
            "name": name,
            "label": getattr(cls, "ui_label", name),
        })
    return jsonify({"predictors": result})


@app.route("/topology/<path:preset_name>")
def topology(preset_name: str):
    if preset_name not in PRESETS:
        return jsonify({"error": f"Unknown preset '{preset_name}'"}), 404

    isa_name = PRESETS[preset_name]["isa"]
    isa_cfg = ISA_CONFIGS[isa_name]
    demo = isa_cfg.demo_program()

    model = PRESETS[preset_name]["model"]
    num_lanes = _coerce_int(request.args.get("num_lanes", 2), 2)
    if num_lanes is None:
        return jsonify({"error": "'num_lanes' must be an integer"}), 400
    num_lanes = max(1, min(num_lanes, MAX_LANES))
    bp_name = request.args.get("branch_predictor", "")
    bp_stage = request.args.get("prediction_stage", "id")
    if bp_name and bp_name not in PREDICTOR_CLASSES:
        return jsonify({"error": f"Unknown branch predictor '{bp_name}'"}), 400
    bp_cls = PREDICTOR_CLASSES.get(bp_name)
    branch_predictor = bp_cls(prediction_stage=bp_stage) if bp_cls else None

    try:
        if model == "superscalar":
            cpu = PRESETS[preset_name]["build"](demo, num_lanes=num_lanes,
                                                branch_predictor=branch_predictor)
        else:
            kwargs = {}
            if branch_predictor is not None:
                kwargs["branch_predictor"] = branch_predictor
            cpu = PRESETS[preset_name]["build"](demo, **kwargs)
        topo = generate_topology(cpu)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    topo["model"] = model
    return jsonify(topo)


@app.route("/simulate", methods=["POST"])
def simulate():
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "JSON body must be an object"}), 400

    preset_name = body.get("preset", "riscv/single_cycle")
    program     = body.get("program", None)
    input_mode  = body.get("input_mode", "hex")
    asm_text    = body.get("asm_text", "")

    cycles = _coerce_int(body.get("cycles", 20), 20)
    if cycles is None:
        return jsonify({"error": "'cycles' must be an integer"}), 400
    cycles = max(0, min(cycles, MAX_CYCLES))

    # Run-to-completion mode: ignore 'cycles' and simulate until the
    # architectural state settles, capped at MAX_AUTO_CYCLES.
    run_to_completion = bool(body.get("run_to_completion", False))

    num_lanes = _coerce_int(body.get("num_lanes", 2), 2)
    if num_lanes is None:
        return jsonify({"error": "'num_lanes' must be an integer"}), 400
    num_lanes = max(1, min(num_lanes, MAX_LANES))

    bp_name     = body.get("branch_predictor", "")
    bp_stage    = body.get("prediction_stage", "id")
    if bp_name and bp_name not in PREDICTOR_CLASSES:
        return jsonify({"error": f"Unknown branch predictor '{bp_name}'"}), 400
    bp_cls = PREDICTOR_CLASSES.get(bp_name)
    branch_predictor = bp_cls(prediction_stage=bp_stage) if bp_cls else None

    if preset_name not in PRESETS:
        return jsonify({"error": f"Unknown preset '{preset_name}'"}), 400

    isa_name = PRESETS[preset_name]["isa"]
    isa_cfg = ISA_CONFIGS[isa_name]
    model = PRESETS[preset_name]["model"]

    # Assembly mode: assemble text to program
    if input_mode == "asm" and asm_text:
        try:
            program = assemble(isa_name, asm_text)
        except Exception as exc:
            return jsonify({"error": f"Assembly error: {str(exc)}"}), 400

    # If no program provided, use demo
    if not program:
        program = isa_cfg.demo_program()

    if not isinstance(program, (list, tuple)):
        return jsonify({"error": "'program' must be a list"}), 400
    if len(program) > MAX_PROGRAM_WORDS:
        return jsonify({"error": f"program too long (max {MAX_PROGRAM_WORDS} entries)"}), 400

    # Convert hex strings to ints if needed
    try:
        program = [int(p, 0) if isinstance(p, str) else int(p) for p in program]
    except (TypeError, ValueError) as exc:
        return jsonify({"error": f"invalid program entry: {exc}"}), 400

    # Per-instruction-class cycle budgets for the "configurable" model.
    cycle_costs = None
    if model == "configurable":
        raw = body.get("cycle_costs") or {}
        if not isinstance(raw, dict):
            return jsonify({"error": "'cycle_costs' must be an object"}), 400
        cycle_costs = {}
        for k in _CYCLE_CLASSES:
            v = _coerce_int(raw.get(k, _DEFAULT_COSTS[k]), _DEFAULT_COSTS[k])
            if v is None:
                return jsonify({"error": f"cycle_costs['{k}'] must be an integer"}), 400
            cycle_costs[k] = max(1, min(v, 64))   # clamp to 1..64 cycles

    try:
        if model == "superscalar":
            cpu = PRESETS[preset_name]["build"](program, num_lanes=num_lanes,
                                                branch_predictor=branch_predictor)
        elif model == "configurable":
            cpu = PRESETS[preset_name]["build"](program,
                                                branch_predictor=branch_predictor,
                                                cycle_costs=cycle_costs)
        else:
            kwargs = {}
            if branch_predictor is not None:
                kwargs["branch_predictor"] = branch_predictor
            cpu = PRESETS[preset_name]["build"](program, **kwargs)
        if run_to_completion:
            states = run_simulation(cpu, num_cycles=MAX_AUTO_CYCLES,
                                    include_reset=True, until_stable=True)
        else:
            states = run_simulation(cpu, num_cycles=cycles, include_reset=True)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    resp = {
        "preset": preset_name,
        "isa": isa_name,
        "model": model,
        "reg_names": isa_cfg.register_names(),
        "program_format": isa_cfg.program_format,
        "cycles": states,
    }
    if run_to_completion:
        # Stopped early == the architectural state settled within the cap.
        # (+1 accounts for the reset cycle prepended by include_reset.)
        resp["run_to_completion"] = True
        resp["completed"] = len(states) < MAX_AUTO_CYCLES + 1
    if model == "configurable":
        # Time model: clock period (work units/cycle) is set by the busiest
        # class; total time = cycles x period. "cycles" is the TRUE completion
        # (last cycle the architectural state changes, +1) so the trailing
        # settle window doesn't inflate it — the UI shows that fewer
        # cycles/instr costs a longer clock.
        final_sig = _arch_signature(states[-1]) if states else None
        settle = 0
        for i, s in enumerate(states):
            if _arch_signature(s) != final_sig:
                settle = i
        settle_cycle = (settle + 1) if states else 0
        period = _clock_period(cycle_costs)
        resp["time_model"] = {
            "costs": cycle_costs,
            "clock_period": period,
            "work": _CYCLE_WORK,
            "cycles": settle_cycle,
            "total_time": settle_cycle * period,
        }
    return jsonify(resp)


@app.route("/compare", methods=["POST"])
def compare():
    """Cycles-to-completion comparison across ISAs x execution models.

    Body: {"source": <Core-C>} for a cross-ISA comparison, or
          {"asm_text": ..., "isa": ...} for a single-ISA (cross-model) one.
    Optional: "models" (default: all five), "num_lanes".

    Each target runs with settle detection (like run_to_completion) but only
    the CYCLE COUNT is returned — no per-cycle states — so a full 3x5 grid
    stays cheap. 'cycles' is the settle point (the cycle the architectural
    state last changed), 'completed' False means the cap was hit. Targets
    that cannot compile/assemble return an 'error' cell instead of failing
    the whole request — the grid itself documents which programs are
    portable to which backends.
    """
    from sim.runner_v2 import STABLE_WINDOW

    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "JSON body must be an object"}), 400

    source = body.get("source", "")
    asm_text = body.get("asm_text", "")
    if not isinstance(source, str) or not isinstance(asm_text, str):
        return jsonify({"error": "'source'/'asm_text' must be strings"}), 400
    if bool(source.strip()) == bool(asm_text.strip()):
        return jsonify({"error": "Provide exactly one of 'source' (Core-C) "
                                 "or 'asm_text' (assembly)"}), 400

    all_models = sorted({p["model"] for p in PRESETS.values()})
    models = body.get("models", all_models)
    if not isinstance(models, list) or not set(models) <= set(all_models):
        return jsonify({"error": f"'models' must be a subset of {all_models}"}), 400

    if source.strip():
        isas = sorted(ISA_CONFIGS)          # Core-C: compare across all ISAs
    else:
        isa_name = body.get("isa", "riscv")
        if isa_name not in ISA_CONFIGS:
            return jsonify({"error": f"Unknown ISA '{isa_name}'"}), 400
        isas = [isa_name]                   # asm is inherently single-ISA

    num_lanes = _coerce_int(body.get("num_lanes", 2), 2)
    if num_lanes is None:
        return jsonify({"error": "'num_lanes' must be an integer"}), 400
    num_lanes = max(1, min(num_lanes, MAX_LANES))

    # Per-instruction-class cycle budgets for the "configurable" model. The
    # grid's editable "Custom" column runs configurable with these costs; every
    # other model ignores them. Absent knobs default to DEFAULT_COSTS (all 1 ==
    # single-cycle). Validated/clamped exactly like /simulate.
    raw_costs = body.get("cycle_costs") or {}
    if not isinstance(raw_costs, dict):
        return jsonify({"error": "'cycle_costs' must be an object"}), 400
    cycle_costs = {}
    for k in _CYCLE_CLASSES:
        v = _coerce_int(raw_costs.get(k, _DEFAULT_COSTS[k]), _DEFAULT_COSTS[k])
        if v is None:
            return jsonify({"error": f"cycle_costs['{k}'] must be an integer"}), 400
        cycle_costs[k] = max(1, min(v, 64))   # clamp to 1..64 cycles

    def _final_arch(states):
        """(registers, nonzero-dmem) of the final cycle, for parity checks."""
        last = states[-1]
        regs, mem = None, None
        for name, comp in last.items():
            if not isinstance(comp, dict):
                continue
            if "registers" in comp:
                regs = tuple(comp["registers"])
            if "memory" in comp and "imem" not in name.lower():
                # Full non-zero memory = dense window + sparse high map (the
                # compiled software stack lives high, in memory_hi).
                dense = [(i, v) for i, v in enumerate(comp["memory"]) if v]
                hi = [(int(k), v) for k, v in (comp.get("memory_hi") or {}).items() if v]
                mem = tuple(sorted(dense + hi))
        return regs, mem

    def _run_target(preset_name, program):
        model = PRESETS[preset_name]["model"]
        if model == "superscalar":
            cpu = PRESETS[preset_name]["build"](program, num_lanes=num_lanes)
        elif model == "configurable":
            cpu = PRESETS[preset_name]["build"](program, cycle_costs=cycle_costs)
        else:
            cpu = PRESETS[preset_name]["build"](program)
        return run_simulation(cpu, num_cycles=MAX_AUTO_CYCLES,
                              include_reset=True, until_stable=True)

    results = []
    for isa in isas:
        # One compile/assemble per ISA, shared by its model rows.
        program, front_err = None, None
        try:
            if source.strip():
                program = assemble(isa, compile_c(source, isa).asm)
            else:
                program = assemble(isa, asm_text)
        except Exception as exc:
            front_err = str(exc)

        # Reference run: cycle counts are only comparable between runs that
        # compute the SAME final state, so every model is parity-checked
        # against this ISA's single_cycle result (the trusted oracle).
        reference = None
        if front_err is None:
            try:
                ref_states = run_simulation(
                    PRESETS[f"{isa}/single_cycle"]["build"](program),
                    num_cycles=MAX_AUTO_CYCLES, include_reset=True,
                    until_stable=True)
                if len(ref_states) < MAX_AUTO_CYCLES + 1:
                    reference = _final_arch(ref_states)
            except Exception:
                reference = None

        for model in models:
            preset_name = f"{isa}/{model}"
            entry = {"isa": isa, "model": model, "preset": preset_name}
            if preset_name not in PRESETS:
                entry["error"] = "preset not available"
                results.append(entry)
                continue
            if front_err is not None:
                entry["error"] = front_err
                results.append(entry)
                continue
            if preset_name == "x86/superscalar":
                entry["error"] = ("illustrative-only preset (reuses the "
                                  "RISC-V decoder) — excluded from comparisons")
                results.append(entry)
                continue
            try:
                states = _run_target(preset_name, program)
            except Exception as exc:
                entry["error"] = str(exc)
                results.append(entry)
                continue
            completed = len(states) < MAX_AUTO_CYCLES + 1
            if (completed and reference is not None
                    and _final_arch(states) != reference):
                entry["error"] = ("result diverges from single_cycle — "
                                  "outside this model's verified scope; "
                                  "cycle count would be meaningless")
                results.append(entry)
                continue
            entry["completed"] = completed
            # Settle point = total run minus the quiet detection window.
            entry["cycles"] = (max(0, len(states) - 1 - STABLE_WINDOW)
                               if completed else MAX_AUTO_CYCLES)
            entry["program_len"] = len(program)
            if model == "configurable" and completed:
                # cycles != time: the busiest class sets the clock period, so
                # a config with fewer cycles can still cost more total time.
                period = _clock_period(cycle_costs)
                entry["clock_period"] = period
                entry["total_time"] = entry["cycles"] * period
            results.append(entry)

    return jsonify({"results": results, "models": models, "isas": isas,
                    "cap": MAX_AUTO_CYCLES, "cycle_costs": cycle_costs,
                    "cost_classes": list(_CYCLE_CLASSES)})


@app.route("/assemble", methods=["POST"])
def assemble_endpoint():
    """Assemble text to hex program."""
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "JSON body must be an object"}), 400
    isa_name = body.get("isa", "riscv")
    text = body.get("text", "")

    if not isinstance(text, str):
        return jsonify({"error": "'text' must be a string"}), 400
    if not text.strip():
        return jsonify({"error": "Empty assembly text"}), 400

    try:
        program = assemble(isa_name, text)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "isa": isa_name,
        "program": program,
    })


@app.route("/compile", methods=["POST"])
def compile_endpoint():
    """Compile Core-C source to the selected ISA's assembly (+ pipeline stages).

    Client source is untrusted, so — like /assemble — any compile/assembly
    failure is a 400 with {error}, never a raw 500.
    """
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "JSON body must be an object"}), 400

    source = body.get("source", "")
    isa_name = body.get("isa", "riscv")

    if not isinstance(source, str):
        return jsonify({"error": "'source' must be a string"}), 400
    if not source.strip():
        return jsonify({"error": "Empty source"}), 400
    if isa_name not in ISA_CONFIGS:
        return jsonify({"error": f"Unknown ISA '{isa_name}'"}), 400

    try:
        result = compile_c(source, isa_name)
    except CompilerError as exc:
        return jsonify({"error": f"Compile error: {exc}"}), 400
    except Exception as exc:  # defensive: untrusted source must never raw-500
        return jsonify({"error": f"Compile error: {exc}"}), 400

    # Assemble the generated asm too, so the UI can hand the program straight to
    # /simulate and so bad codegen surfaces as a 400 rather than downstream.
    try:
        program = assemble(isa_name, result.asm)
    except Exception as exc:
        return jsonify({"error": f"Assembly error: {exc}"}), 400

    return jsonify({
        "isa": isa_name,
        "backend": result.backend,
        "asm": result.asm,
        "stages": {
            "source": source,
            "tokens": result.tokens,
            "ast": result.ast,
            "asm": result.asm,
        },
        "source_map": result.source_map,
        "symbols": result.symbols,
        "program": program,
    })


# ── Core-C example programs (programs/c/*.c) ─────────────────────
C_EXAMPLES_DIR = os.path.join(PROGRAMS_DIR, "c")
_C_NAME_RE = re.compile(r"^[a-z0-9_]+$")


def _c_example_meta(fpath):
    """Parse the header convention of a Core-C sample:
    line 1: '// <name>: <description>'; later: '// Targets: isa, isa (...)'."""
    description, targets = "", []
    try:
        with open(fpath) as f:
            for line in f:
                line = line.strip()
                if not line.startswith("//"):
                    break
                text = line[2:].strip()
                m = re.match(r"^Targets:\s*([^(]+)", text, re.IGNORECASE)
                if m:
                    targets = [t.strip() for t in m.group(1).split(",") if t.strip()]
                    continue
                m = re.match(r"^[\w.]+:\s*(.+)$", text)
                if m and not description:
                    description = m.group(1)
    except OSError:
        pass
    return description, targets


@app.route("/compiler/examples")
def list_c_examples():
    """Catalog of Core-C sample programs for the compiler tab."""
    items = []
    if os.path.isdir(C_EXAMPLES_DIR):
        for fname in sorted(os.listdir(C_EXAMPLES_DIR)):
            if not fname.endswith(".c"):
                continue
            name = os.path.splitext(fname)[0]
            description, targets = _c_example_meta(
                os.path.join(C_EXAMPLES_DIR, fname))
            items.append({
                "name": name,
                "label": name.replace("_", " ").title(),
                "file": fname,
                "description": description,
                "targets": targets,
            })
    return jsonify({"items": items})


@app.route("/compiler/examples/<name>")
def get_c_example(name):
    """Content of a single Core-C sample (name without the .c extension)."""
    if not _C_NAME_RE.match(name):
        return jsonify({"error": "Invalid example name"}), 400
    fpath = os.path.join(C_EXAMPLES_DIR, name + ".c")
    real = os.path.realpath(fpath)
    if not real.startswith(os.path.realpath(C_EXAMPLES_DIR) + os.sep):
        return jsonify({"error": "Invalid example name"}), 400
    if not os.path.isfile(real):
        return jsonify({"error": "Example not found"}), 404
    with open(real) as f:
        return jsonify({"name": name, "content": f.read()})


@app.route("/cheatsheet/<isa_name>")
def cheatsheet(isa_name: str):
    """Return instruction cheatsheet for the given ISA."""
    try:
        data = get_cheatsheet(isa_name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404

    return jsonify({
        "isa": isa_name,
        "instructions": data,
    })


# ── Example programs ─────────────────────────────────────────────
_VALID_ISAS = {"riscv", "arm", "x86"}
_CATEGORY_LABELS = {
    "instructions": "Instructions",
    "hazards": "Pipeline Hazards",
    "branch_prediction": "Branch Prediction",
    "cycle_efficiency": "Cycle Efficiency (compare models)",
    "algorithms": "Algorithms",
}
_CATEGORY_ORDER = ["instructions", "hazards", "branch_prediction", "cycle_efficiency", "algorithms"]


def _extract_title(filepath):
    """Extract title from first comment line: '; === Title ===' -> 'Title'."""
    try:
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith(";"):
                    m = re.match(r";\s*===\s*(.+?)\s*===", line)
                    if m:
                        return m.group(1)
    except OSError:
        pass
    # Fallback: derive from filename
    name = os.path.splitext(os.path.basename(filepath))[0]
    return name.replace("_", " ").title()


@app.route("/examples")
def list_examples():
    """Return catalog of example programs grouped by ISA and category."""
    catalog = {}
    if not os.path.isdir(PROGRAMS_DIR):
        return jsonify(catalog)

    for isa in sorted(os.listdir(PROGRAMS_DIR)):
        isa_dir = os.path.join(PROGRAMS_DIR, isa)
        if isa not in _VALID_ISAS or not os.path.isdir(isa_dir):
            continue
        isa_cat = {}
        for cat in _CATEGORY_ORDER:
            cat_dir = os.path.join(isa_dir, cat)
            if not os.path.isdir(cat_dir):
                continue
            items = []
            for fname in sorted(os.listdir(cat_dir)):
                if not fname.endswith(".asm"):
                    continue
                fpath = os.path.join(cat_dir, fname)
                name = os.path.splitext(fname)[0]
                label = _extract_title(fpath)
                items.append({
                    "name": name,
                    "label": label,
                    "file": f"{isa}/{cat}/{fname}",
                })
            if items:
                isa_cat[cat] = {
                    "label": _CATEGORY_LABELS.get(cat, cat),
                    "items": items,
                }
        if isa_cat:
            catalog[isa] = isa_cat
    return jsonify(catalog)


@app.route("/examples/<path:filepath>")
def get_example(filepath):
    """Return the content of a single example program file."""
    parts = filepath.split("/")
    if len(parts) != 3:
        return jsonify({"error": "Invalid path"}), 400
    isa, category, filename = parts

    # Validate components
    if isa not in _VALID_ISAS:
        return jsonify({"error": f"Unknown ISA '{isa}'"}), 400
    if ".." in filepath or filename != os.path.basename(filename):
        return jsonify({"error": "Invalid path"}), 400
    if not filename.endswith(".asm"):
        return jsonify({"error": "Invalid file type"}), 400

    fpath = os.path.join(PROGRAMS_DIR, isa, category, filename)

    # Containment guard: resolve symlinks / "." segments and confirm the
    # real path stays inside PROGRAMS_DIR before opening.
    real = os.path.realpath(fpath)
    if not real.startswith(os.path.realpath(PROGRAMS_DIR) + os.sep):
        return jsonify({"error": "Invalid path"}), 400
    if not os.path.isfile(real):
        return jsonify({"error": "File not found"}), 404

    with open(real, "r") as f:
        content = f.read()

    return jsonify({"file": filepath, "content": content})


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    app.run(debug=debug, port=5051)
