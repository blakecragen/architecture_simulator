"""
Reservation Station for Out-of-Order execution.

4-entry station that holds instructions waiting for operands.
Each entry snoops the CDB for tag matches to capture forwarded values.

evaluate()     -- combinational: pick the oldest entry with both sources
                  ready and expose it on the exec_* output ports.
rising_edge()  -- sequential: insert new entries, snoop CDB to resolve
                  pending tags, clear issued / flushed entries.
"""
from sim.component.base import ComponentBase, Port, mask32
from sim.components.ooo.rob import ROB_SIZE


RS_SIZE = 4
TAG_MASK = (1 << 5) - 1   # 5-bit tag
OP_MASK = (1 << 4) - 1    # 4-bit ALU op


def _empty_entry() -> dict:
    return {
        "valid": 0,
        "op": 0,
        "src1_ready": 0,
        "src1_tag": 0,
        "src1_val": 0,
        "src2_ready": 0,
        "src2_tag": 0,
        "src2_val": 0,
        "rob_tag": 0,
        "imm": 0,
        "alu_src": 0,
        "is_load": 0,
        "age": 0,  # insertion order for oldest-first selection
    }


class ReservationStation(ComponentBase):
    """
    4-entry reservation station with CDB snooping.

    On issue, an entry is allocated with source operand tags or values.
    Each cycle, the CDB broadcast is checked and any matching tags are
    replaced with the broadcast value.  The oldest entry where both
    sources are ready is selected for execution.
    """
    name = "reservation_station"
    ui_label = "Reservation Station"
    ui_category = "ooo"
    ports_spec = {
        # Issue (from RAT / dispatch) ─────────────────────────
        "issue_en":        Port(1,  "in",  "Allocate new RS entry"),
        "issue_op":        Port(4,  "in",  "ALU operation code"),
        "issue_src1_ready":Port(1,  "in",  "Source 1 value is ready"),
        "issue_src1_tag":  Port(5,  "in",  "Source 1 ROB tag (if not ready)"),
        "issue_src1_val":  Port(32, "in",  "Source 1 value (if ready)"),
        "issue_src2_ready":Port(1,  "in",  "Source 2 value is ready"),
        "issue_src2_tag":  Port(5,  "in",  "Source 2 ROB tag (if not ready)"),
        "issue_src2_val":  Port(32, "in",  "Source 2 value (if ready)"),
        "issue_rob_tag":   Port(5,  "in",  "Destination ROB tag"),
        "issue_imm":       Port(32, "in",  "Immediate value"),
        "issue_alu_src":   Port(1,  "in",  "1 = use imm as src2 for ALU"),
        "issue_is_load":   Port(1,  "in",  "Instruction is a load"),
        # CDB snoop ───────────────────────────────────────────
        "cdb_en":          Port(1,  "in",  "CDB broadcast valid"),
        "cdb_tag":         Port(5,  "in",  "CDB ROB tag"),
        "cdb_value":       Port(32, "in",  "CDB result value"),
        # Store->load ordering (from ROB) ─────────────────────
        "store_mask":      Port(32, "in",  "ROB slots holding uncommitted stores"),
        "rob_head":        Port(5,  "in",  "ROB head index (oldest entry)"),
        # Execute output (oldest ready entry) ─────────────────
        "exec_valid":      Port(1,  "out", "A ready entry is available"),
        "exec_op":         Port(4,  "out", "ALU op of selected entry"),
        "exec_src1":       Port(32, "out", "Source 1 value"),
        "exec_src2":       Port(32, "out", "Source 2 value (or imm)"),
        "exec_rob_tag":    Port(5,  "out", "ROB tag of selected entry"),
        "exec_is_load":    Port(1,  "out", "Selected entry is a load"),
        # Status ──────────────────────────────────────────────
        "full":            Port(1,  "out", "All entries occupied"),
        "flush":           Port(1,  "in",  "Pipeline flush signal"),
    }

    def __init__(self, **kw):
        super().__init__(**kw)
        self._entries = [_empty_entry() for _ in range(RS_SIZE)]
        self._age_counter = 0  # monotonically increasing issue stamp
        self._selected_idx: int | None = None  # index picked by evaluate

    # ── helpers ────────────────────────────────────────────────

    def _is_full(self) -> bool:
        return all(e["valid"] for e in self._entries)

    def _free_slot(self) -> int | None:
        """Return the index of the first free slot, or None."""
        for i, e in enumerate(self._entries):
            if not e["valid"]:
                return i
        return None

    def _entry_ready(self, e: dict) -> bool:
        """Both operand sources must be resolved."""
        return bool(e["valid"] and e["src1_ready"] and e["src2_ready"])

    def _older_store_pending(self, e: dict) -> bool:
        """True iff the ROB holds an uncommitted store OLDER than this entry.

        Loads must wait for older stores to commit (stores write data memory
        at ROB commit; there is no store->load forwarding), otherwise the load
        reads stale memory. Age is position relative to the ROB head in the
        circular buffer. Younger stores never block a load, so the older store
        always reaches the head and commits — no deadlock.
        """
        mask = self["store_mask"]
        if not mask:
            return False
        head = self["rob_head"] % ROB_SIZE
        load_age = (e["rob_tag"] - head) % ROB_SIZE
        for slot in range(ROB_SIZE):
            if (mask >> slot) & 1 and (slot - head) % ROB_SIZE < load_age:
                return True
        return False

    # ── combinational ─────────────────────────────────────────

    def evaluate(self):
        # Defaults
        self["exec_valid"] = 0
        self["exec_op"] = 0
        self["exec_src1"] = 0
        self["exec_src2"] = 0
        self["exec_rob_tag"] = 0
        self["exec_is_load"] = 0
        self["full"] = 1 if self._is_full() else 0

        # Select the oldest ready entry (loads additionally wait until no
        # older store is pending in the ROB — see _older_store_pending).
        best_idx: int | None = None
        best_age: int = -1
        for i, e in enumerate(self._entries):
            if self._entry_ready(e):
                if e["is_load"] and self._older_store_pending(e):
                    continue
                # Oldest = smallest age that is still valid and ready
                if best_idx is None or e["age"] < best_age:
                    best_idx = i
                    best_age = e["age"]

        self._selected_idx = best_idx

        if best_idx is not None:
            e = self._entries[best_idx]
            self["exec_valid"] = 1
            self["exec_op"] = e["op"] & OP_MASK
            self["exec_src1"] = mask32(e["src1_val"])
            # If alu_src == 1, the ALU uses the immediate as src2
            if e["alu_src"]:
                self["exec_src2"] = mask32(e["imm"])
            else:
                self["exec_src2"] = mask32(e["src2_val"])
            self["exec_rob_tag"] = e["rob_tag"] & TAG_MASK
            self["exec_is_load"] = e["is_load"] & 1

    # ── sequential ────────────────────────────────────────────

    def rising_edge(self):
        # 1. Flush: invalidate everything
        if self["flush"]:
            for i in range(RS_SIZE):
                self._entries[i] = _empty_entry()
            self._age_counter = 0
            self._selected_idx = None
            return

        # 2. Remove the entry that was selected for execution this cycle
        if self._selected_idx is not None and self["exec_valid"]:
            self._entries[self._selected_idx] = _empty_entry()
            self._selected_idx = None

        # 3. CDB snoop: update any waiting source whose tag matches
        if self["cdb_en"]:
            cdb_tag = self["cdb_tag"] & TAG_MASK
            cdb_val = mask32(self["cdb_value"])
            for e in self._entries:
                if not e["valid"]:
                    continue
                if not e["src1_ready"] and (e["src1_tag"] & TAG_MASK) == cdb_tag:
                    e["src1_ready"] = 1
                    e["src1_val"] = cdb_val
                if not e["src2_ready"] and (e["src2_tag"] & TAG_MASK) == cdb_tag:
                    e["src2_ready"] = 1
                    e["src2_val"] = cdb_val

        # 4. Issue: insert new entry into the first free slot
        if self["issue_en"] and not self._is_full():
            slot = self._free_slot()
            if slot is not None:
                e = self._entries[slot]
                e["valid"] = 1
                e["op"] = self["issue_op"] & OP_MASK
                e["src1_ready"] = self["issue_src1_ready"] & 1
                e["src1_tag"] = self["issue_src1_tag"] & TAG_MASK
                e["src1_val"] = mask32(self["issue_src1_val"])
                e["src2_ready"] = self["issue_src2_ready"] & 1
                e["src2_tag"] = self["issue_src2_tag"] & TAG_MASK
                e["src2_val"] = mask32(self["issue_src2_val"])
                e["rob_tag"] = self["issue_rob_tag"] & TAG_MASK
                e["imm"] = mask32(self["issue_imm"])
                e["alu_src"] = self["issue_alu_src"] & 1
                e["is_load"] = self["issue_is_load"] & 1
                e["age"] = self._age_counter
                self._age_counter += 1

                # Inline CDB snoop for the newly issued entry: if the
                # CDB broadcast this cycle matches a pending source,
                # capture it immediately so it can fire next cycle.
                if self["cdb_en"]:
                    cdb_tag = self["cdb_tag"] & TAG_MASK
                    cdb_val = mask32(self["cdb_value"])
                    if not e["src1_ready"] and (e["src1_tag"] & TAG_MASK) == cdb_tag:
                        e["src1_ready"] = 1
                        e["src1_val"] = cdb_val
                    if not e["src2_ready"] and (e["src2_tag"] & TAG_MASK) == cdb_tag:
                        e["src2_ready"] = 1
                        e["src2_val"] = cdb_val

    # ── UI state ──────────────────────────────────────────────

    def get_state(self) -> dict:
        entries = []
        for i in range(RS_SIZE):
            e = self._entries[i]
            entries.append({
                "index": i,
                "valid": e["valid"],
                "op": e["op"],
                "src1_ready": e["src1_ready"],
                "src1_tag": e["src1_tag"],
                "src1_val": f"0x{mask32(e['src1_val']):08x}",
                "src2_ready": e["src2_ready"],
                "src2_tag": e["src2_tag"],
                "src2_val": f"0x{mask32(e['src2_val']):08x}",
                "rob_tag": e["rob_tag"],
                "imm": f"0x{mask32(e['imm']):08x}",
                "alu_src": e["alu_src"],
                "age": e["age"],
            })
        return {
            "full": self._is_full(),
            "entries": entries,
            "exec_valid": self["exec_valid"],
            "exec_rob_tag": self["exec_rob_tag"],
        }
