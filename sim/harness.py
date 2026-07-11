"""
Standalone backend simulator harness — no Flask, no UI.

This is the canonical programmatic entry point into the simulator. Give it a
program (assembly text, hex words, or x86 bytes) plus parameters (ISA, model,
branch predictor, prediction stage, superscalar lanes) and it builds the CPU,
runs it, and hands back a SimResult you can inspect: final registers, data
memory, the fetched-instruction stream, and the full per-cycle state.

The Flask API (api/app.py) is a thin layer over this module, and the test
suite drives the simulator through it, so "does the backend compute the right
answer" is verifiable without touching the web layer.

Usage (library):
    from sim.harness import simulate
    r = simulate("riscv", "pipeline", asm="ADDI x1,x0,5\\nADDI x2,x1,3", cycles=40)
    r.reg("x2")        # -> 8
    r.mem_at(0x40)     # data-memory word at byte address 0x40

Usage (CLI):
    python3 -m sim.harness --isa riscv --model pipeline --cycles 40 \\
        --asm-text "ADDI x1,x0,5" --json
    python3 -m sim.harness --preset riscv/ooo --asm prog.s --predictor gshare
"""
from __future__ import annotations

import importlib
import os
import pkgutil
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sim.runner_v2 import run_simulation
from sim.assembler import assemble as _assemble
from sim.isa.riscv.config import RISCV
from sim.isa.arm.config import ARM
from sim.isa.x86.config import X86
import sim.components.branch.predictors as _pred_pkg
from sim.components.branch.predictors.base import BranchPredictorBase

# ── ISA configs ──────────────────────────────────────────────────────────
ISA_CONFIGS = {"riscv": RISCV(), "arm": ARM(), "x86": X86()}
ISAS = tuple(ISA_CONFIGS)

# ── Model labels (kept in sync with the UI dropdown) ──────────────────────
_ISA_DISPLAY = {"riscv": "RISC-V", "arm": "ARM", "x86": "x86"}
_MODEL_LABEL = {
    "single_cycle": "Single Cycle",
    "multicycle":   "FetDecExe",
    "configurable": "Configurable",
    "pipeline":     "Pipeline",
    "ooo":          "Out-of-Order",
    "superscalar":  "Superscalar",
}
MODELS = tuple(_MODEL_LABEL)


# ── Branch-predictor discovery ────────────────────────────────────────────
def _discover_predictors() -> dict:
    """Scan the predictors package -> {name: class}."""
    registry = {}
    for info in pkgutil.iter_modules(_pred_pkg.__path__):
        if info.name in ("base", "__init__"):
            continue
        mod = importlib.import_module(f"sim.components.branch.predictors.{info.name}")
        for attr in dir(mod):
            cls = getattr(mod, attr)
            if (isinstance(cls, type) and issubclass(cls, BranchPredictorBase)
                    and cls is not BranchPredictorBase and hasattr(cls, "name")):
                registry[cls.name] = cls
    return registry


PREDICTOR_CLASSES = _discover_predictors()
PREDICTORS = tuple(sorted(PREDICTOR_CLASSES))


# ── Preset registry ───────────────────────────────────────────────────────
def _build_presets() -> dict:
    """Import every available (isa, model) preset and register its build fn.

    ``single_cycle`` and ``pipeline`` exist for all ISAs; the advanced models
    are imported defensively so a missing/broken one drops out rather than
    taking the whole registry down.
    """
    presets = {}
    for isa in ISAS:
        for model in MODELS:
            try:
                mod = importlib.import_module(f"sim.isa.{isa}.presets.{model}")
            except ImportError:
                continue
            build = getattr(mod, "build", None)
            if build is None:
                continue
            presets[f"{isa}/{model}"] = {
                "label": f"{_ISA_DISPLAY[isa]} {_MODEL_LABEL[model]}",
                "build": build,
                "isa": isa,
                "model": model,
            }
    return presets


