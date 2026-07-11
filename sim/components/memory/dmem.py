from sim.component.base import ComponentBase, Port

# Per-cycle state emits a dense window of the LOW region (globals/arrays) plus a
# sparse map of the non-zero words above it (where the software stack lives). A
# large memory (64 KB = 16384 words) would otherwise bloat every snapshot by
# 16384 ints/cycle; the window keeps the common payload small while `size` still
# advertises the true capacity. Reconstruct any word w as:
#     w < len(memory) ? memory[w] : (memory_hi[w] or 0)
STATE_WINDOW = 2048          # dense words reported each cycle (low region)
DEFAULT_MEM_WORDS = 16384    # 64 KB byte-addressed data memory


def memory_snapshot(mem, size, window=STATE_WINDOW):
    """Split a memory list into (dense low window, sparse {word: value} high map).

    The dense list is the first ``min(size, window)`` words (returned in full,
    including zeros, so the UI can random-access it). The sparse map holds only
    the *non-zero* words at or above the window boundary, so deep recursion (a
    tall stack of mostly-distinct words) stays proportional to real usage rather
    than the full capacity.
    """
    w = min(size, window)
    dense = list(mem[:w])
    hi = {i: mem[i] for i in range(w, size) if mem[i]}
    return dense, hi


class DataMemory(ComponentBase):
    """Word-addressed data memory. Combinational read, synchronous write.

    Uses ``addr`` for combinational reads. For writes, ``waddr`` is used
    when ``waddr_valid`` is asserted (the OoO store-commit path drives a
    dedicated write address that may legitimately be 0); otherwise the
    write falls back to ``addr`` (pipeline/single-cycle share one bus).

    Default capacity is 64 KB (16384 32-bit words); the effective index wraps
    at ``(addr>>2) % size``.
    """
    name = "data_memory"
    ui_label = "Data Memory"
    ui_category = "memory"
    ports_spec = {
        "addr":  Port(32, "in",  "Read address (byte)"),
        "waddr": Port(32, "in",  "Write address (byte)"),
        "waddr_valid": Port(1, "in", "1 = use waddr (else fall back to addr)"),
        "wdata": Port(32, "in",  "Write data"),
        "wen":   Port(1,  "in",  "Write enable"),
        "rdata": Port(32, "out", "Read data"),
    }

    def __init__(self, size: int = DEFAULT_MEM_WORDS, **kw):
        super().__init__(**kw)
        self._mem = [0] * size
        self._size = size

    def evaluate(self):
        word_addr = (self["addr"] >> 2) % self._size
        self["rdata"] = self._mem[word_addr]

    def rising_edge(self):
        if self["wen"]:
            addr = self["waddr"] if self["waddr_valid"] else self["addr"]
            word_addr = (addr >> 2) % self._size
            self._mem[word_addr] = self["wdata"]

    def get_state(self):
        dense, hi = memory_snapshot(self._mem, self._size)
        return {
            "addr": f"0x{self['addr']:08x}",
            "rdata": self["rdata"],
            "wdata": self["wdata"],
            "wen": self["wen"],
            # Effective write address this cycle (mirrors rising_edge's
            # waddr/addr fallback) so the UI can attribute writes — e.g. the
            # lab terminal detecting print() stores — without re-deriving the
            # OoO-vs-shared-bus rule.
            "write_addr": int(self["waddr"] if self["waddr_valid"] else self["addr"]),
            "memory": dense,
            "memory_hi": hi,
            "size": self._size,
            "window": min(self._size, STATE_WINDOW),
        }


class MultiPortDataMemory(ComponentBase):
    """N-port data memory for the superscalar pipeline.

    Every lane presents its own ``(addr, wdata, mem_read, mem_write)`` and gets
    its own ``rdata``, so *all* lanes can issue a memory op in the same cycle —
    there is no single-port structural stall. Program order within a fetch group
    is preserved exactly as a single-cycle machine would see it:

      * **Reads** are combinational against the memory as of the start of the
        cycle, with store->load forwarding from *older* (lower-index) lanes in
        the same group: a load in lane i sees a same-group store in lane j<i to
        the same word, but never a store from a younger lane j>i.
      * **Writes** commit in lane order at the clock edge, so if two lanes in
        the group write the same word the younger (higher-index) lane wins.

    This is the multi-issue load/store model: memory-bound code scales with lane
    width and cycle counts stay monotonic (wider is never slower), unlike the
    old single-port mux which squashed + re-fetched every lane after the first
    memory op. Shares ``_mem``/``_size`` and the sparse snapshot with
    :class:`DataMemory` so the harness (``SimResult.memory``) and UI are
    unchanged.
    """
    name = "multiport_data_memory"
    ui_label = "Data Memory (multi-port)"
    ui_category = "memory"

    def __init__(self, num_lanes: int = 2, size: int = DEFAULT_MEM_WORDS, **kw):
        self.num_lanes = num_lanes
        self.ports_spec = {}
        for i in range(num_lanes):
            self.ports_spec[f"addr_{i}"]      = Port(32, "in",  f"Lane {i} byte address")
            self.ports_spec[f"wdata_{i}"]     = Port(32, "in",  f"Lane {i} write data")
            self.ports_spec[f"mem_read_{i}"]  = Port(1,  "in",  f"Lane {i} is a load")
            self.ports_spec[f"mem_write_{i}"] = Port(1,  "in",  f"Lane {i} is a store")
            self.ports_spec[f"rdata_{i}"]     = Port(32, "out", f"Lane {i} read data")
        super().__init__(**kw)
        self._mem = [0] * size
        self._size = size

    def _word(self, byte_addr: int) -> int:
        return (byte_addr >> 2) % self._size

    def evaluate(self):
        for i in range(self.num_lanes):
            w = self._word(self[f"addr_{i}"])
            val = self._mem[w]
            # Store->load forwarding from older lanes (j<i) in this group.
            # Ascending j means the youngest older store to word w wins.
            for j in range(i):
                if self[f"mem_write_{j}"] and self._word(self[f"addr_{j}"]) == w:
                    val = self[f"wdata_{j}"]
            self[f"rdata_{i}"] = val & 0xFFFF_FFFF

    def rising_edge(self):
        # Commit stores in program (lane) order so a younger same-word store wins.
        for i in range(self.num_lanes):
            if self[f"mem_write_{i}"]:
                self._mem[self._word(self[f"addr_{i}"])] = self[f"wdata_{i}"]

    def get_state(self):
        dense, hi = memory_snapshot(self._mem, self._size)
        active = next((i for i in range(self.num_lanes)
                       if self[f"mem_read_{i}"] or self[f"mem_write_{i}"]), -1)
        writes = [int(self[f"addr_{i}"]) for i in range(self.num_lanes)
                  if self[f"mem_write_{i}"]]
        return {
            "addr": f"0x{(self[f'addr_{active}'] if active >= 0 else 0):08x}",
            "rdata": self[f"rdata_{active}"] if active >= 0 else 0,
            "wdata": self[f"wdata_{active}"] if active >= 0 else 0,
            "wen": 1 if writes else 0,
            "write_addr": writes[-1] if writes else 0,
            "active_lanes": [i for i in range(self.num_lanes)
                             if self[f"mem_read_{i}"] or self[f"mem_write_{i}"]],
            "memory": dense,
            "memory_hi": hi,
            "size": self._size,
            "window": min(self._size, STATE_WINDOW),
        }
