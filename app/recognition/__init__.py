"""Product-identification alternatives (A/B/C) behind one interface.

    template -> Alternative A: normalized correlation / template matching
    orb      -> Alternative B: ORB keypoint + descriptor matching
    cnn      -> Alternative C: MobileNetV3 transfer learning

"auto" picks CNN when a trained model is available, otherwise template matching.
"""
from .base import Candidate, Engine, Match, RecognitionError
from .cnn import CnnEngine
from .orb import OrbEngine
from .template import TemplateEngine

ENGINE_NAMES = ("template", "orb", "cnn")

DESCRIPTIONS = {
    "template": "Alternative A - template matching (normalized correlation)",
    "orb": "Alternative B - ORB feature-based recognition",
    "cnn": "Alternative C - CNN with transfer learning",
}


class EngineRegistry:
    """Creates and caches one instance of each engine per Flask app."""

    def __init__(self, config):
        self.config = config
        self._cache = {}

    def build(self, name):
        if name == "template":
            return TemplateEngine(self.config["PRODUCT_IMAGE_DIR"], self.config["TEMPLATE_THRESHOLD"])
        if name == "orb":
            return OrbEngine(self.config["PRODUCT_IMAGE_DIR"], self.config["ORB_MIN_GOOD_MATCHES"])
        if name == "cnn":
            return CnnEngine(self.config["MODEL_DIR"], self.config["CNN_MODEL_FILE"],
                             self.config["CNN_THRESHOLD"])
        raise RecognitionError(f"Unknown recognition engine '{name}'.")

    def get(self, name=None):
        name = (name or self.config.get("RECOGNITION_ENGINE") or "auto").strip().lower()
        if name == "auto":
            name = "cnn" if self.build("cnn").available() else "template"
        if name not in ENGINE_NAMES:
            raise RecognitionError(f"Unknown recognition engine '{name}'.")
        engine = self._cache.get(name)
        if engine is None:
            engine = self.build(name)
            if not engine.available():
                raise RecognitionError(
                    f"The '{name}' engine is not available. "
                    + ("Train the CNN with ml/train_cnn.py." if name == "cnn"
                       else "Add reference photos under data/products/."))
            self._cache[name] = engine
        return engine

    def describe(self):
        out = []
        for name in ENGINE_NAMES:
            try:
                available = self.build(name).available()
            except Exception:
                available = False
            out.append({"name": name, "available": available, "description": DESCRIPTIONS[name]})
        return out
