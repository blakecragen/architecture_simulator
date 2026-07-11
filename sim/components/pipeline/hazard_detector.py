"""
Hazard detection unit — detects load-use (RAW) hazards and generates stall signals.
"""
from sim.component.base import ComponentBase, Port


class HazardDetector(ComponentBase):
    """
    Detects load-use hazards: if the ID/EX stage has a load (mem_read=1)
    and the instruction in IF/ID depends on the load destination.
    """
    name = "hazard_detector"
    ui_label = "Hazard Detector"
    ui_category = "control"
    ports_spec = {
        # From ID/EX register
        "id_ex_mem_read": Port(1, "in",  "ID/EX stage is a load"),
        "id_ex_rd":       Port(5, "in",  "ID/EX destination register"),
        # From decoder (current instruction in ID stage)
        "if_id_rs1":      Port(5, "in",  "IF/ID source register 1"),
        "if_id_rs2":      Port(5, "in",  "IF/ID source register 2"),
        # Outputs
        "stall":          Port(1, "out", "Stall the pipeline (IF and IF/ID hold)"),
    }

    def evaluate(self):
        stall = 0
        if self["id_ex_mem_read"]:
            rd = self["id_ex_rd"]
            if rd != 0:  # Don't stall on x0
                if rd == self["if_id_rs1"] or rd == self["if_id_rs2"]:
                    stall = 1
        self["stall"] = stall

    def get_state(self):
        result = {
            "stall": "STALL" if self["stall"] else "OK",
        }
        if self["stall"]:
            rd = self["id_ex_rd"]
            rs1 = self["if_id_rs1"]
            rs2 = self["if_id_rs2"]
            result["hazard_type"] = "Load-Use"
            result["stall_rd"] = rd
            conflicting = []
            if rd == rs1:
                conflicting.append(rs1)
            if rd == rs2 and rs2 != rs1:
                conflicting.append(rs2)
            result["conflicting_regs"] = conflicting
        return result
