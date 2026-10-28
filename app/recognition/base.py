"""Shared types for the three image-recognition alternatives."""
from dataclasses import dataclass, field


class RecognitionError(RuntimeError):
    """Raised when an image cannot be processed or an engine is unavailable."""


@dataclass
class Candidate:
    product_id: str
    confidence: float   # 0-100
    score: float        # raw engine score


@dataclass
class Match:
    engine: str
    product_id: str | None
    confidence: float          # 0-100
    score: float               # raw engine score
    threshold: float
    accepted: bool
    elapsed_ms: float
    candidates: list = field(default_factory=list)


class Engine:
    name = "base"
    description = ""

    def available(self):
        return False

    def identify(self, image_bytes):
        raise NotImplementedError
