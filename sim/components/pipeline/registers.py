"""
Pipeline registers for the 5-stage pipelined CPU.

Each register is a ComponentBase with input ports (from previous stage),
output ports (to next stage), plus stall and flush control.

evaluate() outputs the latched values.
rising_edge() latches new inputs (unless stalled) or inserts NOP bubble (if flushed).
"""
from sim.component.base import ComponentBase, Port


class IF_ID(ComponentBase):
    """Instruction Fetch → Instruction Decode pipeline register."""
    name = "if_id"
    ui_label = "IF/ID"
    ui_category = "pipeline"
    ports_spec = {
        # Inputs (from fetch stage)
        "pc_in":         Port(32, "in",  "PC from fetch"),
        "pc4_in":        Port(32, "in",  "PC+4 from fetch"),
        # 64-bit: x86 feeds an 8-byte LE instruction stream through IF/ID (a
        # 32-bit port silently truncated 5-6 byte instructions — imm32 high
        # bytes and Jcc rel32 displacements). RISC-V/ARM words fit unchanged.
        "instr_in":      Port(64, "in",  "Instruction from imem"),
        # Control
        "stall":         Port(1,  "in",  "Stall (hold current values)"),
        "flush":         Port(1,  "in",  "Flush (insert NOP bubble)"),
        "predict_flush": Port(1,  "in",  "Prediction squash (insert NOP bubble)"),
        "predicted_taken_in":  Port(1,  "in",  "IF-stage prediction in"),
        # Outputs (to decode stage)
        "pc_out":        Port(32, "out", "Latched PC"),
        "pc4_out":       Port(32, "out", "Latched PC+4"),
        "instr_out":     Port(64, "out", "Latched instruction"),
        "valid":         Port(1,  "out", "Valid instruction (not bubble)"),
        "predicted_taken_out": Port(1,  "out", "IF-stage prediction out"),
    }

    def __init__(self, nop_encoding: int = 0x00000013, **kw):
        super().__init__(**kw)
        self._pc = 0
        self._pc4 = 0
        self._instr = nop_encoding
        self._valid = 0
        self._nop = nop_encoding
        self._predicted_taken = 0

    def evaluate(self):
        self["pc_out"] = self._pc
        self["pc4_out"] = self._pc4
        self["instr_out"] = self._instr
        self["valid"] = self._valid
        self["predicted_taken_out"] = self._predicted_taken

    def rising_edge(self):
        if self["flush"]:
            self._pc = 0
            self._pc4 = 0
            self._instr = self._nop
            self._valid = 0
            self._predicted_taken = 0
        elif not self["stall"]:
            if self["predict_flush"]:
                self._pc = 0
                self._pc4 = 0
                self._instr = self._nop
                self._valid = 0
                self._predicted_taken = 0
            else:
                self._pc = self["pc_in"]
                self._pc4 = self["pc4_in"]
                self._instr = self["instr_in"]
                self._valid = 1
                self._predicted_taken = self["predicted_taken_in"]

    def get_state(self):
        return {
            "pc": f"0x{self['pc_out']:08x}",
            "instr": f"0x{self['instr_out']:08x}",
            "valid": "VALID" if self['valid'] else "BUBBLE",
        }