PRESETS = _build_presets()


# ── Errors ─────────────────────────────────────────────────────────────────
class HarnessError(ValueError):
    """Raised for bad harness inputs (unknown preset/ISA, malformed program)."""


# ── Program parsing ─────────────────────────────────────────────────────────
def assemble(isa: str, text: str) -> list[int]:
    """Assemble ``text`` for ``isa`` into a machine-code list (words or bytes)."""
    if isa not in ISA_CONFIGS:
        raise HarnessError(f"Unknown ISA '{isa}' (expected one of {list(ISA_CONFIGS)})")
    return _assemble(isa, text)


def parse_program(program) -> list[int]:
    """Coerce a program of ints / hex-strings into a list[int]."""
    if not isinstance(program, (list, tuple)):
        raise HarnessError("program must be a list of ints or hex strings")
    try:
        return [int(p, 0) if isinstance(p, str) else int(p) for p in program]
    except (TypeError, ValueError) as exc:
        raise HarnessError(f"invalid program entry: {exc}") from exc


# ── CPU construction ─────────────────────────────────────────────────────────
def resolve_preset(isa: Optional[str] = None, model: Optional[str] = None,
                   preset: Optional[str] = None) -> str:
    """Return a valid 'isa/model' preset key or raise HarnessError."""
    key = preset or (f"{isa}/{model}" if isa and model else None)
    if not key:
        raise HarnessError("specify either preset='isa/model' or isa=.. and model=..")
    if key not in PRESETS:
        raise HarnessError(f"Unknown preset '{key}' (available: {sorted(PRESETS)})")
    return key


def build_cpu(preset_key: str, program: list[int], *, branch_predictor=None,
              prediction_stage: str = "id", num_lanes: int = 2, cycle_costs=None):
    """Build (but do not run) the CPU for ``preset_key``.

    ``branch_predictor`` may be a predictor name (str), a ready instance, or
    None. Only the superscalar build takes ``num_lanes``; the ``configurable``
    build takes ``cycle_costs`` (per-class cycle budgets); predictors are passed
    to any model that accepts one.
    """
    p = PRESETS[preset_key]
    bp = None
    if isinstance(branch_predictor, str) and branch_predictor:
        cls = PREDICTOR_CLASSES.get(branch_predictor)
        if cls is None:
            raise HarnessError(f"Unknown branch predictor '{branch_predictor}'")
        bp = cls(prediction_stage=prediction_stage)
    elif branch_predictor is not None:
        bp = branch_predictor  # already an instance

    if p["model"] == "superscalar":
        return p["build"](program, num_lanes=num_lanes, branch_predictor=bp)
    kwargs = {}
    if bp is not None:
        kwargs["branch_predictor"] = bp
    if p["model"] == "configurable" and cycle_costs is not None:
        kwargs["cycle_costs"] = cycle_costs
    return p["build"](program, **kwargs)


