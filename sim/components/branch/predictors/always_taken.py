from .base import BranchPredictorBase


class AlwaysTaken(BranchPredictorBase):
    """Static predictor — always predicts taken."""
    name = "always_taken"
    ui_label = "Always Taken"

    def _predict(self):
        self["prediction"] = 1 if (self["is_branch"] or self["is_jal"]) else 0
        self._compute_target()

    def _get_predictor_state(self):
        return {"prediction": "T (always)"}
