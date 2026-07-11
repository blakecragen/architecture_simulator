"""
Branch flag-source selector for Out-of-Order execution (ARM).

ARM has two flavours of conditional branch:

  * ``B.cond`` reads condition flags produced by an *earlier, separate*
    CMP/SUBS — the operands are not in the branch instruction, so the
    comparison must come from the committed condition flags.
  * ``CBNZ`` / ``CBZ`` compare one of their *own* register operands against
    zero — these are self-contained and resolve like a RISC-V branch, from a
    dedicated in-order comparator over the (settled) register file.

This 2:1 mux picks the comparison the branch unit should see.  ``select`` is
the decoder's ``sets_flags`` bit:

  * ``select=1`` (CBNZ/CBZ — the branch computes its own comparison): pass the
    comparator inputs (``a_*``) through.
  * ``select=0`` (B.cond — reads prior flags): pass the committed flags
    (``b_*``) through.
"""
from sim.component.base import ComponentBase, Port


class BranchFlagMux(ComponentBase):
    name = "branch_flag_mux"
    ui_label = "Branch Flag Mux"
    ui_category = "ooo"
    ports_spec = {
        "select":     Port(1,  "in",  "1 = self-comparing branch (use comparator), 0 = use committed flags"),
        "a_zero":     Port(1,  "in",  "Comparator zero flag (CBNZ/CBZ)"),
        "a_result":   Port(32, "in",  "Comparator result (CBNZ/CBZ)"),
        "b_zero":     Port(1,  "in",  "Committed zero flag (B.cond)"),
        "b_result":   Port(32, "in",  "Committed result (B.cond)"),
        "zero_out":   Port(1,  "out", "Selected zero flag"),
        "result_out": Port(32, "out", "Selected result"),
    }

    def evaluate(self):
        if self["select"]:
            self["zero_out"] = self["a_zero"]
            self["result_out"] = self["a_result"]
        else:
            self["zero_out"] = self["b_zero"]
            self["result_out"] = self["b_result"]

    def get_state(self):
        return {
            "select": self["select"],
            "zero": self["zero_out"],
            "result": f"0x{self['result_out']:08x}",
        }
