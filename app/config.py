"""Application configuration. Every value can be overridden from the environment."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _path(env_name, default):
    return str(Path(os.environ.get(env_name, str(default))).expanduser())


class Config:
    SECRET_KEY = os.environ.get("ADISMS_SECRET_KEY", "dev-secret-change-me")

    DB_PATH = _path("ADISMS_DB", BASE_DIR / "adisms.db")
    DATA_DIR = _path("ADISMS_DATA_DIR", BASE_DIR / "data")
    PRODUCT_IMAGE_DIR = os.path.join(DATA_DIR, "products")   # reference / training photos
    TEST_IMAGE_DIR = os.path.join(DATA_DIR, "test")         # held-out evaluation photos
    MODEL_DIR = os.path.join(DATA_DIR, "models")            # cnn.pt + class map
    EVAL_DIR = os.path.join(DATA_DIR, "eval")               # evaluation result JSON

    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

    # Recognition alternatives
    RECOGNITION_ENGINE = os.environ.get("ADISMS_ENGINE", "auto")  # auto | template | orb | cnn
    CNN_MODEL_FILE = os.environ.get("ADISMS_CNN_MODEL", "cnn.pt")
    TEMPLATE_THRESHOLD = float(os.environ.get("ADISMS_TEMPLATE_THRESHOLD", "0.45"))
    ORB_MIN_GOOD_MATCHES = int(os.environ.get("ADISMS_ORB_MIN_MATCHES", "12"))
    CNN_THRESHOLD = float(os.environ.get("ADISMS_CNN_THRESHOLD", "0.60"))

    # Dashboard / reporting
    SALES_CHART_DAYS = 7
    LOW_STOCK_DISPLAY_LIMIT = 4
    RECENT_TRANSACTIONS_LIMIT = 15

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    @classmethod
    def as_dict(cls):
        return {key: getattr(cls, key) for key in dir(cls) if key.isupper()}
