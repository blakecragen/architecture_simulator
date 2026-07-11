"""Wide pipeline registers for N-lane superscalar pipeline.

Each register holds N contexts (one per lane). On stall, all contexts hold.
On flush, all contexts become NOP bubbles. Individual lanes can be invalidated
via lane_valid signals from the cross-lane hazard detector.
"""
from sim.component.base import ComponentBase, Port


class WideIF_ID(ComponentBase):
    """N-wide IF/ID pipeline register."""
    name = "wide_if_id"
    ui_label = "Wide IF/ID"
    ui_category = "pipeline"

    def __init__(self, num_lanes: int = 2, nop_encoding: int = 0x00000013, **kw):
        self.num_lanes = num_lanes
        self._nop = nop_encoding

        self.ports_spec = {
            "stall": Port(1, "in", "Stall all lanes"),
            "flush": Port(1, "in", "Flush all lanes"),
            "predict_flush": Port(1, "in", "Prediction squash"),
            "partial_squash": Port(1, "in", "Cross-lane squash (flush stale fetch)"),
        }
        for i in range(num_lanes):
            self.ports_spec[f"pc_in_{i}"]     = Port(32, "in",  f"Lane {i} PC in")
            self.ports_spec[f"pc4_in_{i}"]    = Port(32, "in",  f"Lane {i} PC+4 in")
            self.ports_spec[f"instr_in_{i}"]  = Port(32, "in",  f"Lane {i} instruction in")
            self.ports_spec[f"lane_valid_in_{i}"] = Port(1, "in", f"Lane {i} valid signal")
            self.ports_spec[f"predicted_taken_in_{i}"] = Port(1, "in", f"Lane {i} IF-stage prediction in")
            self.ports_spec[f"pc_out_{i}"]    = Port(32, "out", f"Lane {i} PC out")
            self.ports_spec[f"pc4_out_{i}"]   = Port(32, "out", f"Lane {i} PC+4 out")
            self.ports_spec[f"instr_out_{i}"] = Port(32, "out", f"Lane {i} instruction out")
            self.ports_spec[f"valid_{i}"]     = Port(1,  "out", f"Lane {i} valid out")
            self.ports_spec[f"predicted_taken_out_{i}"] = Port(1, "out", f"Lane {i} IF-stage prediction out")

        super().__init__(**kw)
        self._lanes = [{"pc": 0, "pc4": 0, "instr": nop_encoding, "valid": 0,
                        "predicted_taken": 0}
                       for _ in range(num_lanes)]

    def evaluate(self):
        for i in range(self.num_lanes):
            self[f"pc_out_{i}"]    = self._lanes[i]["pc"]
            self[f"pc4_out_{i}"]   = self._lanes[i]["pc4"]
            self[f"instr_out_{i}"] = self._lanes[i]["instr"]
            self[f"valid_{i}"]     = self._lanes[i]["valid"]
            self[f"predicted_taken_out_{i}"] = self._lanes[i]["predicted_taken"]

    def rising_edge(self):
        if self["flush"] or self["partial_squash"]:
            # Branch mispredict flush OR cross-lane squash (PC being corrected,
            # so the instructions currently in IF are stale — discard them).
            for i in range(self.num_lanes):
                self._lanes[i] = {"pc": 0, "pc4": 0, "instr": self._nop, "valid": 0,
                                  "predicted_taken": 0}
        elif not self["stall"]:
            if self["predict_flush"]:
                for i in range(self.num_lanes):
                    self._lanes[i] = {"pc": 0, "pc4": 0, "instr": self._nop, "valid": 0,
                                      "predicted_taken": 0}
            else:
                for i in range(self.num_lanes):
                    self._lanes[i] = {
                        "pc":    self[f"pc_in_{i}"],
                        "pc4":   self[f"pc4_in_{i}"],
                        "instr": self[f"instr_in_{i}"],
                        "valid": 1,
                        "predicted_taken": self[f"predicted_taken_in_{i}"],
                    }

    def get_state(self):
        state = {}
        for i in range(self.num_lanes):
            state[f"lane_{i}"] = {
                "pc": f"0x{self[f'pc_out_{i}']:08x}",
                "instr": f"0x{self[f'instr_out_{i}']:08x}",
                "valid": "VALID" if self[f'valid_{i}'] else "BUBBLE",
            }
        return state


