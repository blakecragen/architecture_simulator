"""
CPU factory — composes an ISA with an execution model.

Usage:
    from sim.cpu import build_cpu
    from sim.isa.riscv import RISCV
    from sim.execution.single_cycle import SingleCycle

    cpu = build_cpu(isa=RISCV(), model=SingleCycle(), program=[0x00000013, ...])

To hot-swap:
    cpu = build_cpu(isa=ARM(),   model=SingleCycle(), program=[...])
    cpu = build_cpu(isa=RISCV(), model=Pipeline(),    program=[...])
"""
from __future__ import annotations

from .isa.base import ISABase
from .execution.base import ExecutionModelBase


def build_cpu(isa: ISABase, model: ExecutionModelBase, program: list):
    """
    Return an Amaranth Elaboratable CPU ready for simulation or synthesis.

    isa     : plug-in ISA   (RISCV() | ARM() | X86())
    model   : plug-in model (SingleCycle() | Pipeline() | OoO())
    program : list of 32-bit instruction words
    """
    return model.create_cpu(isa, program)
