"""Move a share of each product's photos into the held-out test set.

    python ml/split_dataset.py --ratio 0.3

Photos move from data/products/<product_id>/ to data/test/<product_id>/.
The reference folder is used by template matching and ORB and for CNN
training; the test folder is only used for evaluation, so results are honest.
"""
import argparse
import random
import shutil
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="data/products")
    parser.add_argument("--dest", default="data/test")
    parser.add_argument("--ratio", type=float, default=0.3, help="share of photos moved to the test set")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    source, dest = Path(args.source), Path(args.dest)
    if not source.is_dir():
        raise SystemExit(f"Source folder not found: {source}")
    rng = random.Random(args.seed)
    moved = 0

    for product_dir in sorted(p for p in source.iterdir() if p.is_dir()):
        photos = sorted(f for f in product_dir.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS)
        if len(photos) < 2:
            if photos:
                print(f"{product_dir.name}: only {len(photos)} photo(s), skipped")
            continue
        count = max(1, round(len(photos) * args.ratio))
        count = min(count, len(photos) - 1)          # always keep at least one reference photo
        chosen = rng.sample(photos, count)
        target = dest / product_dir.name
        if not args.dry_run:
            target.mkdir(parents=True, exist_ok=True)
        for photo in chosen:
            print(f"{'would move' if args.dry_run else 'move'} {photo} -> {target}")
            if not args.dry_run:
                shutil.move(str(photo), str(target / photo.name))
            moved += 1

    print(f"{moved} photo(s) {'to move' if args.dry_run else 'moved'} to {dest}")
    if not args.dry_run:
        print("Re-run template matching / ORB / CNN evaluation to refresh the results.")


if __name__ == "__main__":
    main()
