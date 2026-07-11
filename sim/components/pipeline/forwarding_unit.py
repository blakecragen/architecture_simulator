"""
Forwarding unit — resolves EX→EX and MEM→EX data hazards by selecting
forwarded data instead of stale register file values.
"""
from sim.component.base import ComponentBase, Port


class ForwardingUnit(ComponentBase):
    """
    Checks if the source registers of the EX-stage instruction match the
    destination registers of instructions in EX/MEM or MEM/WB stages.
    Outputs forwarded values or signals to use the register file values.

    Forward A/B: 0 = no forward (use regfile), 1 = from EX/MEM, 2 = from MEM/WB
    """
    name = "forwarding_unit"
    ui_label = "Forwarding Unit"
    ui_category = "control"

    def __init__(self, zero_reg_index: int | None = 0, **kw):
        super().__init__(**kw)
        # The register that always reads 0 and must never be a forwarding
        # source (RISC-V x0 = 0, ARM XZR = 31). x86 has no zero register, so
        # pass None — every register, including EAX (index 0), forwards.
        self._zero = -1 if zero_reg_index is None else zero_reg_index

    ports_spec = {
        # Source registers of instruction in EX stage (from ID/EX)
        "id_ex_rs1":       Port(5,  "in"),
        "id_ex_rs2":       Port(5,  "in"),
        # EX/MEM stage destination
        "ex_mem_rd":       Port(5,  "in"),
        "ex_mem_reg_write":Port(1,  "in"),
        "ex_mem_alu_result":Port(32,"in"),
        # MEM/WB stage destination
        "mem_wb_rd":       Port(5,  "in"),
        "mem_wb_reg_write":Port(1,  "in"),
        "mem_wb_data":     Port(32, "in"),  # writeback data (after wb mux)
        # Register file values (from ID/EX latch)
        "rs1_data_in":     Port(32, "in"),
        "rs2_data_in":     Port(32, "in"),
        # Outputs: forwarded values
        "rs1_data_out":    Port(32, "out"),
        "rs2_data_out":    Port(32, "out"),
        "forward_a":       Port(2,  "out", "0=reg, 1=EX/MEM, 2=MEM/WB"),
        "forward_b":       Port(2,  "out", "0=reg, 1=EX/MEM, 2=MEM/WB"),
    }

    def evaluate(self):
        rs1 = self["id_ex_rs1"]
        rs2 = self["id_ex_rs2"]

        # Forward A (rs1)
        fwd_a = 0
        val_a = self["rs1_data_in"]
        if (self["ex_mem_reg_write"] and self["ex_mem_rd"] != self._zero
                and self["ex_mem_rd"] == rs1):
            fwd_a = 1
            val_a = self["ex_mem_alu_result"]
        elif (self["mem_wb_reg_write"] and self["mem_wb_rd"] != self._zero
              and self["mem_wb_rd"] == rs1):
            fwd_a = 2
            val_a = self["mem_wb_data"]

        # Forward B (rs2)
        fwd_b = 0
        val_b = self["rs2_data_in"]
        if (self["ex_mem_reg_write"] and self["ex_mem_rd"] != self._zero
                and self["ex_mem_rd"] == rs2):
            fwd_b = 1
            val_b = self["ex_mem_alu_result"]
        elif (self["mem_wb_reg_write"] and self["mem_wb_rd"] != self._zero
              and self["mem_wb_rd"] == rs2):
            fwd_b = 2
            val_b = self["mem_wb_data"]

        self["forward_a"] = fwd_a
        self["forward_b"] = fwd_b
        self["rs1_data_out"] = val_a
        self["rs2_data_out"] = val_b

    def get_state(self):
        fwd_names = {0: "REG", 1: "EX/MEM", 2: "MEM/WB"}
        return {
            "forward_a": fwd_names.get(self["forward_a"], str(self["forward_a"])),
            "forward_b": fwd_names.get(self["forward_b"], str(self["forward_b"])),
        }
