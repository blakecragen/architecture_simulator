"""Byte-addressed instruction memory for variable-length ISAs (x86)."""
from sim.component.base import ComponentBase, Port


class ByteInstructionMemory(ComponentBase):
    """
    Byte-addressed instruction memory. Stores program as a byte array.
    Outputs 8 bytes starting at the given address (little-endian packed
    into a 64-bit value) so the decoder can parse variable-length instructions.
    """
    name = "byte_instruction_memory"
    ui_label = "Byte Instr. Memory"
    ui_category = "fetch"
    ports_spec = {
        "addr": Port(32, "in",  "Byte address"),
        "data": Port(64, "out", "8 bytes starting at addr (LE packed)"),
    }

    def __init__(self, program: list[int], **kw):
        super().__init__(**kw)
        self._program = bytes(b & 0xFF for b in program)

    def evaluate(self):
        addr = self["addr"]
        # Read up to 8 bytes starting at addr
        result = 0
        for i in range(8):
            idx = addr + i
            if 0 <= idx < len(self._program):
                result |= self._program[idx] << (i * 8)
            else:
                result |= 0x90 << (i * 8)  # NOP padding
        self["data"] = result

    def get_state(self):
        addr = self["addr"]
        # Show first few bytes at current address for debug
        raw = []
        for i in range(8):
            idx = addr + i
            if 0 <= idx < len(self._program):
                raw.append(f"{self._program[idx]:02X}")
            else:
                raw.append("90")
        return {
            "addr": f"0x{addr:08x}",
            "bytes": " ".join(raw),
            "program_bytes": list(self._program),
            "size": len(self._program),
        }