# ── Result container ──────────────────────────────────────────────────────────
@dataclass
class SimResult:
    """The outcome of a run, with convenient accessors for verification."""
    preset: str
    isa: str
    model: str
    program: list = field(repr=False)
    program_format: str = "words"
    reg_names: list = field(default_factory=list, repr=False)
    cycles: list = field(default_factory=list, repr=False)
    cpu: object = field(default=None, repr=False)

    # -- registers -----------------------------------------------------------
    @property
    def registers(self) -> list:
        """Final architectural register file (list of ints)."""
        for s in reversed(self.cycles):
            rf = s.get("regfile")
            if rf and "registers" in rf:
                return list(rf["registers"])
        return []

    def reg(self, which):
        """Final value of a register by index (int), ABI name ('sp', 'EAX'),
        or numbered alias ('x2', 'r5')."""
        regs = self.registers
        if isinstance(which, int):
            return regs[which]
        w = which.strip()
        if w in self.reg_names:
            return regs[self.reg_names.index(w)]
        m = re.fullmatch(r"[xXrReE]?(\d+)", w)
        if m and int(m.group(1)) < len(regs):
            return regs[int(m.group(1))]
        raise HarnessError(f"unknown register '{which}' (names: {self.reg_names})")

    # -- data memory ---------------------------------------------------------
    @property
    def memory(self) -> list:
        """Final data-memory contents (word-indexed list of ints)."""
        dmem = self.cpu.components.get("dmem") if self.cpu else None
        return list(dmem._mem) if dmem is not None else []

    def mem_word(self, word_index: int) -> int:
        return self.memory[word_index]

    def mem_at(self, byte_addr: int) -> int:
        """Data-memory value at a byte address (word-aligned)."""
        return self.memory[(byte_addr >> 2) % max(1, len(self.memory))]

    def nonzero_memory(self) -> dict:
        """{byte_addr: value} for every non-zero data-memory word."""
        return {i * 4: v for i, v in enumerate(self.memory) if v}

    # -- instruction / PC stream --------------------------------------------
    @property
    def pc_stream(self) -> list:
        """Fetched PC each cycle (hex strings as the components report them)."""
        return [s["fetch"]["pc"] for s in self.cycles if "fetch" in s and "pc" in s["fetch"]]

    # -- summary -------------------------------------------------------------
    def summary(self) -> dict:
        regs = self.registers
        named = {self.reg_names[i]: regs[i]
                 for i in range(min(len(regs), len(self.reg_names))) if regs[i]}
        return {
            "preset": self.preset,
            "isa": self.isa,
            "model": self.model,
            "cycles": len(self.cycles),
            "program_words": len(self.program),
            "nonzero_registers": named,
            "nonzero_memory": self.nonzero_memory(),
        }


# ── Top-level entry point ────────────────────────────────────────────────────
def simulate(isa: Optional[str] = None, model: Optional[str] = None, *,
             preset: Optional[str] = None, program=None, asm: Optional[str] = None,
             cycles: int = 20, branch_predictor=None, prediction_stage: str = "id",
             num_lanes: int = 2, include_reset: bool = True, cycle_costs=None) -> SimResult:
    """Build + run a simulation and return a SimResult.

    Program source (pick one; defaults to the ISA demo program):
      * ``asm``     — assembly text, assembled for the ISA
      * ``program`` — list of ints / hex strings (words for riscv/arm, bytes x86)
      * neither     — the ISA's built-in demo program
    """
    key = resolve_preset(isa, model, preset)
    isa = PRESETS[key]["isa"]
    model = PRESETS[key]["model"]
    cfg = ISA_CONFIGS[isa]

    if asm is not None:
        prog = assemble(isa, asm)
    elif program is not None:
        prog = parse_program(program)
    else:
        prog = list(cfg.demo_program())

    cpu = build_cpu(key, prog, branch_predictor=branch_predictor,
                    prediction_stage=prediction_stage, num_lanes=num_lanes,
                    cycle_costs=cycle_costs)
    states = run_simulation(cpu, num_cycles=cycles, include_reset=include_reset)
    return SimResult(preset=key, isa=isa, model=model, program=prog,
                     program_format=cfg.program_format, reg_names=cfg.register_names(),
                     cycles=states, cpu=cpu)


