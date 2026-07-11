"""
Simulation runner for the component-based CPU.

Drives a CPU object for N clock cycles and returns a list of
per-cycle state snapshots as plain Python dicts, ready for JSON.

``until_stable=True`` turns ``num_cycles`` into a CAP and stops early once the
program has run to completion: the architectural state (register files + data
memories) has been unchanged for ``stable_window`` consecutive cycles. The
window must exceed the longest architecturally-quiet stretch a *live* program
can produce, and the slow case is the multicycle model (~3-5 cycles/instruction)
running a software multiply/divide: the quiet gap between two result updates is
one loop-body iteration (measured max 39 cycles across the sample programs — and
bounded by the loop-body length, NOT the operand magnitude, since every
iteration updates the accumulator), so 64 gives a comfortable margin. A window
that was too short (the old 32) FALSELY settled mid-multiply and returned a
wrong "completed" result; 64 fixes that. PC is deliberately NOT part of the
signature: a finished program may sit in a state-preserving loop (compiled code
returns into an idle spin) or run off into forward NOPs — both freeze committed
state, which is exactly what this detects.
"""
from __future__ import annotations
from sim.component.wire import CPU

# Consecutive architecturally-quiet cycles => the program has completed. Sized
# to exceed the longest quiet stretch a live multicycle software-multiply loop
# can produce (max observed 39; see module docstring).
STABLE_WINDOW = 64


def _arch_signature(state: dict) -> tuple:
    """Hashable snapshot of architectural state: every component's register
    file plus every data memory (instruction memories excluded)."""
    sig = []
    for name in sorted(state):
        comp = state[name]
        if not isinstance(comp, dict):
            continue
        if "registers" in comp:
            sig.append((name, "r", tuple(comp["registers"])))
        if "memory" in comp and "imem" not in name.lower():
            # Full memory = dense low window + sparse high map (the software
            # stack lives high, so hashing only the window would miss stack
            # churn and settle prematurely).
            words = list(enumerate(comp["memory"]))
            hi = comp.get("memory_hi") or {}
            words.extend(sorted((int(k), v) for k, v in hi.items()))
            sig.append((name, "m", tuple(words)))
    return tuple(sig)


def run_simulation(cpu: CPU, num_cycles: int = 50, include_reset: bool = False,
                   until_stable: bool = False,
                   stable_window: int = STABLE_WINDOW) -> list[dict]:
    states = []
    if include_reset:
        # Cycle 0: initial reset state before any tick (empty pipeline)
        state = cpu.get_cycle_state()
        state["_cycle"] = 0
        states.append(state)

    prev_sig = None
    streak = 0
    for cycle in range(num_cycles):
        cpu.tick()
        state = cpu.get_cycle_state()
        state["_cycle"] = len(states)
        states.append(state)
        if until_stable:
            sig = _arch_signature(state)
            streak = streak + 1 if sig == prev_sig else 0
            prev_sig = sig
            if streak >= stable_window:
                break
    return states