# Fields that ID/EX, EX/MEM, and MEM/WB carry per lane
_ID_EX_FIELDS = [
    "pc", "pc4", "rs1_data", "rs2_data", "imm",
    "rs1_addr", "rs2_addr", "rd",
    "alu_op", "alu_src", "use_pc",
    "mem_read", "mem_write", "reg_write",
    "branch", "branch_cond", "jal", "jalr", "wb_sel",
    "write_flags",
    "predicted_taken",
]

_EX_MEM_FIELDS = [
    "alu_result", "alu_zero", "rs2_data", "rd", "pc", "pc4", "imm", "rs1_data",
    "mem_read", "mem_write", "reg_write",
    "branch", "branch_cond", "jal", "jalr", "wb_sel",
    "write_flags",
    "predicted_taken",
]

_MEM_WB_FIELDS = ["alu_result", "mem_data", "rd", "pc", "pc4", "reg_write", "wb_sel"]


class WideID_EX(ComponentBase):
    """N-wide ID/EX pipeline register."""
    name = "wide_id_ex"
    ui_label = "Wide ID/EX"
    ui_category = "pipeline"

    def __init__(self, num_lanes: int = 2, **kw):
        self.num_lanes = num_lanes
        self.ports_spec = {
            "stall": Port(1, "in", "Stall"),
            "flush": Port(1, "in", "Flush"),
        }
        for i in range(num_lanes):
            for f in _ID_EX_FIELDS:
                self.ports_spec[f"{f}_in_{i}"]  = Port(32, "in")
                self.ports_spec[f"{f}_out_{i}"] = Port(32, "out")
            self.ports_spec[f"lane_valid_in_{i}"] = Port(1, "in")
            self.ports_spec[f"valid_in_{i}"] = Port(1, "in",
                                                     f"Lane {i} upstream valid from IF/ID")
            self.ports_spec[f"valid_{i}"] = Port(1, "out")

        super().__init__(**kw)
        self._lanes = [{f: 0 for f in _ID_EX_FIELDS + ["valid"]}
                       for _ in range(num_lanes)]

    def evaluate(self):
        for i in range(self.num_lanes):
            for f in _ID_EX_FIELDS:
                self[f"{f}_out_{i}"] = self._lanes[i][f]
            self[f"valid_{i}"] = self._lanes[i]["valid"]

    def rising_edge(self):
        if self["flush"] or self["stall"]:
            # Flush or stall: insert bubble in all lanes (see ID_EX comment).
            for i in range(self.num_lanes):
                self._lanes[i] = {f: 0 for f in _ID_EX_FIELDS + ["valid"]}
        else:
            for i in range(self.num_lanes):
                if self[f"lane_valid_in_{i}"] and self[f"valid_in_{i}"]:
                    for f in _ID_EX_FIELDS:
                        self._lanes[i][f] = self[f"{f}_in_{i}"]
                    self._lanes[i]["valid"] = 1
                else:
                    self._lanes[i] = {f: 0 for f in _ID_EX_FIELDS + ["valid"]}

    def get_state(self):
        state = {}
        for i in range(self.num_lanes):
            state[f"lane_{i}"] = {
                "pc": f"0x{self[f'pc_out_{i}']:08x}",
                "rd": self[f'rd_out_{i}'],
                "alu_op": self[f'alu_op_out_{i}'],
                "valid": "VALID" if self[f'valid_{i}'] else "BUBBLE",
            }
        return state


