"""
Tests for the IF/ID prediction stage toggle.

Verifies:
1. BTB backward compatibility (thin shim over BimodalPredictor)
2. prediction_stage as constructor param (not class constant)
3. Any predictor + IF-stage builds and simulates correctly
4. Any predictor + ID-stage still works after refactor
5. Base BTB layer learns targets at IF-stage
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.components.branch.predictors.btb import BTBPredictor
from sim.components.branch.predictors.bimodal import BimodalPredictor
from sim.components.branch.predictors.gshare import GSharePredictor
from sim.components.branch.predictors.always_taken import AlwaysTaken
from sim.components.branch.predictors.never_taken import NeverTaken
from sim.components.branch.predictors.no_predict import NoPrediction
from sim.components.branch.predictors.base import BranchPredictorBase
from sim.isa.riscv.presets.pipeline import build as riscv_pipe_build
from sim.isa.riscv.presets.superscalar import build as riscv_super_build
from sim.runner_v2 import run_simulation


class TestPredictionStageParam(unittest.TestCase):
    """prediction_stage is an instance param, not a class constant."""

    def test_default_is_id(self):
        self.assertEqual(BimodalPredictor().prediction_stage, "id")
        self.assertEqual(GSharePredictor().prediction_stage, "id")
        self.assertEqual(AlwaysTaken().prediction_stage, "id")
        self.assertEqual(NeverTaken().prediction_stage, "id")
        self.assertEqual(NoPrediction().prediction_stage, "id")

    def test_btb_defaults_to_if(self):
        self.assertEqual(BTBPredictor().prediction_stage, "if")

    def test_btb_can_be_overridden_to_id(self):
        btb = BTBPredictor(prediction_stage="id")
        self.assertEqual(btb.prediction_stage, "id")

    def test_bimodal_if_stage(self):
        bim = BimodalPredictor(prediction_stage="if")
        self.assertEqual(bim.prediction_stage, "if")
        self.assertIsNotNone(bim._btb)

    def test_gshare_if_stage(self):
        gs = GSharePredictor(prediction_stage="if")
        self.assertEqual(gs.prediction_stage, "if")
        self.assertIsNotNone(gs._btb)

    def test_always_taken_if_stage(self):
        at = AlwaysTaken(prediction_stage="if")
        self.assertEqual(at.prediction_stage, "if")
        self.assertIsNotNone(at._btb)

    def test_id_stage_has_no_btb(self):
        bim = BimodalPredictor()
        self.assertIsNone(bim._btb)


class TestBTBPredictor(unittest.TestCase):
    """Unit-level tests for the BTB predictor class (backward compat)."""

    def test_prediction_stage_is_if(self):
        btb = BTBPredictor()
        self.assertEqual(btb.prediction_stage, "if")

    def test_btb_miss_predicts_not_taken(self):
        """Empty BTB should predict not-taken for any PC."""
        btb = BTBPredictor(table_size=16)
        btb._ports["pc"] = 0x100
        btb.evaluate()
        self.assertEqual(btb["prediction"], 0)
        self.assertEqual(btb["predict_target"], 0)

    def test_btb_learns_target(self):
        """After training with taken branch, BTB should predict taken with correct target."""
        btb = BTBPredictor(table_size=16)
        # Train: branch at PC=0x100 was taken, target=0x80
        btb._ports["update_en"] = 1
        btb._ports["update_pc"] = 0x100
        btb._ports["actual"] = 1
        btb._ports["update_target"] = 0x80
        btb.rising_edge()
        # Now predict for same PC
        btb._ports["pc"] = 0x100
        btb.evaluate()
        self.assertEqual(btb["prediction"], 1)
        self.assertEqual(btb["predict_target"], 0x80)

    def test_btb_decrements_on_not_taken(self):
        """After enough not-taken updates, BTB should predict not-taken."""
        btb = BTBPredictor(table_size=16)
        # First: train as taken (counter=2)
        btb._ports["update_en"] = 1
        btb._ports["update_pc"] = 0x100
        btb._ports["actual"] = 1
        btb._ports["update_target"] = 0x80
        btb.rising_edge()
        # Decrement: 2 → 1
        btb._ports["actual"] = 0
        btb.rising_edge()
        btb._ports["pc"] = 0x100
        btb.evaluate()
        # Counter is now 1 (< 2), predict not-taken
        self.assertEqual(btb["prediction"], 0)

    def test_btb_saturates_at_3(self):
        """Counter should saturate at 3."""
        btb = BTBPredictor(table_size=16)
        btb._ports["update_en"] = 1
        btb._ports["update_pc"] = 0x100
        btb._ports["actual"] = 1
        btb._ports["update_target"] = 0x80
        # Train 5 times (should saturate at 3)
        for _ in range(5):
            btb.rising_edge()
        btb._ports["pc"] = 0x100
        btb.evaluate()
        self.assertEqual(btb["prediction"], 1)

    def test_btb_tag_prevents_aliasing(self):
        """Different PCs that hash to the same index should not alias."""
        btb = BTBPredictor(table_size=4)
        # Train PC=0x00 → target 0x80
        btb._ports["update_en"] = 1
        btb._ports["update_pc"] = 0x00
        btb._ports["actual"] = 1
        btb._ports["update_target"] = 0x80
        btb.rising_edge()
        # Query a different PC that maps to same index (0x40 >> 2 = 16 % 4 = 0)
        btb._ports["pc"] = 0x40
        btb.evaluate()
        # Should miss (tag mismatch), not return the other entry's target
        self.assertEqual(btb["prediction"], 0)


class TestBaseBTBLayer(unittest.TestCase):
    """Test the BTB layer in the base class directly."""

    def test_bimodal_if_learns_and_predicts(self):
        """Bimodal at IF-stage should learn targets via BTB and predict them."""
        bim = BimodalPredictor(table_size=16, prediction_stage="if")
        # Train: branch at PC=0x100 was taken, target=0x80
        bim._ports["update_en"] = 1
        bim._ports["update_pc"] = 0x100
        bim._ports["actual"] = 1
        bim._ports["update_target"] = 0x80
        bim.rising_edge()
        # Predict
        bim._ports["pc"] = 0x100
        bim.evaluate()
        self.assertEqual(bim["prediction"], 1)
        self.assertEqual(bim["predict_target"], 0x80)

    def test_gshare_if_learns_and_predicts(self):
        """GShare at IF-stage should learn targets via BTB and predict them."""
        gs = GSharePredictor(prediction_stage="if")
        gs._ports["update_en"] = 1
        gs._ports["update_pc"] = 0x100
        gs._ports["actual"] = 1
        gs._ports["update_target"] = 0x80
        gs.rising_edge()
        gs._ports["pc"] = 0x100
        gs.evaluate()
        self.assertEqual(gs["prediction"], 1)
        self.assertEqual(gs["predict_target"], 0x80)

    def test_no_prediction_if_stays_not_taken(self):
        """NoPrediction at IF-stage should always predict not-taken."""
        np = NoPrediction(prediction_stage="if")
        np._ports["update_en"] = 1
        np._ports["update_pc"] = 0x100
        np._ports["actual"] = 1
        np._ports["update_target"] = 0x80
        np.rising_edge()
        np._ports["pc"] = 0x100
        np.evaluate()
        # NoPrediction always says 0, BTB hit + strong but _predict returns 0
        # so base wrapper forces prediction=0
        self.assertEqual(np["prediction"], 0)


class TestPipelineIntegration(unittest.TestCase):
    """Integration tests with RISC-V pipeline."""

    def _tight_loop(self):
        return [
            0x00300093,  # ADDI x1, x0, 3    (x1 = 3)
            0x00000013,  # NOP
            0x00000013,  # NOP
            0x00000013,  # NOP
            0xFFF08093,  # ADDI x1, x1, -1   (x1--)   PC=0x10
            0xFE009CE3,  # BNE  x1, x0, -8   (loop)   PC=0x14
            0x00000013,  # NOP (exit)
        ]

    def test_btb_builds_without_error(self):
        btb = BTBPredictor()
        cpu = riscv_pipe_build(self._tight_loop(), branch_predictor=btb)
        states = run_simulation(cpu, num_cycles=30)
        self.assertTrue(len(states) > 0)

    def test_btb_loop_reaches_correct_result(self):
        btb = BTBPredictor()
        cpu = riscv_pipe_build(self._tight_loop(), branch_predictor=btb)
        states = run_simulation(cpu, num_cycles=40)
        self.assertEqual(states[-1]["regfile"]["registers"][1], 0)

    def test_bimodal_id_works(self):
        bimodal = BimodalPredictor()
        cpu = riscv_pipe_build(self._tight_loop(), branch_predictor=bimodal)
        states = run_simulation(cpu, num_cycles=40)
        self.assertEqual(states[-1]["regfile"]["registers"][1], 0)

    def test_bimodal_if_builds_and_runs(self):
        bimodal = BimodalPredictor(prediction_stage="if")
        cpu = riscv_pipe_build(self._tight_loop(), branch_predictor=bimodal)
        states = run_simulation(cpu, num_cycles=40)
        self.assertEqual(states[-1]["regfile"]["registers"][1], 0)

    def test_gshare_if_builds_and_runs(self):
        gs = GSharePredictor(prediction_stage="if")
        cpu = riscv_pipe_build(self._tight_loop(), branch_predictor=gs)
        states = run_simulation(cpu, num_cycles=40)
        self.assertEqual(states[-1]["regfile"]["registers"][1], 0)

    def test_always_taken_if_builds_and_runs(self):
        at = AlwaysTaken(prediction_stage="if")
        cpu = riscv_pipe_build(self._tight_loop(), branch_predictor=at)
        states = run_simulation(cpu, num_cycles=40)
        self.assertEqual(states[-1]["regfile"]["registers"][1], 0)

    def test_no_prediction_id_still_works(self):
        np = NoPrediction()
        cpu = riscv_pipe_build(self._tight_loop(), branch_predictor=np)
        states = run_simulation(cpu, num_cycles=40)
        self.assertEqual(states[-1]["regfile"]["registers"][1], 0)


class TestSuperscalarIntegration(unittest.TestCase):
    """Integration tests with RISC-V superscalar."""

    def _program(self):
        return [
            0x00300093,  # ADDI x1, x0, 3
            0x00000013,  # NOP
            0xFFF08093,  # ADDI x1, x1, -1   PC=0x08
            0xFE009CE3,  # BNE  x1, x0, -8   PC=0x0C
            0x00000013,  # NOP
        ]

    def test_superscalar_btb_builds(self):
        # IF-stage predictors on superscalar are informational-only (they
        # train + display but do not steer fetch), so the result must be
        # architecturally correct: the loop completes with x1 == 0.
        btb = BTBPredictor()
        cpu = riscv_super_build(self._program(), num_lanes=2, branch_predictor=btb)
        states = run_simulation(cpu, num_cycles=30)
        self.assertEqual(states[-1]["regfile"]["registers"][1], 0)

    def test_superscalar_bimodal_id(self):
        bimodal = BimodalPredictor()
        cpu = riscv_super_build(self._program(), num_lanes=2, branch_predictor=bimodal)
        states = run_simulation(cpu, num_cycles=30)
        # ID-stage prediction steers fetch and is architecturally correct:
        # the loop must complete (x1 counted down to 0).
        self.assertEqual(states[-1]["regfile"]["registers"][1], 0)

    def test_superscalar_bimodal_if(self):
        # Informational-only at IF-stage — same contract as the BTB test above.
        bimodal = BimodalPredictor(prediction_stage="if")
        cpu = riscv_super_build(self._program(), num_lanes=2, branch_predictor=bimodal)
        states = run_simulation(cpu, num_cycles=30)
        self.assertEqual(states[-1]["regfile"]["registers"][1], 0)


class TestAutoDiscovery(unittest.TestCase):
    """Verify predictors are auto-discovered by the API."""

    def test_btb_discovered(self):
        import importlib
        import pkgutil
        import sim.components.branch.predictors as _pred_pkg
        registry = {}
        for info in pkgutil.iter_modules(_pred_pkg.__path__):
            if info.name in ("base", "__init__"):
                continue
            mod = importlib.import_module(f"sim.components.branch.predictors.{info.name}")
            for attr in dir(mod):
                cls = getattr(mod, attr)
                if (isinstance(cls, type) and issubclass(cls, BranchPredictorBase)
                        and cls is not BranchPredictorBase and hasattr(cls, "name")):
                    registry[cls.name] = cls
        self.assertIn("btb", registry)
        # prediction_stage is now an instance attribute, not class
        instance = registry["btb"]()
        self.assertEqual(instance.prediction_stage, "if")


if __name__ == "__main__":
    unittest.main()
