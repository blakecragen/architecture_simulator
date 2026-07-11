"""Wide forwarding unit for N-lane superscalar pipeline."""
from sim.component.base import ComponentBase, Port


class WideForwardingUnit(ComponentBase):
    """
    N-lane forwarding unit. For each lane, checks:
    1. EX/MEM forwarding from any lane
    2. MEM/WB forwarding from any lane

    Priority: EX/MEM > MEM/WB > register file value.
    """
    name = "wide_forwarding_unit"
    ui_label = "Wide Forwarding"
    ui_category = "control"

    def __init__(self, num_lanes: int = 2, zero_reg_index: int | None = 0, **kw):
        self.num_lanes = num_lanes
        # Architectural register hardwired to zero (never a forward source/target):
        # RISC-V x0 (0), ARM XZR (31), x86 none (None). -1 disables the check.
        self._zero = -1 if zero_reg_index is None else zero_reg_index
        self.ports_spec = {}

        # Per-lane inputs: source register addresses and regfile values
        for i in range(num_lanes):
            self.ports_spec[f"id_ex_rs1_{i}"]  = Port(5,  "in")
            self.ports_spec[f"id_ex_rs2_{i}"]  = Port(5,  "in")
            self.ports_spec[f"rs1_data_in_{i}"] = Port(32, "in")
            self.ports_spec[f"rs2_data_in_{i}"] = Port(32, "in")

        # EX/MEM stage outputs from all lanes (potential forward sources)
        for i in range(num_lanes):
            self.ports_spec[f"ex_mem_rd_{i}"]         = Port(5,  "in")
            self.ports_spec[f"ex_mem_reg_write_{i}"]   = Port(1,  "in")
            self.ports_spec[f"ex_mem_alu_result_{i}"]  = Port(32, "in")

        # MEM/WB stage outputs from all lanes
        for i in range(num_lanes):
            self.ports_spec[f"mem_wb_rd_{i}"]         = Port(5,  "in")
            self.ports_spec[f"mem_wb_reg_write_{i}"]  = Port(1,  "in")
            self.ports_spec[f"mem_wb_data_{i}"]       = Port(32, "in")

        # Per-lane outputs: forwarded values
        for i in range(num_lanes):
            self.ports_spec[f"rs1_data_out_{i}"] = Port(32, "out")
            self.ports_spec[f"rs2_data_out_{i}"] = Port(32, "out")

        super().__init__(**kw)

    def _forward_value(self, rs_addr: int, default_val: int) -> int:
        """Check all EX/MEM and MEM/WB lanes for a forwarding match.

        Within a fetch group, lane order is program order (lane 0 oldest,
        lane N-1 youngest). When several in-flight lanes write the same
        architectural register, the correct forwarding source is the
        YOUNGEST writer, so scan lanes from highest index to lowest.
        """
        if rs_addr == self._zero:
            return default_val

        # Priority 1: EX/MEM from any lane (youngest wins)
        for j in reversed(range(self.num_lanes)):
            if (self[f"ex_mem_reg_write_{j}"] and
                    self[f"ex_mem_rd_{j}"] == rs_addr and
                    self[f"ex_mem_rd_{j}"] != self._zero):
                return self[f"ex_mem_alu_result_{j}"]

        # Priority 2: MEM/WB from any lane (youngest wins)
        for j in reversed(range(self.num_lanes)):
            if (self[f"mem_wb_reg_write_{j}"] and
                    self[f"mem_wb_rd_{j}"] == rs_addr and
                    self[f"mem_wb_rd_{j}"] != self._zero):
                return self[f"mem_wb_data_{j}"]

        return default_val

    def evaluate(self):
        for i in range(self.num_lanes):
            rs1 = self[f"id_ex_rs1_{i}"]
            rs2 = self[f"id_ex_rs2_{i}"]
            self[f"rs1_data_out_{i}"] = self._forward_value(rs1, self[f"rs1_data_in_{i}"])
            self[f"rs2_data_out_{i}"] = self._forward_value(rs2, self[f"rs2_data_in_{i}"])

    def get_state(self):
        return {f"lane_{i}": "active" for i in range(self.num_lanes)}
