"""Wide instruction memory — fetches N instruction words in parallel."""
from sim.component.base import ComponentBase, Port


class WideInstructionMemory(ComponentBase):
    """
    N-wide instruction memory. Given a base address, outputs N consecutive
    instruction words on data_0 .. data_{N-1}.

    Used by the superscalar preset to feed N decoder lanes.
    """
    name = "wide_instruction_memory"
    ui_label = "Wide Instr. Memory"
    ui_category = "fetch"

    def __init__(self, program: list[int], num_lanes: int = 2, **kw):
        self.num_lanes = num_lanes
        self.ports_spec = {
            "addr": Port(32, "in", "Base byte address"),
        }
        for i in range(num_lanes):
            self.ports_spec[f"data_{i}"] = Port(32, "out", f"Instruction word lane {i}")
        super().__init__(**kw)
        self._program = [w & 0xFFFF_FFFF for w in program]
        self._nop = 0x00000013  # ADDI x0, x0, 0

    def evaluate(self):
        base_word = self["addr"] >> 2
        for i in range(self.num_lanes):
            idx = base_word + i
            if 0 <= idx < len(self._program):
                self[f"data_{i}"] = self._program[idx]
            else:
                self[f"data_{i}"] = self._nop

    def get_state(self):
        state = {"addr": f"0x{self['addr']:08x}"}
        for i in range(self.num_lanes):
            state[f"data_{i}"] = f"0x{self[f'data_{i}']:08x}"
        return state
