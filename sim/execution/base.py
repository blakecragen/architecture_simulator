from abc import ABC, abstractmethod
from amaranth import Elaboratable


class ExecutionModelBase(ABC):
    """
    Abstract execution model interface.

    To add a new execution model:
      1. Create sim/execution/<name>.py
      2. Subclass ExecutionModelBase
      3. Implement create_cpu()
      4. Register in app/flask_app.py MODEL_REGISTRY

    The CPU returned by create_cpu() must expose:
      .pc         — current program counter (Signal 32)
      .instr      — current instruction word (Signal 32)
      .alu_out    — ALU result this cycle (Signal 32)
      .stall      — pipeline stall flag (Signal 1, always 0 for single-cycle)
      ._regfile   — RegisterFile instance (for simulation readback)
      ._decoder   — Decoder instance (for simulation readback)
    """

    name: str = "unknown"

    @abstractmethod
    def create_cpu(self, isa, program: list) -> Elaboratable:
        """Instantiate the full CPU with this execution model and given ISA."""
