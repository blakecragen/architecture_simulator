"""Fall-through address adder: pc_plus_len = pc + instruction length.

x86 instructions are variable-length, so the fall-through (next-sequential)
address depends on the CURRENT instruction's length, produced by the predecode
stage which — because it needs the fetched bytes — runs *after* the fetch unit.
X86Fetch therefore can't compute a correct pc_plus_len in its own evaluate()
(the length wired back to it is still the previous instruction's). This adder
sits downstream of the predecode and threads the correct fall-through as the
pipeline's pc4, so a taken-predicted-but-not-taken branch recovers to the real
next instruction instead of landing mid-instruction.
"""
from sim.component.base import ComponentBase, Port


class PcLenAdder(ComponentBase):
    name = "pc_len_adder"
    ui_label = "PC + len"
    ui_category = "fetch"
    ports_spec = {
        "pc":  Port(32, "in",  "Base PC"),
        "len": Port(4,  "in",  "Instruction length (bytes)"),
        "out": Port(32, "out", "Fall-through address (pc + length)"),
    }

    def evaluate(self):
        length = self["len"] if self["len"] > 0 else 1
        self["out"] = (self["pc"] + length) & 0xFFFF_FFFF

    def get_state(self):
        return {
            "pc": f"0x{self['pc']:08x}",
            "len": self["len"],
            "out": f"0x{self['out']:08x}",
        }
