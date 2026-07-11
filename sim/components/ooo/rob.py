"""
Reorder Buffer (ROB) for Out-of-Order execution.

Tomasulo-style circular buffer that ensures in-order commit.
Size: 8 entries. Head commits, tail dispatches.

evaluate()     -- combinational: expose commit data from head if ready,
                  expose full/flush status, assign dispatch tag.
rising_edge()  -- sequential: dispatch new entry at tail, mark complete,
                  advance head on commit, handle flush.
"""
from sim.component.base import ComponentBase, Port, mask32


# ── ROB entry fields ─────────────────────────────────────────────
_EMPTY_ENTRY = {
    "valid": 0,
    "ready": 0,
    "rd": 0,
    "value": 0,
    "pc": 0,
    "is_branch": 0,
    "branch_taken": 0,
    "is_load": 0,
    "is_store": 0,
    "store_data_reg": 0,
    "reg_write": 0,
    "write_flags": 0,
}

ROB_SIZE = 8
TAG_MASK = (1 << 5) - 1  # 5-bit tag


class ReorderBuffer(ComponentBase):
    """
    Circular reorder buffer with 8 entries.

    Dispatch writes to tail, complete marks an entry ready with its value,
    commit reads from head when the entry is valid and ready.

    Branch misprediction: if the committing entry is a branch whose
    branch_taken flag differs from the predicted path, flush is asserted
    and flush_target_pc is set (simplified: value holds the correct PC).
    """
    name = "reorder_buffer"
    ui_label = "Reorder Buffer"
    ui_category = "ooo"
    ports_spec = {
        # Dispatch (from decoder / rename) ---------------------
        "dispatch_en":         Port(1,  "in",  "Request to allocate a new ROB entry"),
        "dispatch_rd":         Port(5,  "in",  "Destination architectural register"),
        "dispatch_pc":         Port(32, "in",  "PC of dispatched instruction"),
        "dispatch_is_branch":  Port(1,  "in",  "Instruction is a branch"),
        "dispatch_is_load":    Port(1,  "in",  "Instruction is a load"),
        "dispatch_is_store":   Port(1,  "in",  "Instruction is a store"),
        "dispatch_store_data_reg": Port(5, "in", "Store data register (its value is read from the regfile at commit)"),
        "dispatch_reg_write":  Port(1,  "in",  "Instruction writes a register"),
        "dispatch_write_flags": Port(1, "in",  "Instruction sets condition flags (ARM SUBS/CMP, x86 CMP/arith)"),
        "dispatch_tag":        Port(5,  "out", "Assigned ROB tag"),
        # Complete (from execution units via CDB) --------------
        "complete_en":         Port(1,  "in",  "CDB broadcast valid"),
        "complete_tag":        Port(5,  "in",  "CDB ROB tag"),
        "complete_value":      Port(32, "in",  "CDB result value"),
        "complete_mem_value":  Port(32, "in",  "Memory read result (for loads)"),
        "complete_branch_taken": Port(1, "in", "Branch actually taken (CDB)"),
        # Commit -----------------------------------------------
        "commit_en":           Port(1,  "out", "Head entry committed this cycle"),
        "commit_rd":           Port(5,  "out", "Committed destination register"),
        "commit_value":        Port(32, "out", "Committed value"),
        "commit_tag":          Port(5,  "out", "Committed ROB tag"),
        "commit_is_store":     Port(1,  "out", "Committed instruction is a store"),
        "commit_store_data_reg": Port(5, "out", "Store data register index (read from regfile at commit)"),
        "commit_reg_write":    Port(1,  "out", "Committed instruction writes a register"),
        "commit_write_flags":  Port(1,  "out", "Committed instruction sets condition flags"),
        # Status -----------------------------------------------
        "full":                Port(1,  "out", "ROB is full (cannot dispatch)"),
        "empty":               Port(1,  "out", "ROB has no in-flight instructions"),
        "store_pending_mask":  Port(32, "out", "Bit per ROB index: uncommitted store"),
        "head_ptr":            Port(5,  "out", "Current head index (oldest entry)"),
        "flush":               Port(1,  "out", "Branch mispredict detected at commit"),
        "flush_target_pc":     Port(32, "out", "Correct PC after mispredict"),
    }

    def __init__(self, **kw):
        super().__init__(**kw)
        self._entries = [dict(_EMPTY_ENTRY) for _ in range(ROB_SIZE)]
        self._head = 0  # index of next entry to commit
        self._tail = 0  # index of next entry to allocate
        self._count = 0  # number of valid entries

    # ── helpers ────────────────────────────────────────────────

    def _is_full(self) -> bool:
        return self._count >= ROB_SIZE

    def _is_empty(self) -> bool:
        return self._count == 0

    # ── combinational ─────────────────────────────────────────

    def evaluate(self):
        # Default outputs
        self["commit_en"] = 0
        self["commit_rd"] = 0
        self["commit_value"] = 0
        self["commit_tag"] = 0
        self["commit_is_store"] = 0
        self["commit_store_data_reg"] = 0
        self["commit_reg_write"] = 0
        self["commit_write_flags"] = 0
        self["flush"] = 0
        self["flush_target_pc"] = 0
        self["full"] = 1 if self._is_full() else 0
        self["empty"] = 1 if self._is_empty() else 0

        # Dispatch tag: always advertise the current tail index so the
        # dispatch stage can read it combinationally before rising_edge.
        self["dispatch_tag"] = self._tail & TAG_MASK

        # Store->load ordering: advertise which ROB slots hold uncommitted
        # stores (plus the head index for age comparison). The RS refuses to
        # issue a load while a store OLDER than it is still pending, so the
        # load reads dmem only after that store's commit has written it.
        mask = 0
        for i, e in enumerate(self._entries):
            if e["valid"] and e["is_store"]:
                mask |= 1 << i
        self["store_pending_mask"] = mask
        self["head_ptr"] = self._head & TAG_MASK

        # Commit: expose head entry if valid and ready
        if not self._is_empty():
            head = self._entries[self._head]
            if head["valid"] and head["ready"]:
                self["commit_en"] = 1
                self["commit_rd"] = head["rd"] & TAG_MASK
                self["commit_value"] = mask32(head["value"])
                self["commit_tag"] = self._head & TAG_MASK
                self["commit_is_store"] = head["is_store"]
                self["commit_store_data_reg"] = head["store_data_reg"] & TAG_MASK
                self["commit_reg_write"] = 1 if head["reg_write"] else 0
                self["commit_write_flags"] = 1 if head["write_flags"] else 0
                # Branch mispredict check (simplified model):
                # If the instruction is a branch and was taken, we
                # signal a flush.  A real design would compare predicted
                # vs actual direction; here branch_taken == 1 triggers
                # flush, with the correct target carried in value.
                if head["is_branch"] and head["branch_taken"]:
                    self["flush"] = 1
                    self["flush_target_pc"] = mask32(head["value"])

    # ── sequential ────────────────────────────────────────────

    def rising_edge(self):
        # 1. Flush: clear everything
        if self["flush"]:
            for i in range(ROB_SIZE):
                self._entries[i] = dict(_EMPTY_ENTRY)
            self._head = 0
            self._tail = 0
            self._count = 0
            return

        # 2. Commit: retire head entry
        committed = False
        if self["commit_en"]:
            self._entries[self._head] = dict(_EMPTY_ENTRY)
            self._head = (self._head + 1) % ROB_SIZE
            self._count -= 1
            committed = True

        # 3. Complete: mark matching entry ready
        if self["complete_en"]:
            tag = self["complete_tag"] & (ROB_SIZE - 1)
            entry = self._entries[tag]
            if entry["valid"]:
                entry["ready"] = 1
                if entry["is_load"]:
                    entry["value"] = mask32(self["complete_mem_value"])
                else:
                    entry["value"] = mask32(self["complete_value"])
                entry["branch_taken"] = self["complete_branch_taken"] & 1

        # 4. Dispatch: allocate new entry at tail
        if self["dispatch_en"] and not self._is_full():
            entry = self._entries[self._tail]
            entry["valid"] = 1
            entry["ready"] = 0
            entry["rd"] = self["dispatch_rd"] & TAG_MASK
            entry["value"] = 0
            entry["pc"] = mask32(self["dispatch_pc"])
            entry["is_branch"] = self["dispatch_is_branch"] & 1
            entry["branch_taken"] = 0
            entry["is_load"] = self["dispatch_is_load"] & 1
            entry["is_store"] = self["dispatch_is_store"] & 1
            entry["store_data_reg"] = self["dispatch_store_data_reg"] & TAG_MASK
            entry["reg_write"] = self["dispatch_reg_write"] & 1
            entry["write_flags"] = self["dispatch_write_flags"] & 1
            self._tail = (self._tail + 1) % ROB_SIZE
            self._count += 1

    # ── UI state ──────────────────────────────────────────────

    def get_state(self) -> dict:
        entries = []
        for i in range(ROB_SIZE):
            e = self._entries[i]
            entries.append({
                "index": i,
                "valid": e["valid"],
                "ready": e["ready"],
                "rd": e["rd"],
                "value": f"0x{mask32(e['value']):08x}",
                "pc": f"0x{mask32(e['pc']):08x}",
                "is_branch": e["is_branch"],
                "branch_taken": e["branch_taken"],
                "is_load": e["is_load"],
                "is_store": e["is_store"],
            })
        return {
            "head": self._head,
            "tail": self._tail,
            "count": self._count,
            "full": self._is_full(),
            "entries": entries,
            "commit_en": self["commit_en"],
            "flush": self["flush"],
        }
