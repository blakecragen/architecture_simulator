"""
Register Alias Table (RAT) for Out-of-Order execution.

Maps architectural register numbers to ROB tags so the reservation
stations can track which in-flight instruction will produce a value.

32 entries (one per architectural register).  The hardwired-zero register
(RISC-V x0, ARM XZR; x86 has none) is "always ready, value 0" and never aliased.

evaluate()     -- combinational: look up rs1 / rs2 and output whether
                  each is ready (no pending ROB write) or its tag.
rising_edge()  -- sequential: allocate a new mapping on dispatch, clear
                  the mapping when the ROB commits that tag, or flush
                  everything on a pipeline squash.
"""
from sim.component.base import ComponentBase, Port


NUM_REGS = 32
TAG_MASK = (1 << 5) - 1  # 5-bit tag


def _empty_mapping() -> dict:
    """A register with no in-flight writer."""
    return {"valid": 0, "tag": 0}


class RegisterAliasTable(ComponentBase):
    """
    Shared 32-entry RAT used by RISC-V, ARM, and x86 (parameterized via
    has_zero_reg / zero_reg_index for the per-ISA hardwired-zero register:
    RISC-V x0, ARM XZR=31, x86 none).

    Each entry tracks whether an architectural register has a pending
    write and, if so, the ROB tag of the instruction that will produce
    the value.

    Lookup is combinational (evaluate).  Allocation and commit are
    sequential (rising_edge).  Flush resets every mapping.
    """
    name = "register_alias_table"
    ui_label = "Register Alias Table"
    ui_category = "ooo"
    ports_spec = {
        # Lookup (for dispatch) ────────────────────────────────
        "rs1_arch":   Port(5,  "in",  "Source 1 architectural register"),
        "rs2_arch":   Port(5,  "in",  "Source 2 architectural register"),
        "rs1_ready":  Port(1,  "out", "1 = rs1 has no pending write"),
        "rs1_tag":    Port(5,  "out", "ROB tag for rs1 (valid when not ready)"),
        "rs2_ready":  Port(1,  "out", "1 = rs2 has no pending write"),
        "rs2_tag":    Port(5,  "out", "ROB tag for rs2 (valid when not ready)"),
        # Allocate (on dispatch) ───────────────────────────────
        "rd_arch":    Port(5,  "in",  "Destination architectural register"),
        "alloc_en":   Port(1,  "in",  "Allocate a new mapping"),
        "alloc_tag":  Port(5,  "in",  "ROB tag to associate with rd"),
        # Commit (from ROB) ────────────────────────────────────
        "commit_en":  Port(1,  "in",  "Commit / free a mapping"),
        "commit_rd":  Port(5,  "in",  "Arch register being committed"),
        "commit_tag": Port(5,  "in",  "ROB tag being committed"),
        # Control ──────────────────────────────────────────────
        "flush":      Port(1,  "in",  "Pipeline flush: reset all mappings"),
    }

    def __init__(self, has_zero_reg: bool = True, zero_reg_index: int = 0, **kw):
        super().__init__(**kw)
        # Which architectural register (if any) is hardwired to zero and must
        # never be renamed: RISC-V x0 (index 0), ARM XZR (index 31), x86 none.
        self._has_zero = has_zero_reg
        self._zero_idx = zero_reg_index
        self._map: list[dict] = [_empty_mapping() for _ in range(NUM_REGS)]

    # ── helpers ────────────────────────────────────────────────

    def _is_zero(self, reg: int) -> bool:
        """True if *reg* is the hardwired-zero register (never aliased)."""
        return self._has_zero and reg == self._zero_idx

    # ── combinational ─────────────────────────────────────────

    def _is_committing(self, reg: int) -> bool:
        """Check if a same-cycle ROB commit is retiring the mapping for *reg*."""
        if not self["commit_en"]:
            return False
        rd = self["commit_rd"] % NUM_REGS
        if rd != reg or self._is_zero(rd):
            return False
        tag = self["commit_tag"] & TAG_MASK
        m = self._map[reg]
        return bool(m["valid"] and (m["tag"] & TAG_MASK) == tag)

    def evaluate(self):
        rs1 = self["rs1_arch"] % NUM_REGS
        rs2 = self["rs2_arch"] % NUM_REGS

        # The hardwired-zero register is always ready with no tag.
        if self._is_zero(rs1):
            self["rs1_ready"] = 1
            self["rs1_tag"] = 0
        else:
            m = self._map[rs1]
            if m["valid"] and not self._is_committing(rs1):
                # There is an in-flight instruction that will write rs1
                self["rs1_ready"] = 0
                self["rs1_tag"] = m["tag"] & TAG_MASK
            else:
                self["rs1_ready"] = 1
                self["rs1_tag"] = 0

        if self._is_zero(rs2):
            self["rs2_ready"] = 1
            self["rs2_tag"] = 0
        else:
            m = self._map[rs2]
            if m["valid"] and not self._is_committing(rs2):
                self["rs2_ready"] = 0
                self["rs2_tag"] = m["tag"] & TAG_MASK
            else:
                self["rs2_ready"] = 1
                self["rs2_tag"] = 0

    # ── sequential ────────────────────────────────────────────

    def rising_edge(self):
        # 1. Flush: reset every mapping
        if self["flush"]:
            for i in range(NUM_REGS):
                self._map[i] = _empty_mapping()
            return

        # 2. Commit: clear the mapping IF the committed tag is still
        #    the current alias for that register.  A later dispatch may
        #    have already re-aliased the same register to a newer tag,
        #    in which case we must NOT clear it.
        if self["commit_en"]:
            rd = self["commit_rd"] % NUM_REGS
            tag = self["commit_tag"] & TAG_MASK
            if not self._is_zero(rd):
                m = self._map[rd]
                if m["valid"] and (m["tag"] & TAG_MASK) == tag:
                    m["valid"] = 0
                    m["tag"] = 0

        # 3. Allocate: create a new mapping for rd on dispatch.
        #    The hardwired-zero register is never aliased.
        if self["alloc_en"]:
            rd = self["rd_arch"] % NUM_REGS
            tag = self["alloc_tag"] & TAG_MASK
            if not self._is_zero(rd):
                self._map[rd] = {"valid": 1, "tag": tag}

    # ── UI state ──────────────────────────────────────────────

    def get_state(self) -> dict:
        mappings = []
        for i in range(NUM_REGS):
            m = self._map[i]
            if m["valid"]:
                mappings.append({
                    "reg": f"x{i}",
                    "pending": True,
                    "tag": m["tag"],
                })
            else:
                mappings.append({
                    "reg": f"x{i}",
                    "pending": False,
                    "tag": None,
                })
        # Also include a compact "active aliases" list for quick viewing
        active = {
            f"x{i}": m["tag"]
            for i, m in enumerate(self._map)
            if m["valid"]
        }
        return {
            "mappings": mappings,
            "active_aliases": active,
            "rs1_ready": self["rs1_ready"],
            "rs1_tag": self["rs1_tag"],
            "rs2_ready": self["rs2_ready"],
            "rs2_tag": self["rs2_tag"],
        }
