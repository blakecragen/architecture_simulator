from sim.component.base import ComponentBase, Port, to_signed32
from sim.core.signals import BranchCond


class BranchResolutionUnit(ComponentBase):
    """
    Evaluates branch conditions and computes next PC.

    Ordering conditions (LT/GE/LE/GT) are interpreted per ``compare_mode``:

    * ``"slt"`` (RISC-V): the decoder feeds a set-less-than result, so the
      comparison answer is bit 0 of ``alu_result``.
    * ``"sub"`` (ARM / x86): the branch reads a subtraction (CMP/SUBS) result
      from the flags register, so the answer comes from the *sign* of
      ``alu_result`` (plus the zero flag for LE/GT).
    """
    name = "branch_resolution"
    ui_label = "Branch Resolution"
    ui_category = "control"
    ports_spec = {
        "pc":              Port(32, "in",  "Current PC"),
        "pc4":             Port(32, "in",  "PC + 4"),
        "imm":             Port(32, "in",  "Branch/jump offset"),
        "rs1_data":        Port(32, "in",  "RS1 data (for JALR)"),
        "branch":          Port(1,  "in",  "Is branch instruction"),
        "branch_cond":     Port(3,  "in",  "Branch condition code"),
        "jal":             Port(1,  "in",  "JAL instruction"),
        "jalr":            Port(1,  "in",  "JALR instruction"),
        "alu_zero":        Port(1,  "in",  "ALU zero flag"),
        "alu_result":      Port(32, "in",  "ALU result"),
        "predicted_taken": Port(1,  "in",  "Prediction from branch predictor"),
        "rob_empty":       Port(1,  "in",  "OoO: ROB is drained (operands/flags settled)"),
        "next_pc":         Port(32, "out", "Next program counter"),
        "branch_taken":    Port(1,  "out", "Branch was taken"),
        "mispredict":      Port(1,  "out", "Misprediction detected"),
        "is_control":      Port(1,  "out", "Is control-flow instruction"),
        "stall":           Port(1,  "out", "OoO: hold fetch until operands/flags settle"),
    }

    def __init__(self, compare_mode: str = "slt", serialized: bool = False, **kw):
        super().__init__(**kw)
        assert compare_mode in ("slt", "sub")
        self.compare_mode = compare_mode
        # OoO resolves branches combinationally at decode against out-of-order
        # state, which is racy. When serialized, a conditional branch is held
        # (and fetch stalled) until the ROB drains so its comparison operands /
        # condition flags are settled in program order.
        self.serialized = serialized

    def _ordering(self, cond):
        """Resolve an ordering condition (LT/GE/LE/GT) to taken/not-taken."""
        zero = bool(self["alu_zero"])
        if self.compare_mode == "slt":
            # RISC-V: alu_result is a 0/1 set-less-than value; bit 0 == (a < b).
            lt = bool(self["alu_result"] & 1)
        else:
            # ARM/x86: alu_result is (a - b); a < b  <=>  signed(a - b) < 0.
            lt = to_signed32(self["alu_result"]) < 0
        if cond == BranchCond.LT:
            return 1 if lt else 0
        if cond == BranchCond.GE:
            return 0 if lt else 1
        if cond == BranchCond.LE:
            return 1 if (lt or zero) else 0
        if cond == BranchCond.GT:
            return 0 if (lt or zero) else 1
        return 0

    def evaluate(self):
        pc  = self["pc"]
        imm = self["imm"]

        # OoO serialization: hold a conditional branch (and stall fetch) until
        # the ROB has drained, so its comparison inputs are settled in program
        # order.  (JALR is not serialized here: it writes a link register and
        # therefore dispatches to the ROB, so stalling fetch on it would
        # re-dispatch every cycle / never see an empty ROB — register-indirect
        # jump resolution in OoO is a separate concern.)
        if self.serialized and self["branch"] and not self["rob_empty"]:
            self["stall"] = 1
            self["branch_taken"] = 0
            self["next_pc"] = self["pc4"]
            self["mispredict"] = 0
            self["is_control"] = 1
            return
        self["stall"] = 0

        # Evaluate branch condition
        taken = 0
        cond = self["branch_cond"]
        if cond == BranchCond.EQ:
            taken = 1 if self["alu_zero"] else 0
        elif cond == BranchCond.NEQ:
            taken = 0 if self["alu_zero"] else 1
        elif cond in (BranchCond.LT, BranchCond.GE, BranchCond.LE, BranchCond.GT):
            taken = self._ordering(cond)

        # Compute next PC
        if self["jal"]:
            self["next_pc"] = (pc + imm) & 0xFFFF_FFFF
            self["branch_taken"] = 1
        elif self["jalr"]:
            self["next_pc"] = (self["rs1_data"] + imm) & 0xFFFF_FFFE
            self["branch_taken"] = 1
        elif self["branch"] and taken:
            self["next_pc"] = (pc + imm) & 0xFFFF_FFFF
            self["branch_taken"] = 1
        else:
            self["next_pc"] = self["pc4"]
            self["branch_taken"] = 0

        # Misprediction detection
        is_control = self["branch"] or self["jal"] or self["jalr"]
        self["is_control"] = 1 if is_control else 0
        if is_control:
            self["mispredict"] = 1 if (self["branch_taken"] != self["predicted_taken"]) else 0
        else:
            self["mispredict"] = 0

    def get_state(self):
        return {
            "next_pc": f"0x{self['next_pc']:08x}",
            "branch_taken": self["branch_taken"],
            "mispredict": self["mispredict"],
        }
