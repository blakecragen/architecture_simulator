"""
Component framework foundation.

Every CPU component subclasses ComponentBase and declares its I/O interface
as named Ports. The CPUBuilder wires components by port name. Any component
with compatible ports is swappable.
"""
from __future__ import annotations


def mask32(value: int) -> int:
    return value & 0xFFFF_FFFF


def sign_extend(value: int, bits: int) -> int:
    """Sign-extend a value from *bits* width to a Python int."""
    if value & (1 << (bits - 1)):
        return value - (1 << bits)
    return value


def to_signed32(value: int) -> int:
    """Interpret a 32-bit unsigned value as a signed Python int."""
    value &= 0xFFFF_FFFF
    return value - 0x1_0000_0000 if value >= 0x8000_0000 else value


class Port:
    """Declares a named I/O point on a component."""
    __slots__ = ("width", "direction", "desc")

    def __init__(self, width: int = 32, direction: str = "in", desc: str = ""):
        self.width = width
        self.direction = direction
        self.desc = desc

    def __repr__(self):
        return f"Port(w={self.width}, {self.direction})"


class ComponentBase:
    """
    Base class for all CPU components.

    Subclasses declare ``ports_spec`` (class-level dict of {name: Port}).
    At runtime, port values are stored in ``_ports`` and accessed via
    ``self["port_name"]``.

    Override ``evaluate()`` for combinational logic and ``rising_edge()``
    for sequential (clocked) updates.
    """
    name: str = ""
    ui_label: str = ""
    ui_category: str = ""
    ports_spec: dict[str, Port] = {}

    def __init__(self, ui_label: str | None = None):
        if ui_label:
            self.ui_label = ui_label
        self._ports: dict[str, int] = {p: 0 for p in self.ports_spec}

    # ── port access ──────────────────────────────────────────────

    def __getitem__(self, port_name: str) -> int:
        return self._ports[port_name]

    def __setitem__(self, port_name: str, value: int):
        port = self.ports_spec[port_name]
        self._ports[port_name] = value & ((1 << port.width) - 1)

    # ── lifecycle hooks (override in subclass) ───────────────────

    def evaluate(self):
        """Compute output ports from input ports (combinational logic)."""

    def rising_edge(self):
        """Update sequential state on the clock edge."""

    # ── state for UI / runner ────────────────────────────────────

    def get_state(self) -> dict:
        """Return component state for the current cycle (serialisable)."""
        return dict(self._ports)

    def reset(self):
        """Reset all port values to zero."""
        for p in self._ports:
            self._ports[p] = 0