class ID_EX(ComponentBase):
    """Instruction Decode → Execute pipeline register."""
    name = "id_ex"
    ui_label = "ID/EX"
    ui_category = "pipeline"
    ports_spec = {
        # Data inputs
        "pc_in":         Port(32, "in"), "pc4_in":        Port(32, "in"),
        "rs1_data_in":   Port(32, "in"), "rs2_data_in":   Port(32, "in"),
        "imm_in":        Port(32, "in"),
        "rs1_addr_in":   Port(5,  "in"), "rs2_addr_in":   Port(5,  "in"),
        "rd_in":         Port(5,  "in"),
        # Control inputs
        "alu_op_in":     Port(4,  "in"), "alu_src_in":    Port(1,  "in"),
        "use_pc_in":     Port(1,  "in"),
        "mem_read_in":   Port(1,  "in"), "mem_write_in":  Port(1,  "in"),
        "reg_write_in":  Port(1,  "in"),
        "branch_in":     Port(1,  "in"), "branch_cond_in":Port(3,  "in"),
        "jal_in":        Port(1,  "in"), "jalr_in":       Port(1,  "in"),
        "wb_sel_in":     Port(2,  "in"),
        "write_flags_in": Port(1, "in"),
        "predicted_taken_in": Port(1, "in"),
        # Valid propagation from upstream (IF/ID)
        "valid_in":      Port(1,  "in",  "Valid from IF/ID"),
        # Pipeline control
        "stall":         Port(1,  "in"), "flush":         Port(1,  "in"),
        # Data outputs
        "pc_out":        Port(32, "out"), "pc4_out":       Port(32, "out"),
        "rs1_data_out":  Port(32, "out"), "rs2_data_out":  Port(32, "out"),
        "imm_out":       Port(32, "out"),
        "rs1_addr_out":  Port(5,  "out"), "rs2_addr_out":  Port(5,  "out"),
        "rd_out":        Port(5,  "out"),
        # Control outputs
        "alu_op_out":    Port(4,  "out"), "alu_src_out":   Port(1,  "out"),
        "use_pc_out":    Port(1,  "out"),
        "mem_read_out":  Port(1,  "out"), "mem_write_out": Port(1,  "out"),
        "reg_write_out": Port(1,  "out"),
        "branch_out":    Port(1,  "out"), "branch_cond_out":Port(3, "out"),
        "jal_out":       Port(1,  "out"), "jalr_out":      Port(1,  "out"),
        "wb_sel_out":    Port(2,  "out"),
        "write_flags_out": Port(1, "out"),
        "predicted_taken_out": Port(1, "out"),
        "valid":         Port(1,  "out"),
    }

    # Fields to latch: (port_suffix, width)
    _FIELDS = [
        "pc", "pc4", "rs1_data", "rs2_data", "imm",
        "rs1_addr", "rs2_addr", "rd",
        "alu_op", "alu_src", "use_pc",
        "mem_read", "mem_write", "reg_write",
        "branch", "branch_cond", "jal", "jalr", "wb_sel",
        "predicted_taken", "write_flags",
    ]

    def __init__(self, **kw):
        super().__init__(**kw)
        self._latched = {f: 0 for f in self._FIELDS}
        self._valid = 0

    def evaluate(self):
        for f in self._FIELDS:
            self[f"{f}_out"] = self._latched[f]
        self["valid"] = self._valid

    def rising_edge(self):
        if self["flush"] or self["stall"]:
            # Flush: branch mispredict clears the stage.
            # Stall: hazard-detector bubble insertion — the instruction
            #   currently in EX proceeds via EX/MEM (already captured by
            #   evaluate()), while the stalled IF/ID instruction must NOT
            #   enter EX yet, so we insert a bubble here.
            for f in self._FIELDS:
                self._latched[f] = 0
            self._valid = 0
        else:
            for f in self._FIELDS:
                self._latched[f] = self[f"{f}_in"]
            self._valid = 1 if self["valid_in"] else 0

    def get_state(self):
        return {
            "pc": f"0x{self['pc_out']:08x}",
            "rd": self['rd_out'],
            "alu_op": self['alu_op_out'],
            "valid": "VALID" if self['valid'] else "BUBBLE",
        }


