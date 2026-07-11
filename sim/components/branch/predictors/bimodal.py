from .base import BranchPredictorBase


class BimodalPredictor(BranchPredictorBase):
    """Per-PC 2-bit saturating counter table."""
    name = "bimodal"
    ui_label = "Bimodal Predictor"

    def __init__(self, table_size: int = 256, **kw):
        super().__init__(**kw)
        self._table_size = table_size
        # 2-bit counters: 0,1 = not-taken; 2,3 = taken. Init to weakly taken (2).
        self._table = [2] * table_size

    def _index(self, pc: int) -> int:
        return (pc >> 2) % self._table_size

    def _predict(self):
        if self["is_jal"]:
            self["prediction"] = 1
        elif self["is_branch"]:
            idx = self._index(self["pc"])
            self["prediction"] = 1 if self._table[idx] >= 2 else 0
        else:
            self["prediction"] = 0
        self._compute_target()

    def _update(self):
        if self["update_en"]:
            idx = self._index(self["update_pc"])
            if self["actual"]:
                self._table[idx] = min(self._table[idx] + 1, 3)
            else:
                self._table[idx] = max(self._table[idx] - 1, 0)

    def _get_predictor_state(self):
        idx = self._index(self["pc"])
        counter = self._table[idx]
        pred = "T" if counter >= 2 else "NT"
        return {
            "prediction": pred,
            "counter": f"{counter}/3",
            "index": idx,
        }
