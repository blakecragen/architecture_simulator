"""
RISC-V configurable cycle-cost preset ("Configurable" model).

Same combinational datapath as single-cycle, but each instruction is held for a
per-class number of cycles (``cycle_costs`` = {alu, load, store, branch}) and
commits only on its final cycle. All-1s reproduces single-cycle exactly; the
FetDecExe profile {alu:3, load:4, store:4, branch:3} reproduces the multicycle
machine. Results always match the single-cycle oracle — only the cycle count
(and thus the time = cycles x clock-period readout) changes.
"""
from .single_cycle import build as _single_cycle_build
from sim.components.multicycle.budget_controller import DEFAULT_COSTS


def build(program: list[int], branch_predictor=None, dmem=None, alu=None,
          cycle_costs=None):
    if cycle_costs is None:
        cycle_costs = dict(DEFAULT_COSTS)
    return _single_cycle_build(program, branch_predictor=branch_predictor,
                               dmem=dmem, alu=alu, cycle_costs=cycle_costs)
