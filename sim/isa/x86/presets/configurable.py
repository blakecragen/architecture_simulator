"""x86-32 configurable cycle-cost preset ("Configurable" model).

Same combinational datapath as x86 single-cycle, but each instruction is held
for a per-class cycle budget (``cycle_costs`` = {alu, load, store, branch}) and
commits only on its final cycle. All-1s == single-cycle; results always match
the single-cycle oracle. See sim/isa/x86/presets/single_cycle.py.
"""
from .single_cycle import build as _single_cycle_build
from sim.components.multicycle.budget_controller import DEFAULT_COSTS


def build(program: list[int], branch_predictor=None, dmem=None, alu=None,
          cycle_costs=None):
    if cycle_costs is None:
        cycle_costs = dict(DEFAULT_COSTS)
    return _single_cycle_build(program, branch_predictor=branch_predictor,
                               dmem=dmem, alu=alu, cycle_costs=cycle_costs)
