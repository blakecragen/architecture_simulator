from sim.component.base import ComponentBase, Port


class Latch(ComponentBase):
    """
    Generic single-value register (latch).

    On rising_edge, if enable is asserted, captures data_in into _value.
    evaluate() drives data_out from _value (registered output).

    Instantiated as ir (instruction register), reg_a, reg_b, alu_out
    in the multi-cycle preset.
    """
    name = "latch"
    ui_label = "Latch"
    ui_category = "pipeline"
    ports_spec = {
        # 64-bit so the x86 IR latch carries the full 8-byte instruction
        # stream (a 32-bit IR silently truncated 5-6 byte instructions:
        # imm32 high bytes and Jcc rel32 displacements). Register/ALU
        # latches simply never exceed 32 bits of the width.
        "data_in": Port(64, "in", "Data input"),
        "enable":  Port(1,  "in", "Latch enable"),
        "data_out": Port(64, "out", "Latched data output"),
    }

    def __init__(self, **kw):
        super().__init__(**kw)
        self._value = 0

    def evaluate(self):
        self["data_out"] = self._value

    def rising_edge(self):
        if self["enable"]:
            self._value = self["data_in"]

    def get_state(self):
        return {"value": f"0x{self._value:08x}"}
