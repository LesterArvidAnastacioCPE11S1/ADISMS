"""HTTP API consumed by the web interface."""
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file, session

from . import database as db
from .auth import login_required, role_required
from .db_session import get_conn
from .recognition import EngineRegistry, RecognitionError

bp = Blueprint("api", __name__, url_prefix="/api")


# ---------- helpers ----------
def int_field(data, key):
    try:
        value = data[key]
        if isinstance(value, bool) or int(value) != float(value):
            raise ValueError
        return int(value)
    except (KeyError, TypeError, ValueError):
        raise db.StockError(f"'{key}' must be a whole number.")


def _days(value, default=7):
    try:
        days = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(90, days))


def _registry():
    registry = current_app.extensions.get("adis_engines")
    if registry is None:
        registry = current_app.extensions["adis_engines"] = EngineRegistry(current_app.config)
    return registry


def _image_folder(product_id):
    return Path(current_app.config["PRODUCT_IMAGE_DIR"]) / product_id


def _has_image(product_id):
    folder = _image_folder(product_id)
    if not folder.is_dir():
        return False
    allowed = current_app.config["ALLOWED_IMAGE_EXTENSIONS"]
    return any(f.is_file() and f.suffix.lower() in allowed for f in folder.iterdir())


def _with_image(product):
    product = dict(product)
    product["image_url"] = (f"/api/products/{product['product_id']}/image"
                            if _has_image(product["product_id"]) else None)
    return product


# ---------- dashboard ----------
@bp.get("/dashboard")
@login_required
def dashboard():
    conn = get_conn()
    account = db.get_user(conn, session["user_id"])
    today = datetime.now().strftime("%Y-%m-%d")
    sales = db.daily_sales(conn, current_app.config["SALES_CHART_DAYS"])
    summary = db.sale_summary(conn, today)
    counts = db.stock_summary(conn)
    return jsonify(
        user=account["username"],
        role=account["role"],
        email=account["email"],
        phone=account["phone"],
        sales_today=summary["total"],
        transactions_today=summary["transactions"],
        items_sold_today=summary["items"],
        products_count=counts["products"],
        units_in_stock=counts["units"],
        out_of_stock_count=counts["out_of_stock"],
        stock_low_count=counts["low_stock"],
        low_stock_count=db.low_stock_count(conn),
        daily_sales=sales,
        hourly_sales=db.hourly_sales(conn, today),
        stock_checker=[_with_image(p) for p in db.stock_attention(conn)[:4]],
    )


# ---------- products / identification ----------
@bp.get("/products")
@login_required
def products():
    return jsonify([_with_image(p) for p in db.search_products(get_conn(), request.args.get("q", ""))])


@bp.get("/products/<product_id>")
@login_required
def product(product_id):
    conn = get_conn()
    found = db.get_product(conn, product_id)
    if not found:
        return jsonify(error="Product not found."), 404
    data = _with_image(found)
    data["movements"] = db.product_movements(conn, product_id)
    return jsonify(data), 200


@bp.get("/products/<product_id>/image")
@login_required
def product_image(product_id):
    folder = _image_folder(product_id)
    allowed = current_app.config["ALLOWED_IMAGE_EXTENSIONS"]
    if folder.is_dir():
        for path in sorted(f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in allowed):
            return send_file(path, max_age=60)
    return jsonify(error="No photo for this product."), 404


@bp.post("/products/<product_id>/images")
@login_required
def upload_product_images(product_id):
    if not db.get_product(get_conn(), product_id):
        return jsonify(error="Product not found."), 404

    uploads = [f for f in request.files.getlist("image") if f and f.filename]
    if not uploads:
        raise db.StockError("Attach at least one photo.")
    if len(uploads) > 8:
        raise db.StockError("You can upload up to 8 photos per request.")

    allowed = current_app.config["ALLOWED_IMAGE_EXTENSIONS"]
    for upload in uploads:
        if Path(upload.filename).suffix.lower() not in allowed:
            raise db.StockError(f"'{upload.filename}' is not a supported image (jpg, png, webp, bmp).")

    folder = _image_folder(product_id)
    folder.mkdir(parents=True, exist_ok=True)
    saved = []
    for upload in uploads:
        suffix = Path(upload.filename).suffix.lower()
        name = f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}{suffix}"
        upload.save(folder / name)
        saved.append(name)

    if not db.get_product(get_conn(), product_id).get("image_ref"):
        db.set_image_ref(get_conn(), product_id, saved[0])
    return jsonify(product=_with_image(db.get_product(get_conn(), product_id)), images=saved), 201


@bp.get("/barcode/<code>")
@login_required
def barcode(code):
    found = db.find_by_barcode(get_conn(), code)
    return (jsonify(_with_image(found)), 200) if found else (jsonify(error="Product could not be identified."), 404)


