"""Configurable per-instruction cycle-budget controller.

The single-cycle datapath is fully combinational: given a stable PC it produces
an instruction's entire result every cycle. This controller turns that into a
*configurable* multi-cycle machine by holding each instruction in flight for a
per-class number of cycles and committing exactly once, on its final cycle:

  * ``stall``  = 1 while the instruction is still "in flight" (holds the PC, so
    the datapath keeps recomputing the same stable values).
  * ``commit`` = 1 only on the LAST cycle of the instruction's budget; it gates
    the register write, the memory write, and the PC redirect.

Because the committed effect is exactly what the single-cycle datapath produces,
the architectural result is identical to single-cycle — only the CYCLE COUNT
changes. That keeps this model in agreement with the single-cycle oracle while
letting a user dial "how many cycles does each instruction take".

Per-class budgets (each clamped >= 1): ``alu``, ``load``, ``store``, ``branch``.
All-1s reproduces single-cycle exactly; a {alu:3, load:4, store:4, branch:3}
profile reproduces the classic Fetch-Decode-Execute (multicycle) behaviour.
"""
from sim.component.base import ComponentBase, Port

DEFAULT_COSTS = {"alu": 1, "load": 1, "store": 1, "branch": 1}
# The classic Fetch-Decode-Execute profile (matches the multicycle FSM).
FETDECEXE_COSTS = {"alu": 3, "load": 4, "store": 4, "branch": 3}
CLASSES = ("alu", "load", "store", "branch")

# ── Time model (cycles != time) ─────────────────────────────────────────────
# Abstract "work units" each instruction class must do (= the datapath stages it
# traverses: fetch, decode, reg-read, ALU, memory, writeback). A cycle's minimum
# length is the most work packed into it, so if a class does WORK units in K
# cycles, each cycle carries WORK/K units. The clock period is set by the busiest
# class, and total time = total_cycles x clock_period. This is why single-cycle
# (K=1) has the fewest cycles but the LONGEST clock — and often the most time.
WORK = {"alu": 5, "load": 6, "store": 5, "branch": 4}


def clock_period(costs) -> float:
    """Minimum clock period (work units/cycle) for a per-class cost config.

    = max over classes of WORK[c] / cycles[c]. A real clock is set by the
    worst-case cycle regardless of the program, so this depends only on the
    knob settings, not the instruction mix."""
    return max(WORK[c] / max(1, int((costs or {}).get(c, 1))) for c in CLASSES)


def estimate_time(total_cycles: int, costs) -> float:
    """Total execution time (work units) = total_cycles x clock_period."""
    return total_cycles * clock_period(costs)


class CycleBudgetController(ComponentBase):
    name = "cycle_budget_controller"
    ui_label = "Cycle Budget"
    ui_category = "control"
    ports_spec = {
        "mem_read":  Port(1, "in", "Decoder: is a load"),
        "mem_write": Port(1, "in", "Decoder: is a store"),
        "branch":    Port(1, "in", "Decoder: conditional branch"),
        "jal":       Port(1, "in", "Decoder: JAL / unconditional jump"),
        "jalr":      Port(1, "in", "Decoder: JALR / indirect jump"),
        "commit":    Port(1, "out", "1 on the instruction's final cycle (gate writes + PC)"),
        "stall":     Port(1, "out", "1 while the instruction is still in flight (hold PC)"),
    }

    def __init__(self, costs=None, **kw):
        super().__init__(**kw)
        merged = dict(DEFAULT_COSTS)
        if costs:
            merged.update({k: costs[k] for k in CLASSES if k in costs})
        # clamp to >= 1 (an instruction always takes at least one cycle)
        self._costs = {k: max(1, int(merged[k])) for k in CLASSES}
        self._elapsed = 0

    def _class(self) -> str:
        if self["mem_read"]:
            return "load"
        if self["mem_write"]:
            return "store"
        if self["branch"] or self["jal"] or self["jalr"]:
            return "branch"
        return "alu"

    def _cost(self) -> int:
        return self._costs[self._class()]

    def evaluate(self):
        last = (self._elapsed + 1 >= self._cost())
        self["commit"] = 1 if last else 0
        self["stall"] = 0 if last else 1

    def rising_edge(self):
        # PC is held while stalled, so the decoder (and thus _cost) is stable
        # across the whole instruction — advance to the next instruction only
        # after its full budget has elapsed.
        if self._elapsed + 1 >= self._cost():
            self._elapsed = 0
        else:
            self._elapsed += 1

    def get_state(self):
        n = self._cost()
        return {
            "class": self._class(),
            "cycle": self._elapsed + 1,
            "budget": n,
            "commit": self["commit"],
            "costs": dict(self._costs),
        }
