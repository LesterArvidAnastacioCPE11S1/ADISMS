"""Reference-image index built from data/products/<product_id>/<photo>."""
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def is_image(path):
    return path.suffix.lower() in IMAGE_EXTENSIONS


class ImageIndex:
    """Maps product_id -> list of image paths, rescanned only when files change."""

    def __init__(self, root):
        self.root = Path(root)
        self._images = {}
        self.signature = None

    def images(self):
        images, signature = self._scan()
        if signature != self.signature:
            self._images, self.signature = images, signature
        return self._images

    def count(self):
        return sum(len(files) for files in self.images().values())

    def _scan(self):
        images = {}
        signature = []
        if self.root.is_dir():
            product_dirs = sorted(p for p in self.root.iterdir() if p.is_dir())
            for product_dir in product_dirs:
                files = sorted(f for f in product_dir.iterdir() if f.is_file() and is_image(f))
                if files:
                    images[product_dir.name] = files
                    for f in files:
                        stat = f.stat()
                        signature.append((f.name, stat.st_mtime_ns, stat.st_size))
        return images, tuple(signature)
