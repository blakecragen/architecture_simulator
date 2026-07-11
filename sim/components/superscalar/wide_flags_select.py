"""Wide flags selector for N-lane superscalar (ARM condition flags).

A flag-setting instruction (ARM SUBS/CMP) can land in any lane of a fetch
group, but the FlagsRegister has a single input set. This selector picks the
YOUNGEST (highest-lane, i.e. program-order-latest) flag-setter at EX/MEM to
drive the flags register, so flags reflect program order regardless of which
lane the flag-setter occupied. Squashed lanes carry write_flags=0 (their
ID/EX entry is a bubble), so they are naturally ignored.
"""
from sim.component.base import ComponentBase, Port


class WideFlagsSelect(ComponentBase):
    name = "wide_flags_select"
    ui_label = "Wide Flags Select"
    ui_category = "control"

    def __init__(self, num_lanes: int = 2, **kw):
        self.num_lanes = num_lanes
        self.ports_spec = {
            "write_flags_out": Port(1,  "out", "Selected lane sets flags"),
            "alu_zero_out":    Port(1,  "out", "Selected lane zero flag"),
            "alu_result_out":  Port(32, "out", "Selected lane ALU result"),
        }
        for i in range(num_lanes):
            self.ports_spec[f"write_flags_{i}"] = Port(1,  "in", f"Lane {i} sets flags")
            self.ports_spec[f"alu_zero_{i}"]    = Port(1,  "in", f"Lane {i} zero flag")
            self.ports_spec[f"alu_result_{i}"]  = Port(32, "in", f"Lane {i} ALU result")
        super().__init__(**kw)

    def evaluate(self):
        wf, zero, result = 0, 0, 0
        # Scan low -> high so the youngest (highest-index) flag-setter wins.
        for i in range(self.num_lanes):
            if self[f"write_flags_{i}"]:
                wf = 1
                zero = self[f"alu_zero_{i}"]
                result = self[f"alu_result_{i}"]
        self["write_flags_out"] = wf
        self["alu_zero_out"] = zero
        self["alu_result_out"] = result

    def get_state(self):
        return {
            "write_flags": self["write_flags_out"],
            "zero": self["alu_zero_out"],
        }
