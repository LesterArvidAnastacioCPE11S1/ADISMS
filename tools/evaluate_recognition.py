"""Measure accuracy and response time of the recognition alternatives.

    python tools/evaluate_recognition.py                  # every available engine
    python tools/evaluate_recognition.py --engine orb
    python tools/evaluate_recognition.py --engine template --limit 100

Results are printed as a Markdown table and saved to data/eval/*.json.
The test photos in data/test/<product_id>/ are never used as references,
so these numbers are held-out measurements suitable for Chapter 3.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Config
from app.recognition import EngineRegistry, RecognitionError
from app.recognition.evaluate import evaluate


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate ADISMS recognition engines.")
    parser.add_argument("--engine", default="all", choices=["all", "template", "orb", "cnn"])
    parser.add_argument("--limit", type=int, default=None, help="use only the first N test photos")
    parser.add_argument("--no-save", action="store_true", help="do not write a JSON result file")
    return parser.parse_args()


def main():
    args = parse_args()
    config = Config.as_dict()
    registry = EngineRegistry(config)
    names = ["template", "orb", "cnn"] if args.engine == "all" else [args.engine]

    print(f"Test photos: {config['TEST_IMAGE_DIR']}")
    print()
    print("| Engine | Attempts | Correct | Accuracy | Mean (s) | P95 (s) | Accuracy target | Response target |")
    print("|---|---|---|---|---|---|---|---|")

    for name in names:
        try:
            summary = evaluate(name, config, limit=args.limit, save=not args.no_save)
        except RecognitionError as error:
            print(f"| {name} | - | - | - | - | - | skipped: {error} | - |")
            continue

        print("| {engine} | {attempts} | {correct} | {accuracy_pct:.2f}% | {mean:.3f} | {p95:.3f} | {acc_ok} | {time_ok} |".format(
            engine=summary["engine"],
            attempts=summary["attempts"],
            correct=summary["correct"],
            accuracy_pct=summary["accuracy_pct"],
            mean=(summary["mean_response_ms"] or 0) / 1000,
            p95=(summary["p95_response_ms"] or 0) / 1000,
            acc_ok="met" if summary["meets_accuracy_target"] else "NOT met",
            time_ok="met" if summary["meets_response_target"] else "NOT met",
        ))
        if summary.get("saved_to"):
            print(f"|   | saved to `{summary['saved_to']}` | | | | | | |")
        if summary["attempts"] < 100:
            print(f"|   | Note: only {summary['attempts']} attempts. "
                  "The paper requires at least 100 identification attempts. | | | | | | |")

    print()
    print("Targets: accuracy >= 90%, average response time <= 3 s.")
    print("If these runs used tools/make_demo_dataset.py images, label them as mock/simulation "
          "data in the paper, not as real store performance.")


if __name__ == "__main__":
    main()
