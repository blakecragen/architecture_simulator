"""Memory lane mux for superscalar pipeline.

Routes memory operations from any lane to the single-ported data memory.
Lane 0 has priority; if lane 0 is not doing a memory operation, lane 1's
operation is routed instead.

Also routes the read result back so any lane can receive load data.
"""
from sim.component.base import ComponentBase, Port


class MemoryLaneMux(ComponentBase):
    """
    Selects which lane's memory signals reach the shared DataMemory.

    Priority: lane 0 > lane 1 > ... > lane N-1.
    At most one memory operation per cycle.
    """
    name = "memory_lane_mux"
    ui_label = "Mem Lane Mux"
    ui_category = "memory"

    def __init__(self, num_lanes: int = 2, **kw):
        self.num_lanes = num_lanes
        self.ports_spec = {
            # Output to DataMemory
            "addr_out":     Port(32, "out", "Selected byte address"),
            "wdata_out":    Port(32, "out", "Selected write data"),
            "wen_out":      Port(1,  "out", "Selected write enable"),
            # Input from DataMemory
            "rdata_in":     Port(32, "in",  "Read data from memory"),
            # Which lane is active (-1 = none)
            "active_lane":  Port(8,  "out", "Active memory lane"),
        }

        for i in range(num_lanes):
            self.ports_spec[f"addr_{i}"]      = Port(32, "in", f"Lane {i} byte address")
            self.ports_spec[f"wdata_{i}"]     = Port(32, "in", f"Lane {i} write data")
            self.ports_spec[f"mem_read_{i}"]  = Port(1,  "in", f"Lane {i} mem read")
            self.ports_spec[f"mem_write_{i}"] = Port(1,  "in", f"Lane {i} mem write")
            self.ports_spec[f"rdata_out_{i}"] = Port(32, "out", f"Lane {i} read data")

        super().__init__(**kw)

    def evaluate(self):
        # Find the lowest-numbered lane with a memory operation
        active = -1
        for i in range(self.num_lanes):
            if self[f"mem_read_{i}"] or self[f"mem_write_{i}"]:
                active = i
                break

        self["active_lane"] = active & 0xFF

        if active >= 0:
            self["addr_out"]  = self[f"addr_{active}"]
            self["wdata_out"] = self[f"wdata_{active}"]
            self["wen_out"]   = self[f"mem_write_{active}"]
        else:
            self["addr_out"]  = 0
            self["wdata_out"] = 0
            self["wen_out"]   = 0

        # Route read data to all lanes (only the one with mem_read will use it)
        for i in range(self.num_lanes):
            self[f"rdata_out_{i}"] = self["rdata_in"]

    def get_state(self):
        al = self["active_lane"]
        return {
            "active_lane": al if al < self.num_lanes else "none",
            "addr": f"0x{self['addr_out']:08x}",
            "wen": self["wen_out"],
        }
