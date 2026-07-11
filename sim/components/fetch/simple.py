from sim.component.base import ComponentBase, Port


class SimpleFetch(ComponentBase):
    """
    Fetch unit — manages the program counter.
    Outputs current PC and PC+4.

    In single-cycle mode: next_pc is always provided by branch resolution.
    In pipeline mode: defaults to PC+4, overridden by branch_taken + next_pc.
    Supports stall (hold PC) for hazard detection.
    """
    name = "simple_fetch"
    ui_label = "Fetch Unit"
    ui_category = "fetch"
    ports_spec = {
        "next_pc":        Port(32, "in",  "Next PC from branch resolution"),
        "branch_taken":   Port(1,  "in",  "Override PC with next_pc"),
        "predict_taken":  Port(1,  "in",  "Branch predictor says taken"),
        "predict_target": Port(32, "in",  "Predicted branch target PC"),
        "stall":          Port(1,  "in",  "Hold current PC (hazard stall)"),
        "pc_out":         Port(32, "out", "Current PC"),
        "pc4_out":        Port(32, "out", "PC + 4"),
    }

    def __init__(self, pc_reset: int = 0, **kw):
        super().__init__(**kw)
        self._pc = pc_reset

    def evaluate(self):
        self["pc_out"] = self._pc
        self["pc4_out"] = (self._pc + 4) & 0xFFFF_FFFF

    def rising_edge(self):
        # Precedence: a resolved branch redirect wins (the multi-cycle
        # controller asserts stall to hold the PC across F/D/E phases yet
        # still redirects on a taken branch). A load-use stall must outrank
        # branch *prediction*, though: when a hazard is detected the
        # dependent instruction has not read its operand, so predicting a
        # redirect this cycle would drop the held instruction.
        if self["branch_taken"]:
            self._pc = self["next_pc"]
        elif self["stall"]:
            return
        elif self["predict_taken"]:
            self._pc = self["predict_target"]
        else:
            self._pc = (self._pc + 4) & 0xFFFF_FFFF

    def get_state(self):
        return {
            "pc": f"0x{self['pc_out']:08x}",
            "pc4": f"0x{self['pc4_out']:08x}",
        }
