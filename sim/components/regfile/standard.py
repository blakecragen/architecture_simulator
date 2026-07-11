from .base import RegisterFileBase


class StandardRegisterFile(RegisterFileBase):
    """
    Parameterised register file.
    RISC-V: num_regs=32, zero_reg=True
    ARM:    num_regs=31, zero_reg=False
    x86:    num_regs=16, zero_reg=False
    """
    name = "standard_regfile"
    ui_label = "Register File"

    def __init__(self, num_regs: int = 32, zero_reg: bool = True,
                 zero_reg_index: int = 0, write_through: bool = False, **kw):
        super().__init__(**kw)
        self.num_regs = num_regs
        self.zero_reg = zero_reg
        self.zero_reg_index = zero_reg_index
        self.write_through = write_through
        self.regs = [0] * num_regs

    def _read(self, addr: int) -> int:
        """Read a register, honouring the zero register and (when enabled)
        same-cycle write-through forwarding."""
        a = addr % self.num_regs
        if self.zero_reg and a == self.zero_reg_index:
            return 0
        if self.write_through and self["wen"]:
            rd = self["rd_addr"] % self.num_regs
            if a == rd and not (self.zero_reg and rd == self.zero_reg_index):
                return self["rd_data"]
        return self.regs[a]

    def evaluate(self):
        self["rs1_data"] = self._read(self["rs1_addr"])
        self["rs2_data"] = self._read(self["rs2_addr"])
        self["rs3_data"] = self._read(self["rs3_addr"])

    def rising_edge(self):
        if self["wen"]:
            rd = self["rd_addr"] % self.num_regs
            if not (self.zero_reg and rd == self.zero_reg_index):
                self.regs[rd] = self["rd_data"]

    def get_state(self):
        return {
            "rs1_data": self["rs1_data"],
            "rs2_data": self["rs2_data"],
            "registers": list(self.regs),
        }
