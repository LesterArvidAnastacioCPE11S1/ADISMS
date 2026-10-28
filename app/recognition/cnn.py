"""Alternative C: CNN image classification with transfer learning.

The model is trained by ml/train_cnn.py and stored as data/models/cnn.pt
with the class order (product IDs) inside the checkpoint. PyTorch is imported
lazily so the rest of the system runs without it installed.
"""
import io
import time
from pathlib import Path

from .base import Candidate, Engine, Match, RecognitionError

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


class CnnEngine(Engine):
    name = "cnn"
    description = "Alternative C - CNN with transfer learning"

    def __init__(self, model_dir, model_file="cnn.pt", threshold=0.6):
        self.model_path = Path(model_dir) / model_file
        self.threshold = threshold
        self._model = None
        self._classes = []
        self._preprocess = None
        self._torch = None
        self._load_error = None

    def available(self):
        if not self.model_path.is_file():
            return False
        try:
            import torch  # noqa: F401
            import torchvision  # noqa: F401
        except Exception:
            return False
        return True

    def _load(self):
        if self._model is not None:
            return
        if self._load_error:
            raise RecognitionError(self._load_error)
        try:
            import torch
            import torchvision
            from torchvision import transforms
        except Exception as exc:
            self._load_error = "PyTorch/torchvision are not installed on this machine."
            raise RecognitionError(self._load_error) from exc
        if not self.model_path.is_file():
            self._load_error = f"CNN model not found: {self.model_path}"
            raise RecognitionError(self._load_error)

        checkpoint = torch.load(self.model_path, map_location="cpu")
        arch = checkpoint.get("arch", "mobilenet_v3_small")
        classes = checkpoint["classes"]
        model = getattr(torchvision.models, arch)(weights=None)
        if arch.startswith("mobilenet"):
            model.classifier[3] = torch.nn.Linear(model.classifier[3].in_features, len(classes))
        elif arch.startswith("resnet"):
            model.fc = torch.nn.Linear(model.fc.in_features, len(classes))
        else:
            raise RecognitionError(f"Unsupported CNN architecture '{arch}'.")
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()

        self._torch = torch
        self._model = model
        self._classes = classes
        self._preprocess = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ])

    def identify(self, image_bytes):
        self._load()
        from PIL import Image

        started = time.perf_counter()
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception as exc:
            raise RecognitionError("Could not read the uploaded image.") from exc

        tensor = self._preprocess(image).unsqueeze(0)
        with self._torch.no_grad():
            probabilities = self._torch.softmax(self._model(tensor), dim=1)[0]
        top = self._torch.topk(probabilities, k=min(3, len(self._classes)))
        ranked = [
            (self._classes[int(index)], float(probability) * 100, float(probability))
            for probability, index in zip(top.values, top.indices)
        ]

        product_id, confidence, score = ranked[0]
        elapsed = (time.perf_counter() - started) * 1000
        accepted = score >= self.threshold
        return Match(
            engine=self.name,
            product_id=product_id if accepted else None,
            confidence=confidence,
            score=score,
            threshold=self.threshold,
            accepted=accepted,
            elapsed_ms=elapsed,
            candidates=[Candidate(pid, conf, raw) for pid, conf, raw in ranked],
        )
