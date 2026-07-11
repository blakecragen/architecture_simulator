"""
Generates a topology graph (nodes + edges) from an assembled CPU.
The UI renders this as a live block diagram.
"""
from __future__ import annotations
from .wire import CPU


def generate_topology(cpu: CPU) -> dict:
    nodes = []
    for comp_name, comp in cpu.components.items():
        ports = {}
        for pname, port in comp.ports_spec.items():
            ports[pname] = {
                "width": port.width,
                "direction": port.direction,
                "desc": port.desc,
            }
        nodes.append({
            "id": comp_name,
            "label": comp.ui_label or comp.name or comp_name,
            "category": comp.ui_category,
            "ports": ports,
        })

    edges = []
    for w in cpu.wires:
        src_comp = cpu.components[w.src_comp]
        src_port = src_comp.ports_spec[w.src_port]
        edges.append({
            "from": f"{w.src_comp}.{w.src_port}",
            "to": f"{w.dst_comp}.{w.dst_port}",
            "label": src_port.desc or w.src_port,
        })

    return {"nodes": nodes, "edges": edges}
