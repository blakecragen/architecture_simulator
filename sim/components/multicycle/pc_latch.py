from sim.component.base import ComponentBase, Port


class PCLatch(ComponentBase):
    """
    PC Latch -- same as Latch but get_state() reports a 'pc' field
    for UI badge computation.

    Captures the PC of the instruction currently being processed
    by the multi-cycle controller.
    """
    name = "pc_latch"
    ui_label = "PC Latch"
    ui_category = "fetch"
    ports_spec = {
        "data_in": Port(32, "in", "PC input"),
        "enable":  Port(1,  "in", "Latch enable"),
        "data_out": Port(32, "out", "Latched PC output"),
        "pc4_out":  Port(32, "out", "Latched PC + 4 (for link/return values)"),
    }

    def __init__(self, **kw):
        super().__init__(**kw)
        self._value = 0

    def evaluate(self):
        self["data_out"] = self._value
        self["pc4_out"] = (self._value + 4) & 0xFFFF_FFFF

    def rising_edge(self):
        if self["enable"]:
            self._value = self["data_in"]

    def get_state(self):
        return {
            "pc": f"0x{self._value:08x}",
            "value": f"0x{self._value:08x}",
        }
