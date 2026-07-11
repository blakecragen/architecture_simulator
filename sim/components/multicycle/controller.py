from sim.component.base import ComponentBase, Port


# Phase constants
FETCH   = 0
DECODE  = 1
EXECUTE = 2
MEMORY  = 3

_PHASE_NAMES = {FETCH: "FETCH", DECODE: "DECODE", EXECUTE: "EXECUTE", MEMORY: "MEMORY"}


class MultiCycleController(ComponentBase):
    """
    Multi-cycle FSM controller.

    Tracks the current phase (FETCH -> DECODE -> EXECUTE -> [MEMORY] -> FETCH)
    and generates enable signals to gate latches and component write-enables.

    Phase transitions (on rising_edge):
      FETCH:   -> DECODE
      DECODE:  -> EXECUTE  (latches mem_read/mem_write/reg_write from decoder)
      EXECUTE: -> MEMORY   if load or store
                -> FETCH   otherwise (reg_write_en asserted for ALU ops)
      MEMORY:  -> FETCH    (mem_read_en/mem_write_en/reg_write_en asserted)

    Output enables (computed in evaluate):
      ir_latch:      1 during FETCH (latch instruction)
      ab_latch:      1 during DECODE (latch register values)
      alu_out_latch: 1 during EXECUTE (latch ALU result)
      fetch_stall:   0 during FETCH, 1 otherwise (hold PC)
      reg_write_en:  1 when regfile write should happen
      mem_read_en:   1 when data memory read should happen
      mem_write_en:  1 when data memory write should happen
    """
    name = "multicycle_controller"
    ui_label = "MC Controller"
    ui_category = "control"
    ports_spec = {
        # Inputs from decoder (sampled during DECODE)
        "dec_mem_read":  Port(1, "in", "Decoder mem_read signal"),
        "dec_mem_write": Port(1, "in", "Decoder mem_write signal"),
        "dec_reg_write": Port(1, "in", "Decoder reg_write signal"),
        # Outputs
        "phase":            Port(3, "out", "Current phase (0-3)"),
        "fetch_stall":      Port(1, "out", "Stall fetch unit"),
        "ir_latch":         Port(1, "out", "Enable IR latch"),
        "ab_latch":         Port(1, "out", "Enable reg A/B latches"),
        "alu_out_latch":    Port(1, "out", "Enable ALU output latch"),
        "reg_write_en":     Port(1, "out", "Enable register write"),
        "mem_read_en":      Port(1, "out", "Enable memory read"),
        "mem_write_en":     Port(1, "out", "Enable memory write"),
        "branch_resolve_en": Port(1, "out", "Enable branch resolution (EXECUTE only)"),
    }

    def __init__(self, **kw):
        super().__init__(**kw)
        self._phase = FETCH
        self._mem_read = 0
        self._mem_write = 0
        self._reg_write = 0
        self._instr_pc = 0

    def evaluate(self):
        phase = self._phase
        self["phase"] = phase

        # Default all enables off
        self["ir_latch"] = 0
        self["ab_latch"] = 0
        self["alu_out_latch"] = 0
        self["fetch_stall"] = 1
        self["reg_write_en"] = 0
        self["mem_read_en"] = 0
        self["mem_write_en"] = 0
        self["branch_resolve_en"] = 0

        if phase == FETCH:
            self["ir_latch"] = 1
            self["fetch_stall"] = 0  # allow PC to advance
        elif phase == DECODE:
            self["ab_latch"] = 1
            self["fetch_stall"] = 1
        elif phase == EXECUTE:
            self["alu_out_latch"] = 1
            self["fetch_stall"] = 1
            self["branch_resolve_en"] = 1  # allow branch resolution
            # For ALU ops (no memory), writeback happens this cycle
            if not self._mem_read and not self._mem_write:
                self["reg_write_en"] = self._reg_write
        elif phase == MEMORY:
            self["fetch_stall"] = 1
            if self._mem_read:
                self["mem_read_en"] = 1
            if self._mem_write:
                self["mem_write_en"] = 1
            # Writeback for ANY memory instruction that also writes a register:
            # loads (rd <- mem) and stores with a register side effect
            # (x86 PUSH decrements ESP: mem_write=1 AND reg_write=1).
            self["reg_write_en"] = self._reg_write

    def rising_edge(self):
        phase = self._phase

        if phase == FETCH:
            self._phase = DECODE
        elif phase == DECODE:
            # Latch decoder control signals for phase transitions
            self._mem_read = self["dec_mem_read"]
            self._mem_write = self["dec_mem_write"]
            self._reg_write = self["dec_reg_write"]
            self._phase = EXECUTE
        elif phase == EXECUTE:
            if self._mem_read or self._mem_write:
                self._phase = MEMORY
            else:
                self._phase = FETCH
        elif phase == MEMORY:
            self._phase = FETCH

    def get_state(self):
        p = self["phase"]
        return {
            "phase": p,
            "phase_name": _PHASE_NAMES.get(p, "?"),
        }
