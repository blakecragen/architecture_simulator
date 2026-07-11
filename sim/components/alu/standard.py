from sim.component.base import to_signed32
from sim.core.signals import AluOp, ALU_OP_NAMES
from .base import ALUBase


class StandardALU(ALUBase):
    """32-bit ALU: ADD/SUB/AND/OR/XOR/SLT/SLTU/shifts/PASS."""
    name = "standard_alu"
    ui_label = "Standard ALU"

    def evaluate(self):
        a = self["a"]
        b = self["b"]
        op = self["op"]
        shamt = b & 0x1F

        if op == AluOp.ADD:
            r = a + b
        elif op == AluOp.SUB:
            r = a - b
        elif op == AluOp.AND:
            r = a & b
        elif op == AluOp.OR:
            r = a | b
        elif op == AluOp.XOR:
            r = a ^ b
        elif op == AluOp.SLT:
            r = 1 if to_signed32(a) < to_signed32(b) else 0
        elif op == AluOp.SLTU:
            r = 1 if a < b else 0
        elif op == AluOp.SLL:
            r = a << shamt
        elif op == AluOp.SRL:
            r = a >> shamt
        elif op == AluOp.SRA:
            r = (to_signed32(a) >> shamt) & 0xFFFF_FFFF
        elif op == AluOp.PASS:
            r = b
        else:
            r = 0

        self["result"] = r & 0xFFFF_FFFF
        self["zero"] = 1 if (r & 0xFFFF_FFFF) == 0 else 0

    def get_state(self):
        return {
            "a": self["a"],
            "b": self["b"],
            "op": ALU_OP_NAMES.get(self["op"], str(self["op"])),
            "result": self["result"],
            "zero": self["zero"],
        }
