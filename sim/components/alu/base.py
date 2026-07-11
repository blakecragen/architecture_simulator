from sim.component.base import ComponentBase, Port


class ALUBase(ComponentBase):
    """Port contract for all ALU implementations. Swap freely."""
    name = "alu_base"
    ui_category = "execute"
    ports_spec = {
        "a":      Port(32, "in",  "Operand A"),
        "b":      Port(32, "in",  "Operand B"),
        "op":     Port(4,  "in",  "Operation code"),
        "result": Port(32, "out", "Result"),
        "zero":   Port(1,  "out", "Zero flag"),
    }
