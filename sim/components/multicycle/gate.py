from sim.component.base import ComponentBase, Port


class GatedSignal(ComponentBase):
    """
    Simple AND gate: out = a AND b.

    Used to gate write-enables by the multi-cycle controller phase.
    Pure combinational -- no rising_edge().
    """
    name = "gated_signal"
    ui_label = "Gate"
    ui_category = "control"
    ports_spec = {
        "a":   Port(1, "in", "Input A"),
        "b":   Port(1, "in", "Input B"),
        "out": Port(1, "out", "Gated output (A AND B)"),
    }

    def evaluate(self):
        self["out"] = 1 if (self["a"] and self["b"]) else 0


class OrSignal(ComponentBase):
    """
    Simple OR gate: out = a OR b.

    Used to combine two control signals into one enable (e.g. an OoO
    dispatch enable that fires for register-writing OR memory-writing
    instructions). Pure combinational -- no rising_edge().
    """
    name = "or_signal"
    ui_label = "OR Gate"
    ui_category = "control"
    ports_spec = {
        "a":   Port(1, "in", "Input A"),
        "b":   Port(1, "in", "Input B"),
        "out": Port(1, "out", "Gated output (A OR B)"),
    }

    def evaluate(self):
        self["out"] = 1 if (self["a"] or self["b"]) else 0


class AndNotSignal(ComponentBase):
    """
    out = a AND (NOT b).

    Used to express "a flag-setter that is not itself a branch": ARM CBNZ/CBZ
    set flags (sets_flags=1) but are branches, so they must NOT be dispatched
    to the ROB (they self-resolve from settled register operands).  This gate
    isolates plain flag-setters (CMP/SUBS) from compare-and-branch ops.
    Pure combinational -- no rising_edge().
    """
    name = "and_not_signal"
    ui_label = "AND-NOT Gate"
    ui_category = "control"
    ports_spec = {
        "a":   Port(1, "in", "Input A"),
        "b":   Port(1, "in", "Input B (negated)"),
        "out": Port(1, "out", "Gated output (A AND NOT B)"),
    }

    def evaluate(self):
        self["out"] = 1 if (self["a"] and not self["b"]) else 0
