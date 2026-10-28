"""Accuracy and response-time evaluation of the recognition alternatives.

Held-out photos live in data/test/<product_id>/ and are never used as
references, so the measurement is a genuine held-out test.
"""
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

from . import EngineRegistry
from .base import RecognitionError
from .dataset import is_image

ACCURACY_TARGET_PCT = 90.0
RESPONSE_TARGET_SECONDS = 3.0


def test_images(directory):
    root = Path(directory)
    pairs = []
    if not root.is_dir():
        return pairs
    for product_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for path in sorted(f for f in product_dir.iterdir() if f.is_file() and is_image(f)):
            pairs.append((product_dir.name, path))
    return pairs


def _percentile(values, pct):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def evaluate(engine_name, config, limit=None, save=True, warmup=True):
    """Run every test photo through one engine and summarize the result."""
    engine = EngineRegistry(config).get(engine_name)
    pairs = test_images(config["TEST_IMAGE_DIR"])
    if limit:
        pairs = pairs[:limit]
    if not pairs:
        raise RecognitionError(
            "No test photos found. Add held-out photos under data/test/<product_id>/.")

    if warmup:
        try:
            engine.identify(pairs[0][1].read_bytes())
        except RecognitionError:
            pass

    attempts = []
    for truth, path in pairs:
        started = time.perf_counter()
        try:
            match = engine.identify(path.read_bytes())
        except RecognitionError as exc:
            attempts.append({
                "file": str(path), "truth": truth, "predicted": None,
                "correct": False, "confidence": 0.0, "elapsed_ms": 0.0,
                "error": str(exc),
            })
            continue
        elapsed = (time.perf_counter() - started) * 1000
        predicted = match.product_id or ""
        attempts.append({
            "file": str(path),
            "truth": truth,
            "predicted": predicted,
            "correct": predicted == truth,
            "accepted": match.accepted,
            "confidence": round(match.confidence, 1),
            "score": round(match.score, 4),
            "elapsed_ms": round(elapsed, 1),
        })

    times = [a["elapsed_ms"] for a in attempts if "error" not in a]
    correct = sum(1 for a in attempts if a["correct"])
    accuracy = correct / len(attempts) * 100
    mean_ms = statistics.fmean(times) if times else None

    summary = {
        "engine": engine.name,
        "test_dir": str(config["TEST_IMAGE_DIR"]),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "attempts": len(attempts),
        "correct": correct,
        "accuracy_pct": round(accuracy, 2),
        "mean_response_ms": round(mean_ms, 1) if mean_ms is not None else None,
        "median_response_ms": round(statistics.median(times), 1) if times else None,
        "p95_response_ms": round(_percentile(times, 95), 1) if times else None,
        "accuracy_target_pct": ACCURACY_TARGET_PCT,
        "response_target_seconds": RESPONSE_TARGET_SECONDS,
        "meets_accuracy_target": accuracy >= ACCURACY_TARGET_PCT,
        "meets_response_target": (mean_ms / 1000 <= RESPONSE_TARGET_SECONDS) if mean_ms is not None else False,
        "attempts_detail": attempts,
    }

    if save:
        out_dir = Path(config["EVAL_DIR"])
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"eval_{engine.name}_{stamp}.json"
        out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        summary["saved_to"] = str(out_path)
    return summary
