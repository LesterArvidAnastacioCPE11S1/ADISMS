"""Alternative A: template matching with normalized correlation.

Every reference photo is resized to a fixed 224x224 grayscale image with
histogram equalization, then compared with the query using
cv2.TM_CCOEFF_NORMED. The best reference score becomes the product score.
"""
import time

import cv2
import numpy as np

from .base import Candidate, Engine, Match, RecognitionError
from .dataset import ImageIndex
from .imaging import decode_image, gray_resized

SIZE = (224, 224)


class TemplateEngine(Engine):
    name = "template"
    description = "Alternative A - template matching (normalized correlation)"

    def __init__(self, image_dir, threshold=0.45):
        self.index = ImageIndex(image_dir)
        self.threshold = threshold
        self._refs = {}
        self._refs_signature = None

    def available(self):
        return True

    def _references(self):
        images = self.index.images()
        if self.index.signature != self._refs_signature:
            refs = {}
            for product_id, files in images.items():
                prepared = []
                for path in files:
                    try:
                        gray = gray_resized(decode_image(path.read_bytes()), SIZE)
                    except (RecognitionError, OSError):
                        continue
                    if float(gray.std()) >= 1.0:   # skip blank / near-uniform photos
                        prepared.append(gray)
                if prepared:
                    refs[product_id] = prepared
            self._refs = refs
            self._refs_signature = self.index.signature
        if not self._refs:
            raise RecognitionError("No reference photos found under data/products/.")
        return self._refs

    def identify(self, image_bytes):
        started = time.perf_counter()
        query = gray_resized(decode_image(image_bytes), SIZE)
        if float(query.std()) < 1.0:
            raise RecognitionError("The image has no visible detail. Take another photo in better light.")
        references = self._references()

        scores = []
        for product_id, templates in references.items():
            best = 0.0
            for template in templates:
                raw = cv2.matchTemplate(template, query, cv2.TM_CCOEFF_NORMED)[0, 0]
                best = max(best, float(np.nan_to_num(raw)))
            scores.append((product_id, best, max(0.0, min(1.0, best)) * 100))

        scores.sort(key=lambda item: item[1], reverse=True)
        product_id, score, confidence = scores[0]
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
            candidates=[Candidate(pid, conf, raw) for pid, raw, conf in scores[:3]],
        )
