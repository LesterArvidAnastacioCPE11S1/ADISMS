"""Alternative B: ORB keypoint and descriptor matching.

ORB keypoints/descriptors are extracted from every reference photo, then
matched against the query with a brute-force Hamming matcher and Lowe's
ratio test. The product with the most good matches wins.
"""
import time

import cv2

from .base import Candidate, Engine, Match, RecognitionError
from .dataset import ImageIndex
from .imaging import decode_image

MIN_KEYPOINTS = 10
FULL_MATCHES = 30   # good matches that count as full confidence


class OrbEngine(Engine):
    name = "orb"
    description = "Alternative B - ORB feature-based recognition"

    def __init__(self, image_dir, min_good_matches=12):
        self.index = ImageIndex(image_dir)
        self.min_good_matches = min_good_matches
        self._detector = cv2.ORB_create(nfeatures=1000, fastThreshold=10)
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        self._refs = {}
        self._refs_signature = None

    def available(self):
        return True

    def _descriptors(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, descriptors = self._detector.detectAndCompute(gray, None)
        return descriptors

    def _references(self):
        images = self.index.images()
        if self.index.signature != self._refs_signature:
            refs = {}
            for product_id, files in images.items():
                descriptors = []
                for path in files:
                    try:
                        des = self._descriptors(decode_image(path.read_bytes()))
                    except (RecognitionError, OSError):
                        continue
                    if des is not None and len(des) >= MIN_KEYPOINTS:
                        descriptors.append(des)
                if descriptors:
                    refs[product_id] = descriptors
            self._refs = refs
            self._refs_signature = self.index.signature
        if not self._refs:
            raise RecognitionError("No usable reference photos found under data/products/.")
        return self._refs

    def _count_good_matches(self, query_des, ref_des):
        pairs = self._matcher.knnMatch(query_des, ref_des, k=2)
        good = 0
        for pair in pairs:
            if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance:
                good += 1
        return good

    def identify(self, image_bytes):
        started = time.perf_counter()
        query_des = self._descriptors(decode_image(image_bytes))
        references = self._references()

        scores = []
        if query_des is not None and len(query_des) >= MIN_KEYPOINTS:
            for product_id, refs in references.items():
                best = max(self._count_good_matches(query_des, ref) for ref in refs)
                scores.append((product_id, float(best), min(100.0, best / FULL_MATCHES * 100)))

        scores.sort(key=lambda item: item[1], reverse=True)
        if scores:
            product_id, score, confidence = scores[0]
        else:
            product_id, score, confidence = None, 0.0, 0.0

        elapsed = (time.perf_counter() - started) * 1000
        accepted = score >= self.min_good_matches
        return Match(
            engine=self.name,
            product_id=product_id if accepted else None,
            confidence=confidence,
            score=score,
            threshold=float(self.min_good_matches),
            accepted=accepted,
            elapsed_ms=elapsed,
            candidates=[Candidate(pid, conf, raw) for pid, raw, conf in scores[:3]],
        )
