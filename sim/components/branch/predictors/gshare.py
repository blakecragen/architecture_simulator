from .base import BranchPredictorBase


class GSharePredictor(BranchPredictorBase):
    """Global history register XOR PC → 2-bit saturating counter table."""
    name = "gshare"
    ui_label = "GShare Predictor"

    def __init__(self, history_bits: int = 8, **kw):
        super().__init__(**kw)
        self._history_bits = history_bits
        table_size = 1 << history_bits
        self._table = [2] * table_size  # weakly taken (2 of 0-3)
        self._ghr = 0  # global history register

    def _index(self, pc: int) -> int:
        mask = (1 << self._history_bits) - 1
        return ((pc >> 2) ^ self._ghr) & mask

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
            actual = self["actual"]
            if actual:
                self._table[idx] = min(self._table[idx] + 1, 3)
            else:
                self._table[idx] = max(self._table[idx] - 1, 0)
            mask = (1 << self._history_bits) - 1
            self._ghr = ((self._ghr << 1) | actual) & mask

    def _get_predictor_state(self):
        idx = self._index(self["pc"])
        counter = self._table[idx]
        pred = "T" if counter >= 2 else "NT"
        return {
            "prediction": pred,
            "counter": f"{counter}/3",
            "ghr": f"0b{self._ghr:0{self._history_bits}b}",
            "index": idx,
        }
