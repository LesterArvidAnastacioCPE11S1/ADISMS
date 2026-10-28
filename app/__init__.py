"""ADISMS application factory."""
import os

from flask import Flask, jsonify

from . import database as db
from .config import Config
from .db_session import close_conn


def create_app(test_config=None):
    app = Flask(__name__, static_folder="static", static_url_path="/static")

    config = Config.as_dict()
    if test_config:
        config.update(test_config)
    app.config.from_mapping(config)

    for key in ("DATA_DIR", "PRODUCT_IMAGE_DIR", "TEST_IMAGE_DIR", "MODEL_DIR", "EVAL_DIR"):
        os.makedirs(app.config[key], exist_ok=True)

    conn = db.connect(app.config["DB_PATH"])
    try:
        db.init_db(conn)
    finally:
        conn.close()

    app.teardown_appcontext(close_conn)

    from .api import bp as api_bp
    from .auth import bp as auth_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.errorhandler(db.StockError)
    def handle_stock_error(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(413)
    def handle_too_large(_):
        return jsonify(error="Image is too large (maximum 8 MB)."), 413

    return app
