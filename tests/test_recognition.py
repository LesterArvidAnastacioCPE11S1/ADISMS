"""Recognition engine plumbing, thresholds, and the evaluation harness."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.recognition import EngineRegistry, RecognitionError
from app.recognition.evaluate import evaluate
from tests.helpers import PRODUCTS, build_dataset, image_bytes, noise_bytes, unrelated_bytes


class RecognitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.products = Path(self.tmp) / "products"
        self.test_dir = Path(self.tmp) / "test"
        build_dataset(self.products, self.test_dir)
        self.config = {
            "RECOGNITION_ENGINE": "auto",
            "PRODUCT_IMAGE_DIR": str(self.products),
            "TEST_IMAGE_DIR": str(self.test_dir),
            "MODEL_DIR": str(Path(self.tmp) / "models"),
            "EVAL_DIR": str(Path(self.tmp) / "eval"),
            "CNN_MODEL_FILE": "cnn.pt",
            "TEMPLATE_THRESHOLD": 0.45,
            "ORB_MIN_GOOD_MATCHES": 12,
            "CNN_THRESHOLD": 0.6,
        }

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_template_identifies_every_class(self):
        engine = EngineRegistry(self.config).get("template")
        for product_id in PRODUCTS:
            match = engine.identify(image_bytes(product_id, variant=9))
            self.assertTrue(match.accepted, f"{product_id} rejected: {match.score:.3f}")
            self.assertEqual(match.product_id, product_id)
            self.assertGreaterEqual(match.confidence, 45.0)
            self.assertLess(match.elapsed_ms, 3000)

    def test_template_rejects_unrelated_image(self):
        engine = EngineRegistry(self.config).get("template")
        match = engine.identify(noise_bytes())
        self.assertIsNone(match.product_id)
        self.assertFalse(match.accepted)

    def test_template_rejects_detail_free_image(self):
        engine = EngineRegistry(self.config).get("template")
        with self.assertRaises(RecognitionError):
            engine.identify(unrelated_bytes())

    def test_orb_identifies_with_ranked_candidates(self):
        engine = EngineRegistry(self.config).get("orb")
        match = engine.identify(image_bytes("P002", variant=9))
        self.assertEqual(match.product_id, "P002")
        self.assertTrue(match.accepted)
        self.assertEqual(match.candidates[0].product_id, "P002")

    def test_cnn_unavailable_without_model(self):
        registry = EngineRegistry(self.config)
        with self.assertRaises(RecognitionError):
            registry.get("cnn")
        self.assertFalse([e for e in registry.describe() if e["name"] == "cnn"][0]["available"])

    def test_engine_descriptions(self):
        names = [engine["name"] for engine in EngineRegistry(self.config).describe()]
        self.assertEqual(names, ["template", "orb", "cnn"])

    def test_evaluation_reports_accuracy_and_time(self):
        summary = evaluate("template", self.config, save=False)
        self.assertEqual(summary["attempts"], len(PRODUCTS))
        self.assertEqual(summary["accuracy_pct"], 100.0)
        self.assertTrue(summary["meets_accuracy_target"])
        self.assertIsNotNone(summary["mean_response_ms"])
        self.assertTrue(any(a["correct"] for a in summary["attempts_detail"]))

    def test_evaluation_saves_json(self):
        summary = evaluate("template", self.config, save=True)
        self.assertTrue(Path(summary["saved_to"]).is_file())

    def test_evaluation_requires_test_photos(self):
        empty = Path(self.tmp) / "empty"
        empty.mkdir()
        config = dict(self.config, TEST_IMAGE_DIR=str(empty))
        with self.assertRaises(RecognitionError):
            evaluate("template", config, save=False)


if __name__ == "__main__":
    unittest.main()
