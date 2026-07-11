"""Store Commit Unit for Out-of-Order execution.

Routes store data from the ROB commit path to data memory.
Stores only write memory when the ROB commits them in program order.
"""
from sim.component.base import ComponentBase, Port, mask32


class StoreCommitUnit(ComponentBase):
    """
    Bridges the ROB commit interface to dmem write ports.

    When the ROB commits a store (commit_en && commit_is_store),
    this unit drives the dmem write address, data, and enable.
    """
    name = "store_commit_unit"
    ui_label = "Store Commit"
    ui_category = "ooo"
    ports_spec = {
        "commit_en":       Port(1,  "in",  "ROB commit enable"),
        "commit_is_store": Port(1,  "in",  "Committed instruction is a store"),
        "commit_addr":     Port(32, "in",  "Store address (ALU result from ROB)"),
        "commit_data":     Port(32, "in",  "Store data (read from the regfile at COMMIT via rs3)"),
        "dmem_wen":        Port(1,  "out", "Data memory write enable"),
        "dmem_waddr":      Port(32, "out", "Data memory write address"),
        "dmem_wdata":      Port(32, "out", "Data memory write data"),
    }

    def evaluate(self):
        if self["commit_en"] and self["commit_is_store"]:
            self["dmem_wen"] = 1
            self["dmem_waddr"] = mask32(self["commit_addr"])
            self["dmem_wdata"] = mask32(self["commit_data"])
        else:
            self["dmem_wen"] = 0
            self["dmem_waddr"] = 0
            self["dmem_wdata"] = 0

    def get_state(self):
        return {
            "wen": self["dmem_wen"],
            "addr": f"0x{self['dmem_waddr']:08x}",
            "data": f"0x{self['dmem_wdata']:08x}",
        }
