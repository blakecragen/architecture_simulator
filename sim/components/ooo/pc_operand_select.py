"""PC operand select for Out-of-Order execution.

For PC-relative ALU operations (e.g. RISC-V AUIPC: rd = PC + imm), the ALU's
first operand is the instruction's own PC, not a register value. The OoO
reservation station otherwise resolves src1 from the register file, so without
this select an AUIPC would add its immediate to a register (PC is ignored) and
produce the wrong result.

When ``use_pc`` is set, src1 is driven from ``pc`` and marked ready immediately
(the PC is a constant known at dispatch, with no producing instruction to wait
on). Otherwise the register-file value / RAT readiness+tag pass straight
through.
"""
from sim.component.base import ComponentBase, Port


class PcOperandSelect(ComponentBase):
    name = "pc_operand_select"
    ui_label = "PC Operand Select"
    ui_category = "ooo"
    ports_spec = {
        "use_pc":     Port(1,  "in",  "1 = src1 is the instruction PC"),
        "pc":         Port(32, "in",  "Instruction PC"),
        "reg_val":    Port(32, "in",  "Register-file src1 value"),
        "reg_ready":  Port(1,  "in",  "RAT: src1 has no pending writer"),
        "reg_tag":    Port(5,  "in",  "RAT: src1 ROB tag (if not ready)"),
        "src_val":    Port(32, "out", "Selected src1 value"),
        "src_ready":  Port(1,  "out", "Selected src1 ready"),
        "src_tag":    Port(5,  "out", "Selected src1 tag"),
    }

    def evaluate(self):
        if self["use_pc"]:
            self["src_val"] = self["pc"]
            self["src_ready"] = 1
            self["src_tag"] = 0
        else:
            self["src_val"] = self["reg_val"]
            self["src_ready"] = self["reg_ready"]
            self["src_tag"] = self["reg_tag"]

    def get_state(self):
        return {
            "use_pc": self["use_pc"],
            "src_val": f"0x{self['src_val']:08x}",
            "src_ready": self["src_ready"],
        }
