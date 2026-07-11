from sim.component.base import ComponentBase, Port


class AluInputMux(ComponentBase):
    """
    Mux for ALU inputs A and B.
    A: selects between rs1_data (use_pc=0) and PC (use_pc=1).
    B: selects between rs2_data (alu_src=0) and immediate (alu_src=1).
    """
    name = "alu_input_mux"
    ui_label = "ALU Input Mux"
    ui_category = "execute"
    ports_spec = {
        "rs1_data": Port(32, "in",  "Register source 1 data"),
        "rs2_data": Port(32, "in",  "Register source 2 data"),
        "pc":       Port(32, "in",  "Program counter"),
        "imm":      Port(32, "in",  "Immediate value"),
        "use_pc":   Port(1,  "in",  "Select PC for input A"),
        "alu_src":  Port(1,  "in",  "Select immediate for input B"),
        "alu_a":    Port(32, "out", "ALU input A"),
        "alu_b":    Port(32, "out", "ALU input B"),
    }

    def evaluate(self):
        self["alu_a"] = self["pc"] if self["use_pc"] else self["rs1_data"]
        self["alu_b"] = self["imm"] if self["alu_src"] else self["rs2_data"]