class WideEX_MEM(ComponentBase):
    """N-wide EX/MEM pipeline register."""
    name = "wide_ex_mem"
    ui_label = "Wide EX/MEM"
    ui_category = "pipeline"

    def __init__(self, num_lanes: int = 2, **kw):
        self.num_lanes = num_lanes
        self.ports_spec = {
            "flush": Port(1, "in", "Flush"),
        }
        for i in range(num_lanes):
            for f in _EX_MEM_FIELDS:
                self.ports_spec[f"{f}_in_{i}"]  = Port(32, "in")
                self.ports_spec[f"{f}_out_{i}"] = Port(32, "out")
            self.ports_spec[f"valid_in_{i}"] = Port(1, "in",
                                                     f"Lane {i} valid from ID/EX")
            self.ports_spec[f"valid_{i}"] = Port(1, "out")

        super().__init__(**kw)
        self._lanes = [{f: 0 for f in _EX_MEM_FIELDS + ["valid"]}
                       for _ in range(num_lanes)]

    def evaluate(self):
        for i in range(self.num_lanes):
            for f in _EX_MEM_FIELDS:
                self[f"{f}_out_{i}"] = self._lanes[i][f]
            self[f"valid_{i}"] = self._lanes[i]["valid"]

    def rising_edge(self):
        if self["flush"]:
            for i in range(self.num_lanes):
                self._lanes[i] = {f: 0 for f in _EX_MEM_FIELDS + ["valid"]}
        else:
            for i in range(self.num_lanes):
                for f in _EX_MEM_FIELDS:
                    self._lanes[i][f] = self[f"{f}_in_{i}"]
                self._lanes[i]["valid"] = 1 if self[f"valid_in_{i}"] else 0

    def get_state(self):
        state = {}
        for i in range(self.num_lanes):
            state[f"lane_{i}"] = {
                "pc": f"0x{self[f'pc_out_{i}']:08x}",
                "rd": self[f'rd_out_{i}'],
                "alu_result": self[f'alu_result_out_{i}'],
                "valid": "VALID" if self[f'valid_{i}'] else "BUBBLE",
            }
        return state


class WideMEM_WB(ComponentBase):
    """N-wide MEM/WB pipeline register."""
    name = "wide_mem_wb"
    ui_label = "Wide MEM/WB"
    ui_category = "pipeline"

    def __init__(self, num_lanes: int = 2, **kw):
        self.num_lanes = num_lanes
        self.ports_spec = {}
        for i in range(num_lanes):
            for f in _MEM_WB_FIELDS:
                self.ports_spec[f"{f}_in_{i}"]  = Port(32, "in")
                self.ports_spec[f"{f}_out_{i}"] = Port(32, "out")
            self.ports_spec[f"valid_in_{i}"] = Port(1, "in",
                                                     f"Lane {i} valid from EX/MEM")
            self.ports_spec[f"valid_{i}"] = Port(1, "out")

        super().__init__(**kw)
        self._lanes = [{f: 0 for f in _MEM_WB_FIELDS + ["valid"]}
                       for _ in range(num_lanes)]

    def evaluate(self):
        for i in range(self.num_lanes):
            for f in _MEM_WB_FIELDS:
                self[f"{f}_out_{i}"] = self._lanes[i][f]
            self[f"valid_{i}"] = self._lanes[i]["valid"]

    def rising_edge(self):
        for i in range(self.num_lanes):
            for f in _MEM_WB_FIELDS:
                self._lanes[i][f] = self[f"{f}_in_{i}"]
            self._lanes[i]["valid"] = 1 if self[f"valid_in_{i}"] else 0

    def get_state(self):
        state = {}
        for i in range(self.num_lanes):
            state[f"lane_{i}"] = {
                "pc": f"0x{self[f'pc_out_{i}']:08x}",
                "rd": self[f'rd_out_{i}'],
                "wb_sel": self[f'wb_sel_out_{i}'],
                "valid": "VALID" if self[f'valid_{i}'] else "BUBBLE",
            }
        return state