@bp.post("/products")
@login_required
def register():
    data = request.get_json(silent=True) or {}
    try:
        price = float(data.get("price", 0))
    except (TypeError, ValueError):
        raise db.StockError("Price must be a number.")
    product = db.register_product(
        get_conn(),
        data.get("product_id"),
        data.get("name"),
        price,
        int_field(data, "stock") if "stock" in data else 0,
        int_field(data, "reorder_level") if "reorder_level" in data else 10,
        (data.get("barcode") or "").strip() or None,
        session["user_id"],
    )
    return jsonify(_with_image(product)), 201


@bp.delete("/products/<product_id>")
@login_required
@role_required("Owner")
def delete_product(product_id):
    conn = get_conn()
    if not db.get_product(conn, product_id):
        return jsonify(error="Product not found."), 404
    removed = db.delete_product(conn, product_id)
    shutil.rmtree(_image_folder(product_id), ignore_errors=True)
    return jsonify(ok=True, product_id=removed["product_id"], name=removed["name"]), 200


# ---------- sales & deliveries ----------
@bp.post("/sales")
@login_required
def sale():
    data = request.get_json(silent=True) or {}
    product = db.record_sale(get_conn(), data.get("product_id"),
                             int_field(data, "quantity"), session["user_id"])
    return jsonify(_with_image(product)), 201


@bp.post("/sales/cart")
@login_required
def sale_cart():
    data = request.get_json(silent=True) or {}
    receipt = db.record_cart_sale(get_conn(), data.get("items"), session["user_id"])
    return jsonify(receipt), 201


@bp.post("/deliveries")
@login_required
def delivery():
    data = request.get_json(silent=True) or {}
    product = db.record_delivery(get_conn(), data.get("product_id"),
                                 int_field(data, "quantity"), session["user_id"],
                                 reference=data.get("reference"),
                                 received_on=data.get("received_on"))
    return jsonify(_with_image(product)), 201


@bp.get("/stock")
@login_required
def stock():
    conn = get_conn()
    attention = [_with_image(p) for p in db.stock_attention(conn)]
    attention_ids = {p["product_id"] for p in attention}
    everything = [_with_image(p) for p in db.search_products(conn)]
    return jsonify(attention=attention,
                   above=[p for p in everything if p["product_id"] not in attention_ids],
                   summary=db.stock_summary(conn))


# ---------- reports ----------
@bp.get("/transactions")
@login_required
def transactions():
    limit = _days(request.args.get("limit", 50), 50)
    return jsonify(db.transaction_history(get_conn(), limit))


@bp.get("/reports/summary")
@login_required
def report_summary():
    days = _days(request.args.get("days", 7))
    conn = get_conn()
    return jsonify(
        days=days,
        daily_sales=db.daily_sales(conn, days),
        top_products=db.top_products(conn, days, 5),
        totals=db.totals(conn, days),
        low_stock_count=db.low_stock_count(conn),
        transactions=db.transaction_history(conn, current_app.config["RECENT_TRANSACTIONS_LIMIT"]),
    )


@bp.get("/reports/day")
@login_required
def report_day():
    value = (request.args.get("date") or "").strip() or datetime.now().strftime("%Y-%m-%d")
    try:
        day = datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise db.StockError("Date must be in YYYY-MM-DD format.")
    conn = get_conn()
    return jsonify(
        date=day,
        summary=db.sale_summary(conn, day),
        hourly=db.hourly_sales(conn, day),
        top_products=db.top_products_for_date(conn, day, 6),
        recent=db.recent_sales(conn, day, 8),
    )


# ---------- product recognition ----------
@bp.get("/recognition/engines")
@login_required
def recognition_engines():
    return jsonify(default=current_app.config["RECOGNITION_ENGINE"], engines=_registry().describe())


@bp.post("/recognize")
@login_required
def recognize():
    upload = request.files.get("image")
    if upload is None or not upload.filename:
        raise db.StockError("Attach an image file.")
    image_bytes = upload.read()
    if not image_bytes:
        raise db.StockError("The uploaded image is empty.")

    requested = (request.form.get("engine") or "auto").strip().lower()
    try:
        engine = _registry().get(requested)
    except RecognitionError as exc:
        return jsonify(error=str(exc)), 503

    try:
        match = engine.identify(image_bytes)
    except RecognitionError as exc:
        return jsonify(error=str(exc)), 400

    conn = get_conn()
    product = _with_image(db.get_product(conn, match.product_id)) if match.product_id else None
    candidates = []
    for candidate in match.candidates:
        entry = {"product_id": candidate.product_id,
                 "confidence": round(candidate.confidence, 1)}
        row = db.get_product(conn, candidate.product_id)
        if row:
            entry["name"] = row["name"]
        candidates.append(entry)

    return jsonify(
        engine=engine.name,
        accepted=match.accepted,
        product=product,
        confidence=round(match.confidence, 1),
        score=round(match.score, 4),
        threshold=match.threshold,
        elapsed_ms=round(match.elapsed_ms, 1),
        candidates=candidates,
    )
