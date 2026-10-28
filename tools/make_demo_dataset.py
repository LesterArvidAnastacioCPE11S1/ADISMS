"""Generate synthetic 'product package' photos so the pipeline can be demoed.

    python tools/make_demo_dataset.py
    python tools/make_demo_dataset.py --clean

Files are named demo_*.png so they are easy to remove. These are MOCK images:
use real photos of Arvid DryGoods products for the accuracy figures reported
in the paper.
"""
import argparse
import io
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

PRODUCTS = {
    "P001": ((178, 34, 34), (255, 245, 220), "PANCIT"),
    "P002": ((20, 60, 140), (250, 250, 250), "SOY SAUCE"),
    "P003": ((24, 110, 70), (255, 255, 255), "VINEGAR"),
    "P004": ((90, 55, 30), (245, 225, 190), "KOPIKO"),
    "P005": ((10, 120, 130), (255, 255, 255), "SAFEGUARD"),
    "P006": ((20, 40, 90), (250, 240, 210), "BEAR BRAND"),
    "P007": ((110, 30, 30), (240, 230, 210), "NESCAFE"),
    "P008": ((40, 90, 120), (240, 245, 250), "SURF"),
}


def draw(product_id, size=(480, 640)):
    background, accent, label = PRODUCTS[product_id]
    index = sorted(PRODUCTS).index(product_id)
    rng = random.Random(3000 + index * 131)
    image = Image.new("RGB", size, background)
    painter = ImageDraw.Draw(image)
    for _ in range(8):
        x = rng.randint(15, size[0] - 150)
        y = rng.randint(15, size[1] - 170)
        w = rng.randint(60, 140)
        h = rng.randint(50, 130)
        fill = accent if rng.random() < 0.62 else tuple(value // 2 for value in background)
        if rng.random() < 0.4:
            painter.ellipse([x, y, x + w, y + h], fill=fill)
        else:
            painter.rectangle([x, y, x + w, y + h], fill=fill)
    painter.rectangle([0, size[1] - 96, size[0], size[1]], fill=accent)
    painter.text((24, size[1] - 68), label, fill=background)
    return image


def save(path, product_id, variant):
    image = draw(product_id)
    if variant:
        image = image.rotate(4 + variant * 2, expand=False)
        image = ImageEnhance.Brightness(image).enhance(1.0 + variant * 0.04)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG")


def clean(folders):
    removed = 0
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in folder.rglob("demo_*.png"):
            path.unlink()
            removed += 1
    print(f"Removed {removed} demo image(s).")


def main():
    parser = argparse.ArgumentParser(description="Create a synthetic demo dataset.")
    parser.add_argument("--products", default="data/products")
    parser.add_argument("--test", default="data/test")
    parser.add_argument("--references", type=int, default=4)
    parser.add_argument("--test-images", type=int, default=2)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    reference_dir, test_dir = Path(args.products), Path(args.test)
    if args.clean:
        clean([reference_dir, test_dir])
        return

    for product_id in PRODUCTS:
        for number in range(args.references):
            save(reference_dir / product_id / f"demo_{product_id}_ref{number}.png", product_id, number)
        for number in range(args.test_images):
            save(test_dir / product_id / f"demo_{product_id}_test{number}.png", product_id, 5 + number)

    print(f"Wrote {len(PRODUCTS) * (args.references + args.test_images)} demo images.")
    print("Reference photos: data/products/<product_id>/  |  held-out: data/test/<product_id>/")
    print("These are MOCK images. Replace them with real product photos before collecting paper results.")


if __name__ == "__main__":
    main()
