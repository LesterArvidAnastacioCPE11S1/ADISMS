"""OpenCV helpers shared by the non-learning engines."""
import cv2
import numpy as np

from .base import RecognitionError


def decode_image(data):
    if not data:
        raise RecognitionError("The image is empty.")
    array = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise RecognitionError("Could not read the uploaded image.")
    return image


def gray_resized(image, size=(224, 224), equalize=True):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, size, interpolation=cv2.INTER_AREA)
    return cv2.equalizeHist(gray) if equalize else gray
