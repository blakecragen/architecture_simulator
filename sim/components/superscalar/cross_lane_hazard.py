"""Cross-lane hazard detector for superscalar pipeline.

Detects intra-group RAW dependencies (lane j reads what lane i<j writes)
and pipeline load-use hazards across lanes.
"""
from sim.component.base import ComponentBase, Port


class CrossLaneHazardDetector(ComponentBase):
    """
    Cross-lane hazard detector for N-wide superscalar.

    Detects two types of hazards:
    1. Intra-group RAW: Within a fetch group, if lane i writes rd and
       lane j>i reads that register, lane j (and all later lanes) are squashed.
    2. Pipeline load-use: If any lane in ID/EX has mem_read=1 and the current
       group depends on that load destination, the pipeline stalls.

    Outputs lane_valid_i signals (1=execute, 0=squash/NOP).
    """
    name = "cross_lane_hazard_detector"
    ui_label = "Cross-Lane Hazard"
    ui_category = "control"

    def __init__(self, num_lanes: int = 2, zero_reg_index: int | None = 0, **kw):
        self.num_lanes = num_lanes
        # Architectural register hardwired to zero (never a real RAW source/dest):
        # RISC-V x0 (0), ARM XZR (31), x86 none (None). -1 disables the check.
        self._zero = -1 if zero_reg_index is None else zero_reg_index

        self.ports_spec = {
            "stall": Port(1, "out", "Pipeline stall (all lanes)"),
            "partial_squash": Port(1, "out", "Intra-group squash (fetch advances partial)"),
            "squash_from": Port(8, "out", "Number of lanes that execute this group (re-fetch boundary)"),
        }

        # Per-lane decoder outputs (rd, rs1, rs2, reg_write) for current group
        for i in range(num_lanes):
            self.ports_spec[f"rd_{i}"]        = Port(5, "in", f"Lane {i} destination reg")
            self.ports_spec[f"rs1_{i}"]       = Port(5, "in", f"Lane {i} source reg 1")
            self.ports_spec[f"rs2_{i}"]       = Port(5, "in", f"Lane {i} source reg 2")
            self.ports_spec[f"reg_write_{i}"] = Port(1, "in", f"Lane {i} writes register")
            self.ports_spec[f"mem_read_{i}"]  = Port(1, "in", f"Lane {i} is a load")
            self.ports_spec[f"mem_write_{i}"] = Port(1, "in", f"Lane {i} is a store")
            self.ports_spec[f"branch_{i}"]    = Port(1, "in", f"Lane {i} is a conditional branch")
            self.ports_spec[f"jal_{i}"]       = Port(1, "in", f"Lane {i} is a JAL/unconditional jump")
            self.ports_spec[f"jalr_{i}"]      = Port(1, "in", f"Lane {i} is a JALR/indirect jump")
            self.ports_spec[f"alu_src_{i}"]   = Port(1, "in", f"Lane {i} ALU src (1=imm; rs2 field is then immediate bits, not a register read)")
            self.ports_spec[f"lane_valid_{i}"] = Port(1, "out", f"Lane {i} valid (not squashed)")

        # Pipeline hazard inputs (from ID/EX stages of all lanes)
        for i in range(num_lanes):
            self.ports_spec[f"id_ex_mem_read_{i}"] = Port(1, "in", f"ID/EX lane {i} is load")
            self.ports_spec[f"id_ex_rd_{i}"]       = Port(5, "in", f"ID/EX lane {i} dest reg")

        super().__init__(**kw)

    def evaluate(self):
        stall = 0
        lane_valid = [1] * self.num_lanes
        squash_from = self.num_lanes  # index from which to squash (== lanes that execute)

        # Whether each lane actually reads the rs2 REGISTER. For I-type ALU ops,
        # loads, LUI/AUIPC and JAL the decoder's rs2 field carries immediate bits
        # (RISC-V) or a stale 0 (ARM/x86), NOT a real source register — treating
        # it as one caused phantom RAW/load-use hazards that falsely squashed
        # independent lanes (wider-is-slower on dependency-free code). rs2 is a
        # genuine register read only for register-ALU ops (alu_src==0, excluding
        # JAL/JALR), stores (rs2 = store data), and branches (rs2 = compare rhs).
        reads_rs2 = [
            bool(self[f"mem_write_{i}"]) or bool(self[f"branch_{i}"]) or
            (self[f"alu_src_{i}"] == 0 and not self[f"jal_{i}"] and not self[f"jalr_{i}"])
            for i in range(self.num_lanes)
        ]

        # 1. Pipeline load-use hazard: check if any ID/EX lane is a load
        #    whose rd matches any current-group source register
        for ex_lane in range(self.num_lanes):
            if not self[f"id_ex_mem_read_{ex_lane}"]:
                continue
            ex_rd = self[f"id_ex_rd_{ex_lane}"]
            if ex_rd == self._zero:
                continue
            for cur_lane in range(self.num_lanes):
                if (self[f"rs1_{cur_lane}"] == ex_rd or
                        (reads_rs2[cur_lane] and self[f"rs2_{cur_lane}"] == ex_rd)):
                    stall = 1
                    break
            if stall:
                break

        if not stall:
            # 2. Intra-group RAW hazard: if lane i writes rd and lane j>i reads
            #    it, squash lane j and all later lanes.
            for i in range(self.num_lanes):
                if not self[f"reg_write_{i}"]:
                    continue
                rd_i = self[f"rd_{i}"]
                if rd_i == self._zero:
                    continue
                for j in range(i + 1, self.num_lanes):
                    if j >= squash_from:
                        break
                    if (self[f"rs1_{j}"] == rd_i or
                            (reads_rs2[j] and self[f"rs2_{j}"] == rd_i)):
                        squash_from = j
                        break

            # 3. (removed) Structural memory hazard. The superscalar pipeline now
            #    uses a MultiPortDataMemory: every lane has its own port, so
            #    multiple loads/stores execute in the same group with correct
            #    program-order semantics (store->load forwarding from older lanes,
            #    younger-store-wins on same-word writes). Memory-bound code
            #    therefore scales with lane width and cycle counts stay monotonic,
            #    instead of the old single-port squash-and-refetch penalty.

            # 4. Control-flow shadow: a branch/jump must be the LAST instruction
            #    that executes in its group, and branch resolution is wired from
            #    lane 0 only. For the first control-transfer lane i:
            #      i == 0 -> squash_from = 1 (the branch executes in lane 0 and
            #                resolves; the shadow in lanes 1+ is squashed),
            #      i  > 0 -> squash_from = i (the branch itself is squashed and
            #                re-fetched, so next cycle it starts a fresh group in
            #                lane 0 where resolution can see it).
            #    i.e. squash_from = min(squash_from, max(i, 1)). Conservative for
            #    conditional branches (never speculate past a branch in-group).
            for i in range(self.num_lanes):
                if self[f"branch_{i}"] or self[f"jal_{i}"] or self[f"jalr_{i}"]:
                    squash_from = min(squash_from, max(i, 1))
                    break

            for i in range(self.num_lanes):
                if i >= squash_from:
                    lane_valid[i] = 0

        # Output
        self["stall"] = stall
        self["squash_from"] = (self.num_lanes if stall else squash_from) & 0xFF
        self["partial_squash"] = 0 if stall else (1 if squash_from < self.num_lanes else 0)
        for i in range(self.num_lanes):
            self[f"lane_valid_{i}"] = 0 if stall else lane_valid[i]

    def get_state(self):
        state = {
            "stall": "STALL" if self["stall"] else "OK",
            "squash_from": self["squash_from"],
        }
        for i in range(self.num_lanes):
            state[f"lane_{i}_valid"] = self[f"lane_valid_{i}"]
        return state
