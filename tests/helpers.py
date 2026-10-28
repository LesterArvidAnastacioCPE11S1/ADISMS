"""Synthetic package photos for deterministic engine tests.

These are mock images only. Never use them for the accuracy figures reported
in the paper; collect real photos of the store's products for that.
"""
import io
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

PRODUCTS = {
    "P001": {"bg": (178, 34, 34), "accent": (255, 245, 220), "label": "PANCIT"},
    "P002": {"bg": (20, 60, 140), "accent": (250, 250, 250), "label": "SOY"},
    "P003": {"bg": (24, 110, 70), "accent": (255, 255, 255), "label": "VINEGAR"},
}


def _draw(product_id, size=(480, 640)):
    spec = PRODUCTS[product_id]
    index = sorted(PRODUCTS).index(product_id)
    rng = random.Random(2000 + index * 97)
    image = Image.new("RGB", size, spec["bg"])
    draw = ImageDraw.Draw(image)
    for _ in range(7):
        x = rng.randint(20, size[0] - 140)
        y = rng.randint(20, size[1] - 160)
        w = rng.randint(60, 130)
        h = rng.randint(50, 120)
        fill = spec["accent"] if rng.random() < 0.6 else tuple(v // 2 for v in spec["bg"])
        if rng.random() < 0.4:
            draw.ellipse([x, y, x + w, y + h], fill=fill)
        else:
            draw.rectangle([x, y, x + w, y + h], fill=fill)
    draw.rectangle([0, size[1] - 90, size[0], size[1]], fill=spec["accent"])
    draw.text((24, size[1] - 64), spec["label"], fill=spec["bg"])
    return image


def image_bytes(product_id, variant=0):
    image = _draw(product_id)
    if variant:
        image = image.rotate(5 + variant % 3, expand=False)
        image = ImageEnhance.Brightness(image).enhance(1.08)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def unrelated_bytes():
    image = Image.new("RGB", (480, 640), (0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def noise_bytes(seed=123):
    rng = random.Random(seed)
    size = (240, 320)
    image = Image.new("RGB", size)
    image.putdata([(rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
                   for _ in range(size[0] * size[1])])
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def save_package(path, product_id, variant=0):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image_bytes(product_id, variant))
    return path


def build_dataset(reference_dir, test_dir, references=2):
    for product_id in PRODUCTS:
        for variant in range(references):
            save_package(Path(reference_dir) / product_id / f"{product_id}_ref{variant}.png",
                         product_id, variant)
        save_package(Path(test_dir) / product_id / f"{product_id}_test.png", product_id, 9)