class EX_MEM(ComponentBase):
    """Execute → Memory pipeline register."""
    name = "ex_mem"
    ui_label = "EX/MEM"
    ui_category = "pipeline"
    ports_spec = {
        # Data inputs
        "alu_result_in": Port(32, "in"), "alu_zero_in":    Port(1,  "in"),
        "rs2_data_in":   Port(32, "in"),
        "rd_in":         Port(5,  "in"),
        "pc_in":         Port(32, "in"), "pc4_in":         Port(32, "in"),
        "imm_in":        Port(32, "in"),
        "rs1_data_in":   Port(32, "in"),
        # Control inputs
        "mem_read_in":   Port(1,  "in"), "mem_write_in":   Port(1,  "in"),
        "reg_write_in":  Port(1,  "in"),
        "branch_in":     Port(1,  "in"), "branch_cond_in": Port(3,  "in"),
        "jal_in":        Port(1,  "in"), "jalr_in":        Port(1,  "in"),
        "wb_sel_in":     Port(2,  "in"),
        "predicted_taken_in": Port(1, "in"),
        # Flags captured at EX (ARM/x86: condition for THIS instruction's
        # branch resolution — a younger flag-writer in EX must not clobber it)
        "flags_zero_in":   Port(1,  "in"),
        "flags_result_in": Port(32, "in"),
        # Valid propagation from upstream (ID/EX)
        "valid_in":      Port(1,  "in",  "Valid from ID/EX"),
        # Pipeline control
        "flush":         Port(1,  "in"),
        # Data outputs
        "alu_result_out":Port(32, "out"), "alu_zero_out":   Port(1,  "out"),
        "rs2_data_out":  Port(32, "out"),
        "rd_out":        Port(5,  "out"),
        "pc_out":        Port(32, "out"), "pc4_out":        Port(32, "out"),
        "imm_out":       Port(32, "out"),
        "rs1_data_out":  Port(32, "out"),
        # Control outputs
        "mem_read_out":  Port(1,  "out"), "mem_write_out":  Port(1,  "out"),
        "reg_write_out": Port(1,  "out"),
        "branch_out":    Port(1,  "out"), "branch_cond_out":Port(3,  "out"),
        "jal_out":       Port(1,  "out"), "jalr_out":       Port(1,  "out"),
        "wb_sel_out":    Port(2,  "out"),
        "predicted_taken_out": Port(1, "out"),
        "flags_zero_out":   Port(1,  "out"),
        "flags_result_out": Port(32, "out"),
        "valid":         Port(1,  "out"),
    }

    _FIELDS = [
        "alu_result", "alu_zero", "rs2_data", "rd", "pc", "pc4", "imm", "rs1_data",
        "mem_read", "mem_write", "reg_write",
        "branch", "branch_cond", "jal", "jalr", "wb_sel",
        "predicted_taken", "flags_zero", "flags_result",
    ]

    def __init__(self, **kw):
        super().__init__(**kw)
        self._latched = {f: 0 for f in self._FIELDS}
        self._valid = 0

    def evaluate(self):
        for f in self._FIELDS:
            self[f"{f}_out"] = self._latched[f]
        self["valid"] = self._valid

    def rising_edge(self):
        if self["flush"]:
            for f in self._FIELDS:
                self._latched[f] = 0
            self._valid = 0
        else:
            for f in self._FIELDS:
                self._latched[f] = self[f"{f}_in"]
            self._valid = 1 if self["valid_in"] else 0

    def get_state(self):
        return {
            "pc": f"0x{self['pc_out']:08x}",
            "rd": self['rd_out'],
            "alu_result": self['alu_result_out'],
            "valid": "VALID" if self['valid'] else "BUBBLE",
        }


class MEM_WB(ComponentBase):
    """Memory → Writeback pipeline register."""
    name = "mem_wb"
    ui_label = "MEM/WB"
    ui_category = "pipeline"
    ports_spec = {
        # Data inputs
        "alu_result_in": Port(32, "in"),
        "mem_data_in":   Port(32, "in"),
        "rd_in":         Port(5,  "in"),
        "pc_in":         Port(32, "in"),
        "pc4_in":        Port(32, "in"),
        # Control inputs
        "reg_write_in":  Port(1,  "in"),
        "wb_sel_in":     Port(2,  "in"),
        # Valid propagation from upstream (EX/MEM)
        "valid_in":      Port(1,  "in",  "Valid from EX/MEM"),
        # Data outputs
        "alu_result_out":Port(32, "out"),
        "mem_data_out":  Port(32, "out"),
        "rd_out":        Port(5,  "out"),
        "pc_out":        Port(32, "out"),
        "pc4_out":       Port(32, "out"),
        # Control outputs
        "reg_write_out": Port(1,  "out"),
        "wb_sel_out":    Port(2,  "out"),
        "valid":         Port(1,  "out"),
    }

    _FIELDS = ["alu_result", "mem_data", "rd", "pc", "pc4", "reg_write", "wb_sel"]

    def __init__(self, **kw):
        super().__init__(**kw)
        self._latched = {f: 0 for f in self._FIELDS}
        self._valid = 0

    def evaluate(self):
        for f in self._FIELDS:
            self[f"{f}_out"] = self._latched[f]
        self["valid"] = self._valid

    def rising_edge(self):
        for f in self._FIELDS:
            self._latched[f] = self[f"{f}_in"]
        self._valid = 1 if self["valid_in"] else 0

    def get_state(self):
        return {
            "pc": f"0x{self['pc_out']:08x}",
            "rd": self['rd_out'],
            "wb_sel": self['wb_sel_out'],
            "valid": "VALID" if self['valid'] else "BUBBLE",
        }
