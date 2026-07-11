from sim.component.base import ComponentBase, Port
from sim.core.signals import WBSel


class WritebackUnit(ComponentBase):
    """Writeback mux — selects between ALU result, memory read, and PC+4."""
    name = "writeback"
    ui_label = "Writeback Mux"
    ui_category = "writeback"
    ports_spec = {
        "alu_in":   Port(32, "in",  "ALU result"),
        "mem_in":   Port(32, "in",  "Memory read data"),
        "pc4_in":   Port(32, "in",  "PC + 4"),
        "sel":      Port(2,  "in",  "Source select"),
        "data_out": Port(32, "out", "Selected writeback data"),
    }

    def evaluate(self):
        sel = self["sel"]
        if sel == WBSel.ALU:
            self["data_out"] = self["alu_in"]
        elif sel == WBSel.MEMORY:
            self["data_out"] = self["mem_in"]
        elif sel == WBSel.PC4:
            self["data_out"] = self["pc4_in"]
        else:
            self["data_out"] = 0

    def get_state(self):
        from sim.core.signals import WB_SEL_NAMES
        return {
            "sel": WB_SEL_NAMES.get(self["sel"], str(self["sel"])),
            "data_out": self["data_out"],
        }
