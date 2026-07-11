from sim.component.base import ComponentBase, Port


class InstructionMemory(ComponentBase):
    """Read-only instruction memory. Loaded from a program list at construction."""
    name = "instruction_memory"
    ui_label = "Instruction Memory"
    ui_category = "fetch"
    ports_spec = {
        "addr": Port(32, "in",  "Byte address"),
        "data": Port(32, "out", "Instruction word"),
    }

    def __init__(self, program: list[int], **kw):
        super().__init__(**kw)
        self._program = [w & 0xFFFF_FFFF for w in program]

    def evaluate(self):
        word_idx = self["addr"] >> 2
        if 0 <= word_idx < len(self._program):
            self["data"] = self._program[word_idx]
        else:
            self["data"] = 0x0000_0013  # NOP: ADDI x0, x0, 0

    def get_state(self):
        return {
            "addr": f"0x{self['addr']:08x}",
            "data": f"0x{self['data']:08x}",
            "program": list(self._program),
            "size": len(self._program),
        }
