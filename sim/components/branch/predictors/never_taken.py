from .base import BranchPredictorBase


class NeverTaken(BranchPredictorBase):
    """Static predictor — always predicts not-taken for branches, taken for JAL."""
    name = "never_taken"
    ui_label = "Never Taken"

    def _predict(self):
        self["prediction"] = 1 if self["is_jal"] else 0
        self._compute_target()

    def _get_predictor_state(self):
        return {"prediction": "NT (branches)"}
