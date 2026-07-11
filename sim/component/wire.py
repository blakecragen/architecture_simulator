"""
Wiring infrastructure: Wire, CPU, CPUBuilder.

CPUBuilder provides the fluent API shown in presets:
    b = CPUBuilder()
    b.add("fetch", SimpleFetch(...))
    b.wire("fetch.instr_out", "decode.instr_in")
    cpu = b.build()
"""
from __future__ import annotations
from .base import ComponentBase


class Wire:
    """A single connection between an output port and an input port."""
    __slots__ = ("src_comp", "src_port", "dst_comp", "dst_port")

    def __init__(self, src_comp: str, src_port: str, dst_comp: str, dst_port: str):
        self.src_comp = src_comp
        self.src_port = src_port
        self.dst_comp = dst_comp
        self.dst_port = dst_port

    def propagate(self, components: dict[str, ComponentBase]):
        val = components[self.src_comp][self.src_port]
        components[self.dst_comp][self.dst_port] = val

    def __repr__(self):
        return f"{self.src_comp}.{self.src_port} → {self.dst_comp}.{self.dst_port}"


class CPU:
    """
    Assembled CPU: holds components, wires, and evaluation order.
    Created by CPUBuilder.build().
    """

    def __init__(
        self,
        components: dict[str, ComponentBase],
        wires: list[Wire],
        eval_order: list[str],
    ):
        self.components = components
        self.wires = wires
        self.eval_order = eval_order

    def tick(self):
        """Execute one clock cycle."""
        # Phase 1: combinational settle — propagate wires then evaluate,
        # in dependency order.
        for name in self.eval_order:
            for w in self.wires:
                if w.dst_comp == name:
                    w.propagate(self.components)
            self.components[name].evaluate()

        # Phase 2: final wire propagation (ensures outputs like branch.next_pc
        # reach their destinations before the rising edge).
        for w in self.wires:
            w.propagate(self.components)

        # Phase 3: rising edge — sequential updates.
        for name in self.eval_order:
            self.components[name].rising_edge()

    def get_cycle_state(self) -> dict:
        """Return per-component state for the current cycle."""
        return {name: comp.get_state() for name, comp in self.components.items()}


class CPUBuilder:
    """Fluent builder for assembling a CPU from components and wires."""

    def __init__(self):
        self._components: dict[str, ComponentBase] = {}
        self._wires: list[Wire] = []
        self._eval_order: list[str] | None = None

    def add(self, name: str, component: ComponentBase) -> "CPUBuilder":
        self._components[name] = component
        return self

    def wire(self, src: str, dst: str) -> "CPUBuilder":
        sc, sp = src.split(".", 1)
        dc, dp = dst.split(".", 1)
        # Explicit raises (not assert) so wiring typos are caught even under
        # python -O, where assert statements are stripped.
        if sc not in self._components:
            raise ValueError(f"Unknown source component '{sc}' in wire '{src}' -> '{dst}'")
        if dc not in self._components:
            raise ValueError(f"Unknown destination component '{dc}' in wire '{src}' -> '{dst}'")
        if sp not in self._components[sc].ports_spec:
            raise ValueError(f"No port '{sp}' on '{sc}' in wire '{src}' -> '{dst}'")
        if dp not in self._components[dc].ports_spec:
            raise ValueError(f"No port '{dp}' on '{dc}' in wire '{src}' -> '{dst}'")
        self._wires.append(Wire(sc, sp, dc, dp))
        return self

    def set_eval_order(self, order: list[str]) -> "CPUBuilder":
        self._eval_order = order
        return self

    def build(self) -> CPU:
        if self._eval_order is None:
            self._eval_order = list(self._components.keys())
        else:
            # Validate completeness: every component must appear exactly once in
            # the eval order, or it is silently never evaluated/clocked (tick()
            # iterates eval_order for both evaluate() and rising_edge()).
            order_set = set(self._eval_order)
            comp_set = set(self._components)
            if len(self._eval_order) != len(order_set):
                dupes = sorted({n for n in self._eval_order
                                if self._eval_order.count(n) > 1})
                raise ValueError(f"Duplicate components in eval order: {dupes}")
            if order_set != comp_set:
                missing = sorted(comp_set - order_set)
                extra = sorted(order_set - comp_set)
                raise ValueError(
                    f"eval order does not match components "
                    f"(missing: {missing}, unknown: {extra})")
        return CPU(self._components, self._wires, self._eval_order)
