"""Superscalar fetch unit — advances PC by 4*N per cycle."""
from sim.component.base import ComponentBase, Port


class SuperscalarFetch(ComponentBase):
    """
    Superscalar fetch unit. Outputs current PC and advances by 4*num_lanes
    each cycle (unless stalled or branch taken).

    Outputs pc_out (base PC) and pc_lane_{i} for each lane's individual PC.
    """
    name = "superscalar_fetch"
    ui_label = "Superscalar Fetch"
    ui_category = "fetch"

    def __init__(self, num_lanes: int = 2, pc_reset: int = 0, **kw):
        self.num_lanes = num_lanes
        self.ports_spec = {
            "next_pc":        Port(32, "in",  "Next PC from branch resolution"),
            "branch_taken":   Port(1,  "in",  "Override PC with next_pc"),
            "predict_taken":  Port(1,  "in",  "Branch predictor says taken"),
            "predict_target": Port(32, "in",  "Predicted branch target PC"),
            "stall":          Port(1,  "in",  "Hold current PC"),
            "partial_squash": Port(1,  "in",  "Intra-group squash, re-fetch from boundary"),
            "squash_from":    Port(8,  "in",  "Lanes that executed (re-fetch boundary)"),
            "pc_out":         Port(32, "out", "Base PC (lane 0)"),
        }
        for i in range(num_lanes):
            self.ports_spec[f"pc_lane_{i}"] = Port(32, "out", f"PC for lane {i}")
            self.ports_spec[f"pc4_lane_{i}"] = Port(32, "out", f"PC+4 for lane {i} (link/return value)")
        self.ports_spec["pc_next_group"] = Port(32, "out", "PC of next fetch group")
        super().__init__(**kw)
        self._pc = pc_reset

    def evaluate(self):
        self["pc_out"] = self._pc
        for i in range(self.num_lanes):
            self[f"pc_lane_{i}"] = (self._pc + i * 4) & 0xFFFF_FFFF
            self[f"pc4_lane_{i}"] = (self._pc + i * 4 + 4) & 0xFFFF_FFFF
        self["pc_next_group"] = (self._pc + self.num_lanes * 4) & 0xFFFF_FFFF

    def rising_edge(self):
        # Precedence: resolved branch redirect > stall > prediction (see
        # SimpleFetch). A load-use stall must outrank branch prediction so
        # the held group is not dropped.
        if self["branch_taken"]:
            self._pc = self["next_pc"]
        elif self["stall"]:
            return
        elif self["predict_taken"]:
            self._pc = self["predict_target"]
        elif self["partial_squash"]:
            # Re-fetch from the first squashed lane. The group currently in
            # decode advanced the PC by a full group last cycle, so retreat by
            # the lanes that did NOT execute: (num_lanes - squash_from) * 4.
            executed = self["squash_from"] or 1
            self._pc = (self._pc - (self.num_lanes - executed) * 4) & 0xFFFF_FFFF
        else:
            self._pc = (self._pc + self.num_lanes * 4) & 0xFFFF_FFFF

    def get_state(self):
        state = {"pc": f"0x{self._pc:08x}"}
        for i in range(self.num_lanes):
            state[f"pc_lane_{i}"] = f"0x{self[f'pc_lane_{i}']:08x}"
        return state
