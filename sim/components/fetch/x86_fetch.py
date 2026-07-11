"""x86 fetch unit with variable-length PC increment."""
from sim.component.base import ComponentBase, Port


class X86Fetch(ComponentBase):
    """
    Fetch unit for x86 variable-length instructions.
    PC advances by instruction length (from decoder), not fixed +4.
    """
    name = "x86_fetch"
    ui_label = "x86 Fetch"
    ui_category = "fetch"
    ports_spec = {
        "next_pc":        Port(32, "in",  "Next PC from branch resolution"),
        "instr_len":      Port(4,  "in",  "Current instruction length in bytes"),
        "branch_taken":   Port(1,  "in",  "Branch was taken (use next_pc)"),
        "predict_taken":  Port(1,  "in",  "Branch predictor says taken"),
        "predict_target": Port(32, "in",  "Predicted branch target PC"),
        "stall":          Port(1,  "in",  "Hold current PC (hazard stall)"),
        "pc_out":         Port(32, "out", "Current PC"),
        "pc_plus_len":    Port(32, "out", "PC + instruction length"),
    }

    def __init__(self, pc_reset: int = 0, **kw):
        super().__init__(**kw)
        self._pc = pc_reset

    def evaluate(self):
        self["pc_out"] = self._pc
        length = self["instr_len"] if self["instr_len"] > 0 else 1
        self["pc_plus_len"] = (self._pc + length) & 0xFFFF_FFFF

    def rising_edge(self):
        # PC precedence: branch_taken > stall > predict_taken > +len
        # (matches SimpleFetch/SuperscalarFetch and the documented contract).
        # A load-use stall must outrank a taken prediction: the held
        # instruction has not yet read its operand, so honouring a redirect
        # this cycle would drop it.
        if self["branch_taken"]:
            self._pc = self["next_pc"]
        elif self["stall"]:
            pass  # hold current PC
        elif self["predict_taken"]:
            self._pc = self["predict_target"]
        else:
            length = self["instr_len"] if self["instr_len"] > 0 else 1
            self._pc = (self._pc + length) & 0xFFFF_FFFF

    def get_state(self):
        return {
            "pc": f"0x{self['pc_out']:08x}",
            "pc_plus_len": f"0x{self['pc_plus_len']:08x}",
            "instr_len": self["instr_len"],
        }
