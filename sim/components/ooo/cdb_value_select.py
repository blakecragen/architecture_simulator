"""CDB value select for Out-of-Order execution.

For loads, the ALU computes the *address*; the value that must be broadcast on
the Common Data Bus to waiting reservation-station entries is the data memory
read result. The ROB already performs this per-entry select internally when an
instruction completes (see ReorderBuffer.rising_edge); this component applies
the same select to the RS snoop path, so a dependent instruction captures the
loaded data rather than the load's address.
"""
from sim.component.base import ComponentBase, Port


class CdbValueSelect(ComponentBase):
    name = "cdb_value_select"
    ui_label = "CDB Value Select"
    ui_category = "ooo"
    ports_spec = {
        "is_load":   Port(1,  "in",  "1 = completing instruction is a load"),
        "alu_value": Port(32, "in",  "ALU result (address for loads)"),
        "mem_value": Port(32, "in",  "Data memory read result"),
        "value":     Port(32, "out", "Selected CDB broadcast value"),
    }

    def evaluate(self):
        if self["is_load"]:
            self["value"] = self["mem_value"]
        else:
            self["value"] = self["alu_value"]

    def get_state(self):
        return {
            "is_load": self["is_load"],
            "value": f"0x{self['value']:08x}",
        }
