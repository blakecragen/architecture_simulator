"""x86 flags register — latches ALU flags for use by Jcc instructions."""
from sim.component.base import ComponentBase, Port


class FlagsRegister(ComponentBase):
    """
    x86 EFLAGS latch. Sits between the ALU and the branch resolution unit.

    When write_flags=1 (CMP, ADD, SUB, etc.): passes through current ALU outputs
    and latches them on the rising edge.

    When write_flags=0 (Jcc, MOV, etc.): outputs the latched values from the
    last flag-setting instruction.
    """
    name = "flags_register"
    ui_label = "Flags Register"
    ui_category = "execute"
    ports_spec = {
        "alu_zero_in":   Port(1,  "in",  "Current ALU zero flag"),
        "alu_result_in": Port(32, "in",  "Current ALU result"),
        "write_flags":   Port(1,  "in",  "Latch new flags this cycle"),
        "zero_out":      Port(1,  "out", "Effective zero flag"),
        "result_out":    Port(32, "out", "Effective ALU result"),
    }

    def __init__(self, **kw):
        super().__init__(**kw)
        self._latched_zero = 0
        self._latched_result = 0

    def evaluate(self):
        if self["write_flags"]:
            self["zero_out"] = self["alu_zero_in"]
            self["result_out"] = self["alu_result_in"]
        else:
            self["zero_out"] = self._latched_zero
            self["result_out"] = self._latched_result

    def rising_edge(self):
        if self["write_flags"]:
            self._latched_zero = self["alu_zero_in"]
            self._latched_result = self["alu_result_in"]

    def get_state(self):
        return {
            "zero": self._latched_zero,
            "result": self._latched_result,
            "write_flags": self["write_flags"],
        }
