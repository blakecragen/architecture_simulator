from .base import BranchPredictorBase


class NoPrediction(BranchPredictorBase):
    """No prediction — always predicts not-taken. Safest for single-cycle."""
    name = "no_prediction"
    ui_label = "No Prediction"

    def _predict(self):
        self["prediction"] = 0
        self["predict_target"] = 0
