from sim.component.base import ComponentBase, Port


class BranchPredictorBase(ComponentBase):
    """Port contract for all branch predictors. Swap freely.

    Subclasses override ``_predict()`` (direction) and ``_update()`` (training)
    instead of ``evaluate()``/``rising_edge()``.  The base class wraps them with
    an optional BTB target-cache layer when ``prediction_stage="if"``.
    """
    ui_category = "control"
    ports_spec = {
        "pc":             Port(32, "in",  "Current PC"),
        "is_branch":      Port(1,  "in",  "Is this a branch?"),
        "is_jal":         Port(1,  "in",  "Is this a JAL (unconditional jump)?"),
        "imm":            Port(32, "in",  "Immediate (branch offset)"),
        "prediction":     Port(1,  "out", "Predicted taken/not-taken"),
        "predict_target": Port(32, "out", "Predicted branch target PC"),
        "update_en":      Port(1,  "in",  "Feedback enable"),
        "update_pc":      Port(32, "in",  "PC of instruction being trained"),
        "actual":         Port(1,  "in",  "Actual branch outcome"),
        "update_target":  Port(32, "in",  "Actual target PC (for BTB training)"),
    }

    def __init__(self, prediction_stage="id", btb_size=256, **kw):
        super().__init__(**kw)
        self.prediction_stage = prediction_stage
        # BTB target cache — only allocated for IF-stage
        if prediction_stage == "if":
            # Each entry: {"pc": tag, "target": int, "counter": int} or None
            self._btb_size = btb_size
            self._btb = [None] * btb_size
        else:
            self._btb = None
            self._btb_size = 0

    # ── BTB helpers ───────────────────────────────────────────────
    def _btb_index(self, pc):
        return (pc >> 2) % self._btb_size

    def _btb_lookup(self, pc):
        """Return entry if tag matches, else None."""
        idx = self._btb_index(pc)
        entry = self._btb[idx]
        if entry is not None and entry["pc"] == pc:
            return entry
        return None

    def _btb_train(self, pc, target, taken):
        """Update BTB on feedback."""
        idx = self._btb_index(pc)
        if taken:
            entry = self._btb[idx]
            if entry is not None and entry["pc"] == pc:
                self._btb[idx] = {
                    "pc": pc,
                    "target": target,
                    "counter": min(entry["counter"] + 1, 3),
                }
            else:
                self._btb[idx] = {"pc": pc, "target": target, "counter": 2}
        else:
            entry = self._btb[idx]
            if entry is not None and entry["pc"] == pc:
                self._btb[idx] = {
                    "pc": pc,
                    "target": entry["target"],
                    "counter": max(entry["counter"] - 1, 0),
                }

    # ── Template hooks (subclasses override these) ────────────────
    def _predict(self):
        """Direction prediction — called by evaluate(). Override in subclass."""
        self["prediction"] = 0
        self["predict_target"] = 0

    def _update(self):
        """Training on feedback — called by rising_edge(). Override in subclass."""
        pass

    def _get_predictor_state(self):
        """Subclass-specific state for the UI. Override in subclass."""
        return {}

    # ── Shared helpers ────────────────────────────────────────────
    def _compute_target(self):
        """Set predict_target = pc + imm when prediction is taken."""
        if self["prediction"]:
            self["predict_target"] = (self["pc"] + self["imm"]) & 0xFFFF_FFFF
        else:
            self["predict_target"] = 0

    def get_state(self):
        state = self._get_predictor_state()
        if self.prediction_stage == "if" and self._btb is not None:
            pc = self["pc"]
            entry = self._btb_lookup(pc)
            if entry is not None:
                hit = True
                pred = "T" if entry["counter"] >= 2 else "NT"
                state["btb_target"] = f"0x{entry['target']:08x}"
                state["btb_counter"] = f"{entry['counter']}/3"
            else:
                hit = False
                pred = "NT (miss)"
            state["prediction"] = pred
            state["btb_hit"] = hit
        return state

    # ── Base evaluate / rising_edge with BTB wrapper ──────────────
    def evaluate(self):
        if self.prediction_stage == "if" and self._btb is not None:
            # IF-stage: inject virtual is_branch from BTB hit
            pc = self["pc"]
            entry = self._btb_lookup(pc)
            if entry is not None and entry["counter"] >= 2:
                # BTB hit + strong — inject signals so subclass sees a branch
                self._ports["is_branch"] = 1
                self._predict()
                # Override target with BTB-cached target (subclass computed
                # pc+imm which is wrong at IF-stage since imm is unwired)
                if self["prediction"]:
                    self["predict_target"] = entry["target"]
            else:
                # BTB miss or weak — predict not-taken
                self._ports["is_branch"] = 0
                self._predict()
                self["prediction"] = 0
                self["predict_target"] = 0
        else:
            # ID-stage: decoder ports are wired, just delegate
            self._predict()

    def rising_edge(self):
        if self.prediction_stage == "if" and self._btb is not None:
            # Train the BTB from committed outcomes
            if self["update_en"]:
                self._btb_train(
                    self["update_pc"],
                    self["update_target"],
                    self["actual"],
                )
        # Always let the subclass update its own tables (counters, GHR, etc.)
        self._update()
