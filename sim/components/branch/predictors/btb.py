"""IF-stage Branch Target Buffer predictor.

Thin wrapper around BimodalPredictor that defaults to IF-stage prediction.
The base class BTB layer handles target caching; BimodalPredictor provides
the 2-bit saturating counter direction logic.
"""
from .bimodal import BimodalPredictor


class BTBPredictor(BimodalPredictor):
    """PC-indexed BTB backed by bimodal counters."""
    name = "btb"
    ui_label = "BTB"

    def __init__(self, table_size: int = 256, **kw):
        kw.setdefault("prediction_stage", "if")
        super().__init__(table_size=table_size, **kw)
