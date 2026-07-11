from sim.component.base import ComponentBase, Port


class MemoryUnitBase(ComponentBase):
    """Port contract for memory units."""
    ui_category = "memory"
    ports_spec = {
        "addr":  Port(32, "in",  "Address (byte-addressed)"),
        "rdata": Port(32, "out", "Read data"),
    }