def compile_and_simulate(isa: str, model: str, source: str, *, cycles: int = 200,
                         **kwargs) -> SimResult:
    """Compile Core-C ``source`` for ``isa`` and simulate it on ``model``.

    Thin convenience wrapper: it runs the Core-C compiler
    (``sim.compiler.compile_c``) to obtain the project's own assembly text, then
    reuses :func:`simulate` with ``preset=f"{isa}/{model}"`` and ``asm=`` so the
    compiled program flows through the exact same assemble -> build -> run path
    as hand-written assembly.

    Args:
        isa: "riscv" | "arm" | "x86".
        model: an execution model, e.g. "single_cycle" | "multicycle" | "pipeline".
        source: Core-C source text.
        cycles: number of cycles to run (compiled code is verbose, so loop-heavy
            programs may need a few thousand cycles).
        **kwargs: forwarded to :func:`simulate` (branch_predictor,
            prediction_stage, num_lanes, include_reset).

    Returns:
        SimResult for the compiled program.

    Raises:
        CompilerError: on any Core-C lex/parse/codegen failure or unknown ISA.
        HarnessError: on an unknown preset.
    """
    from sim.compiler import compile_c  # local import: keeps core harness dep-free
    result = compile_c(source, isa)
    return simulate(preset=f"{isa}/{model}", asm=result.asm, cycles=cycles, **kwargs)


# ── CLI ───────────────────────────────────────────────────────────────────────
def _read_program_arg(args):
    """Resolve the program source from CLI args -> (kwarg_name, value)."""
    if args.asm:
        with open(args.asm) as f:
            return "asm", f.read()
    if args.asm_text:
        return "asm", args.asm_text.replace("\\n", "\n")
    if args.hex:
        with open(args.hex) as f:
            toks = f.read().split()
        return "program", toks
    if args.hex_words:
        return "program", args.hex_words.split(",")
    return None, None


def main(argv=None) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(
        prog="sim.harness",
        description="Standalone RTL CPU simulator (no UI). Run a program on a "
                    "given ISA/model and inspect registers + memory.")
    ap.add_argument("--preset", help="preset key 'isa/model' (overrides --isa/--model)")
    ap.add_argument("--isa", choices=ISAS)
    ap.add_argument("--model", choices=MODELS)
    ap.add_argument("--cycles", type=int, default=40)
    ap.add_argument("--predictor", choices=PREDICTORS, default=None)
    ap.add_argument("--stage", choices=["id", "if"], default="id")
    ap.add_argument("--lanes", type=int, default=2)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--asm", metavar="FILE", help="assembly source file")
    src.add_argument("--asm-text", metavar="TEXT", help="inline assembly (use \\n for newlines)")
    src.add_argument("--hex", metavar="FILE", help="file of whitespace-separated hex words/bytes")
    src.add_argument("--hex-words", metavar="CSV", help="comma-separated hex/int program")
    src.add_argument("--demo", action="store_true", help="use the ISA demo program (default)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a text report")
    ap.add_argument("--list-presets", action="store_true", help="list presets and exit")
    args = ap.parse_args(argv)

    if args.list_presets:
        for k in sorted(PRESETS):
            print(f"{k:22s} {PRESETS[k]['label']}")
        print(f"\npredictors: {', '.join(PREDICTORS)}")
        return 0

    try:
        key = resolve_preset(args.isa, args.model, args.preset)
        src_kw, src_val = _read_program_arg(args)
        kwargs = {src_kw: src_val} if src_kw else {}
        res = simulate(preset=key, cycles=args.cycles, branch_predictor=args.predictor,
                       prediction_stage=args.stage, num_lanes=args.lanes, **kwargs)
    except (HarnessError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # surface simulator failures with context
        print(f"simulation failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(res.summary(), indent=2))
        return 0

    s = res.summary()
    print(f"preset : {s['preset']}  ({res.program_format} program, {s['program_words']} entries)")
    print(f"cycles : {s['cycles']}")
    print("registers (non-zero):")
    if s["nonzero_registers"]:
        for name, val in s["nonzero_registers"].items():
            print(f"  {name:5s} = {val}  (0x{val & 0xFFFFFFFF:08x})")
    else:
        print("  (all zero)")
    print("data memory (non-zero words):")
    if s["nonzero_memory"]:
        for addr, val in s["nonzero_memory"].items():
            print(f"  [0x{addr:04x}] = {val}  (0x{val & 0xFFFFFFFF:08x})")
    else:
        print("  (all zero)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
