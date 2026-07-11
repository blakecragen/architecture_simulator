"""Wide register file — 2N read ports + N write ports for superscalar."""
from sim.component.base import ComponentBase, Port


class WideRegisterFile(ComponentBase):
    """
    Register file with 2*N read ports and N write ports for N-lane superscalar.

    Lane i reads rs1_addr_i/rs2_addr_i and writes rd_addr_i.
    Reads are combinational, writes are sequential.
    """
    name = "wide_register_file"
    ui_label = "Wide Register File"
    ui_category = "decode"

    def __init__(self, num_regs: int = 32, zero_reg: bool = True,
                 zero_reg_index: int = 0, num_lanes: int = 2, **kw):
        self.num_regs = num_regs
        self.zero_reg = zero_reg
        self.zero_reg_index = zero_reg_index
        self.num_lanes = num_lanes

        self.ports_spec = {}
        for i in range(num_lanes):
            self.ports_spec[f"rs1_addr_{i}"] = Port(5,  "in",  f"Lane {i} read addr 1")
            self.ports_spec[f"rs2_addr_{i}"] = Port(5,  "in",  f"Lane {i} read addr 2")
            self.ports_spec[f"rs1_data_{i}"] = Port(32, "out", f"Lane {i} read data 1")
            self.ports_spec[f"rs2_data_{i}"] = Port(32, "out", f"Lane {i} read data 2")
            self.ports_spec[f"rd_addr_{i}"]  = Port(5,  "in",  f"Lane {i} write addr")
            self.ports_spec[f"rd_data_{i}"]  = Port(32, "in",  f"Lane {i} write data")
            self.ports_spec[f"wen_{i}"]      = Port(1,  "in",  f"Lane {i} write enable")

        super().__init__(**kw)
        self.regs = [0] * num_regs

    def _read_reg(self, addr: int) -> int:
        addr = addr % self.num_regs
        if self.zero_reg and addr == self.zero_reg_index:
            return 0
        # Write-through (write-first-half / read-second-half): a same-cycle
        # write to this register is visible on the read ports. Without this a
        # writeback that coincides with a younger instruction's ID read (a RAW
        # across fetch groups) returns the stale value. Scan lanes low->high so
        # the highest-index (youngest) writer wins, matching rising_edge().
        val = self.regs[addr]
        for i in range(self.num_lanes):
            if self[f"wen_{i}"] and (self[f"rd_addr_{i}"] % self.num_regs) == addr:
                val = self[f"rd_data_{i}"]
        return val

    def evaluate(self):
        for i in range(self.num_lanes):
            self[f"rs1_data_{i}"] = self._read_reg(self[f"rs1_addr_{i}"])
            self[f"rs2_data_{i}"] = self._read_reg(self[f"rs2_addr_{i}"])

    def rising_edge(self):
        # Write in lane order low->high; on a same-register conflict the
        # highest-index (youngest, program-order-newest) lane wins, matching the
        # write-through read path in _read_reg().
        for i in range(self.num_lanes):
            if self[f"wen_{i}"]:
                rd = self[f"rd_addr_{i}"] % self.num_regs
                if not (self.zero_reg and rd == self.zero_reg_index):
                    self.regs[rd] = self[f"rd_data_{i}"]

    def get_state(self):
        return {"registers": list(self.regs)}
