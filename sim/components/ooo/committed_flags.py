"""
Committed condition flags for Out-of-Order execution (ARM / x86).

ARM (SUBS/CMP) and x86 (CMP / arithmetic) conditional branches read condition
flags produced by an earlier flag-setting instruction.  In the out-of-order
core the live ALU output cannot be trusted for this — it reflects whatever the
reservation station happened to dispatch this cycle, not the program-order
flag-setter the branch depends on.

This component latches the flags of a flag-setting instruction when it
*commits* from the ROB (i.e. in program order).  A conditional branch is held
(fetch stalled) until the ROB drains, so by the time it resolves the most
recent flag-setter before it has committed and these latched flags are settled.

The latched ``result`` is the subtraction result (a - b) produced by the
flag-setter; the zero flag is derived from it.  The BranchResolutionUnit in
``compare_mode="sub"`` interprets result/zero exactly as it does for the
in-order models' FlagsRegister.
"""
from sim.component.base import ComponentBase, Port, mask32


class CommittedFlags(ComponentBase):
    name = "committed_flags"
    ui_label = "Committed Flags"
    ui_category = "ooo"
    ports_spec = {
        "commit_write_flags": Port(1,  "in",  "Committing instruction sets flags"),
        "commit_value":       Port(32, "in",  "Committed flag-setter result (a - b)"),
        "zero_out":           Port(1,  "out", "Latched zero flag"),
        "result_out":         Port(32, "out", "Latched result (a - b)"),
    }

    def __init__(self, **kw):
        super().__init__(**kw)
        self._zero = 0
        self._result = 0

    def evaluate(self):
        # Expose the most recently committed flag-setter's flags.
        self["zero_out"] = self._zero
        self["result_out"] = self._result

    def rising_edge(self):
        if self["commit_write_flags"]:
            value = mask32(self["commit_value"])
            self._result = value
            self._zero = 1 if value == 0 else 0

    def get_state(self):
        return {
            "zero": self._zero,
            "result": f"0x{mask32(self._result):08x}",
        }
