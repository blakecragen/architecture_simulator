from sim.component.base import ComponentBase, Port


class RegisterFileBase(ComponentBase):
    """Port contract for register files."""
    ui_category = "decode"
    ports_spec = {
        "rs1_addr": Port(5,  "in",  "Read address 1"),
        "rs2_addr": Port(5,  "in",  "Read address 2"),
        "rs1_data": Port(32, "out", "Read data 1"),
        "rs2_data": Port(32, "out", "Read data 2"),
        "rs3_addr": Port(5,  "in",  "Read address 3 (e.g. OoO store-data commit read)"),
        "rs3_data": Port(32, "out", "Read data 3"),
        "rd_addr":  Port(5,  "in",  "Write address"),
        "rd_data":  Port(32, "in",  "Write data"),
        "wen":      Port(1,  "in",  "Write enable"),
    }
