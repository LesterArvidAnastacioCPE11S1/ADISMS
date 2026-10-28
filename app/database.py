"""SQLite data layer.

Every sale / delivery is written inside one transaction together with its
stock adjustment, so either both are saved or neither is (ACID).
"""
import re
import sqlite3
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

DB_PATH = "adisms.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email TEXT,
    phone TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('Owner','Employee')),
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    price REAL NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    reorder_level INTEGER NOT NULL DEFAULT 10 CHECK (reorder_level >= 0),
    image_ref TEXT
);
CREATE TABLE IF NOT EXISTS barcodes (
    barcode TEXT PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES products(product_id)
);
CREATE TABLE IF NOT EXISTS sales_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    total REAL NOT NULL,
    items INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price REAL NOT NULL,
    total REAL NOT NULL,
    created_at TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id),
    batch_id INTEGER REFERENCES sales_batches(id)
);
CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    created_at TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id),
    reference TEXT
);
CREATE TABLE IF NOT EXISTS inventory_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL REFERENCES products(product_id),
    type TEXT NOT NULL CHECK (type IN ('SALE','DELIVERY','REGISTER')),
    qty_change INTEGER NOT NULL,
    qty_before INTEGER NOT NULL,
    qty_after INTEGER NOT NULL,
    ref_id INTEGER,
    created_at TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_batches_created ON sales_batches(created_at);
CREATE INDEX IF NOT EXISTS idx_sales_created ON sales(created_at);
CREATE INDEX IF NOT EXISTS idx_deliveries_created ON deliveries(created_at);
CREATE INDEX IF NOT EXISTS idx_tx_product ON inventory_transactions(product_id);
CREATE INDEX IF NOT EXISTS idx_tx_created ON inventory_transactions(created_at);
"""

# Sample products from the clickable prototype (mock data, not real store data).
SEED_PRODUCTS = [
    ("P001", "Lucky Me Pancit Canton", 18, 6, 20, "4800016644801"),
    ("P002", "Silver Swan Soy Sauce 385ml", 28, 34, 15, "4800010001"),
    ("P003", "Datu Puti Vinegar 385ml", 26, 3, 15, "4800010002"),
    ("P004", "Kopiko Brown Coffee 3in1", 9, 48, 30, "4800010003"),
    ("P005", "Safeguard Soap 85g", 42, 12, 10, "4800010004"),
    ("P006", "Bear Brand Milk 33g", 15, 9, 20, "4800010005"),
    ("P007", "Nescafe Classic 25g", 35, 22, 12, "4800010006"),
    ("P008", "Surf Powder Sachet", 11, 60, 25, None),
]


class StockError(ValueError):
    """Raised when a sale, delivery, or registration is rejected."""


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect(path=None):
    conn = sqlite3.connect(path or DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn):
    """Bring an older database up to the current schema without data loss."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    for column in ("email", "phone", "created_at"):
        if column not in columns:
            conn.execute(f"ALTER TABLE users ADD COLUMN {column} TEXT")
    conn.execute("UPDATE users SET created_at=? WHERE created_at IS NULL", (now(),))
    conn.execute("UPDATE users SET email='owner@arviddrygoods.local' "
                 "WHERE username='owner' AND (email IS NULL OR email='')")
    conn.execute("UPDATE users SET email='employee@arviddrygoods.local' "
                 "WHERE username='employee' AND (email IS NULL OR email='')")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email "
                 "ON users(email COLLATE NOCASE) WHERE email IS NOT NULL")

    sale_columns = {row["name"] for row in conn.execute("PRAGMA table_info(sales)")}
    if "batch_id" not in sale_columns:
        conn.execute("ALTER TABLE sales ADD COLUMN batch_id INTEGER REFERENCES sales_batches(id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_batch ON sales(batch_id)")
    delivery_columns = {row["name"] for row in conn.execute("PRAGMA table_info(deliveries)")}
    if "reference" not in delivery_columns:
        conn.execute("ALTER TABLE deliveries ADD COLUMN reference TEXT")
    _backfill_sale_batches(conn)


def _backfill_sale_batches(conn):
    """Give every pre-cart sale its own batch so receipts and reports stay whole."""
    rows = conn.execute(
        "SELECT id, quantity, total, created_at, user_id FROM sales "
        "WHERE batch_id IS NULL ORDER BY id").fetchall()
    for row in rows:
        cur = conn.execute(
            "INSERT INTO sales_batches(total,items,created_at,user_id) VALUES (?,?,?,?)",
            (row["total"], row["quantity"], row["created_at"], row["user_id"]))
        conn.execute("UPDATE sales SET batch_id=? WHERE id=?", (cur.lastrowid, row["id"]))


def init_db(conn, seed=True):
    conn.executescript(SCHEMA)
    _migrate(conn)
    if seed and conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        conn.execute("INSERT INTO users(username,email,phone,password_hash,role,created_at)"
                     " VALUES (?,?,?,?,?,?)",
                     ("owner", "owner@arviddrygoods.local", None,
                      generate_password_hash("owner123"), "Owner", now()))
        conn.execute("INSERT INTO users(username,email,phone,password_hash,role,created_at)"
                     " VALUES (?,?,?,?,?,?)",
                     ("employee", "employee@arviddrygoods.local", None,
                      generate_password_hash("employee123"), "Employee", now()))
        for pid, name, price, stock, reorder, barcode in SEED_PRODUCTS:
            conn.execute("INSERT INTO products(product_id,name,price,stock,reorder_level) VALUES (?,?,?,?,?)",
                         (pid, name, price, stock, reorder))
            if barcode:
                conn.execute("INSERT INTO barcodes VALUES (?,?)", (barcode, pid))


# ---------- accounts ----------
def _user(row):
    if row is None:
        return None
    data = {key: row[key] for key in ("id", "username", "email", "phone", "role", "created_at")}
    return data


def get_user(conn, user_id):
    return _user(conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())


def find_user_for_login(conn, identifier):
    """Look up an account by username or email, case-insensitively."""
    return conn.execute(
        "SELECT * FROM users WHERE username=? COLLATE NOCASE OR email=? COLLATE NOCASE",
        (identifier, identifier)).fetchone()


def create_user(conn, username, email, password, phone=None):
    username, email = (username or "").strip(), (email or "").strip().lower()
    phone = (phone or "").strip() or None
    if not username or not email or not password:
        raise StockError("Username, email and password are required.")
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute("SELECT 1 FROM users WHERE username=? COLLATE NOCASE",
                        (username,)).fetchone():
            raise StockError("That username is already taken.")
        if conn.execute("SELECT 1 FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone():
            raise StockError("That email is already registered.")
        conn.execute(
            "INSERT INTO users(username,email,phone,password_hash,role,created_at)"
            " VALUES (?,?,?,?,?,?)",
            (username, email, phone, generate_password_hash(password), "Employee", now()))
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return get_user(conn, user_id)


def update_user_contact(conn, user_id, email, phone=None):
    email, phone = (email or "").strip().lower(), (phone or "").strip() or None
    if not email:
        raise StockError("Email is required.")
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute("SELECT 1 FROM users WHERE email=? COLLATE NOCASE AND id<>?",
                        (email, user_id)).fetchone():
            raise StockError("That email is already registered.")
        cur = conn.execute("UPDATE users SET email=?, phone=? WHERE id=?",
                           (email, phone, user_id))
        if cur.rowcount == 0:
            raise StockError("Account not found.")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return get_user(conn, user_id)


def update_password(conn, user_id, password_hash):
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, user_id))
    return get_user(conn, user_id)


# ---------- stock updates ----------
def _delivery_timestamp(received_on):
    if not received_on:
        return now()
    value = received_on.strip() if isinstance(received_on, str) else ""
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise StockError("Delivery date must be a valid date.")
    if day > datetime.now().date():
        raise StockError("Delivery date cannot be in the future.")
    return f"{day.isoformat()} {datetime.now():%H:%M:%S}"


def _clean_reference(value):
    reference = value.strip() if isinstance(value, str) else ""
    if len(reference) > 60:
        raise StockError("Delivery reference is too long (max 60 characters).")
    return reference or None


def _apply(conn, product_id, qty, kind, user_id, reference=None, received_on=None):
    """Q_new = Q_current -/+ qty, with record + stock change committed together."""
    if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
        raise StockError("Quantity must be a whole number of at least 1.")
    reference = _clean_reference(reference) if kind == "DELIVERY" else None
    ts = _delivery_timestamp(received_on) if kind == "DELIVERY" else now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        product = conn.execute("SELECT * FROM products WHERE product_id=?", (product_id,)).fetchone()
        if product is None:
            raise StockError(f"Unknown product '{product_id}'.")
        before = product["stock"]
        change = -qty if kind == "SALE" else qty
        after = before + change
        if after < 0:
            raise StockError(f"Rejected: only {before} in stock.")
        if kind == "SALE":
            batch = conn.execute(
                "INSERT INTO sales_batches(total,items,created_at,user_id) VALUES (?,?,?,?)",
                (product["price"] * qty, qty, ts, user_id))
            cur = conn.execute(
                "INSERT INTO sales(product_id,quantity,unit_price,total,created_at,user_id,batch_id)"
                " VALUES (?,?,?,?,?,?,?)",
                (product_id, qty, product["price"], product["price"] * qty, ts, user_id,
                 batch.lastrowid))
        else:
            cur = conn.execute(
                "INSERT INTO deliveries(product_id,quantity,created_at,user_id,reference)"
                " VALUES (?,?,?,?,?)", (product_id, qty, ts, user_id, reference))
        conn.execute("UPDATE products SET stock=? WHERE product_id=?", (after, product_id))
        conn.execute(
            "INSERT INTO inventory_transactions(product_id,type,qty_change,qty_before,qty_after,ref_id,created_at,user_id)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (product_id, kind, change, before, after, cur.lastrowid, ts, user_id))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return get_product(conn, product_id)


def record_sale(conn, product_id, qty, user_id=None):
    return _apply(conn, product_id, qty, "SALE", user_id)


def record_delivery(conn, product_id, qty, user_id=None, reference=None, received_on=None):
    return _apply(conn, product_id, qty, "DELIVERY", user_id, reference, received_on)


def record_cart_sale(conn, items, user_id=None):
    """Record a multi-product sale as one batch; every line and stock change is atomic."""
    wanted = {}
    if not isinstance(items, list) or not items:
        raise StockError("Add at least one product to the sale.")
    for item in items:
        if not isinstance(item, dict):
            raise StockError("Each cart item needs a product and a quantity.")
        product_id = (item.get("product_id") or "").strip()
        qty = item.get("quantity")
        if not product_id:
            raise StockError("Each cart item needs a product.")
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            raise StockError("Each cart quantity must be a whole number of at least 1.")
        wanted[product_id] = wanted.get(product_id, 0) + qty

    conn.execute("BEGIN IMMEDIATE")
    try:
        lines = []
        for product_id, qty in wanted.items():
            row = conn.execute("SELECT * FROM products WHERE product_id=?",
                               (product_id,)).fetchone()
            if row is None:
                raise StockError(f"Unknown product '{product_id}'.")
            if qty > row["stock"]:
                raise StockError(f"{row['name']}: only {row['stock']} in stock.")
            lines.append((row, qty))

        ts = now()
        total = round(sum(row["price"] * qty for row, qty in lines), 2)
        item_count = sum(qty for _, qty in lines)
        batch = conn.execute(
            "INSERT INTO sales_batches(total,items,created_at,user_id) VALUES (?,?,?,?)",
            (total, item_count, ts, user_id))
        batch_id = batch.lastrowid
        receipt_items = []
        for row, qty in lines:
            before = row["stock"]
            after = before - qty
            cur = conn.execute(
                "INSERT INTO sales(product_id,quantity,unit_price,total,created_at,user_id,batch_id)"
                " VALUES (?,?,?,?,?,?,?)",
                (row["product_id"], qty, row["price"], row["price"] * qty, ts, user_id, batch_id))
            conn.execute("UPDATE products SET stock=? WHERE product_id=?",
                         (after, row["product_id"]))
            conn.execute(
                "INSERT INTO inventory_transactions(product_id,type,qty_change,qty_before,qty_after,ref_id,created_at,user_id)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (row["product_id"], "SALE", -qty, before, after, cur.lastrowid, ts, user_id))
            receipt_items.append({
                "product_id": row["product_id"],
                "name": row["name"],
                "quantity": qty,
                "unit_price": row["price"],
                "line_total": round(row["price"] * qty, 2),
                "qty_before": before,
                "qty_after": after,
            })
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    user_row = conn.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
    return {
        "sale_id": batch_id,
        "sale_number": f"S-{batch_id:03d}",
        "created_at": ts,
        "total": total,
        "item_count": item_count,
        "username": user_row["username"] if user_row else None,
        "lines": receipt_items,
    }


# ---------- products ----------
def _row(product):
    data = dict(product)
    data["low_stock"] = data["stock"] <= data["reorder_level"]
    return data


def get_product(conn, product_id):
    row = conn.execute(
        "SELECT p.*, (SELECT barcode FROM barcodes b WHERE b.product_id=p.product_id LIMIT 1) AS barcode "
        "FROM products p WHERE product_id=?", (product_id,)).fetchone()
    return _row(row) if row else None


def search_products(conn, query=""):
    like = f"%{query.strip()}%"
    rows = conn.execute(
        "SELECT * FROM products WHERE name LIKE ? OR product_id LIKE ? ORDER BY product_id",
        (like, like)).fetchall()
    return [_row(row) for row in rows]


def find_by_barcode(conn, code):
    row = conn.execute("SELECT product_id FROM barcodes WHERE barcode=?", (code.strip(),)).fetchone()
    return get_product(conn, row["product_id"]) if row else None


def register_product(conn, product_id, name, price, stock, reorder_level, barcode=None, user_id=None):
    product_id, name = (product_id or "").strip(), (name or "").strip()
    if not product_id or not name:
        raise StockError("Product name and a unique Product ID are required.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", product_id):
        raise StockError("Product ID may only contain letters, numbers, hyphens and underscores (max 32).")
    if price < 0 or stock < 0 or reorder_level < 0:
        raise StockError("Price, quantity and reorder level cannot be negative.")
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute("SELECT 1 FROM products WHERE product_id=?", (product_id,)).fetchone():
            raise StockError(f"Product ID '{product_id}' already exists.")
        if barcode and conn.execute("SELECT 1 FROM barcodes WHERE barcode=?", (barcode,)).fetchone():
            raise StockError("That barcode is already registered.")
        conn.execute("INSERT INTO products(product_id,name,price,stock,reorder_level) VALUES (?,?,?,?,?)",
                     (product_id, name, price, stock, reorder_level))
        if barcode:
            conn.execute("INSERT INTO barcodes VALUES (?,?)", (barcode, product_id))
        if stock:
            conn.execute(
                "INSERT INTO inventory_transactions(product_id,type,qty_change,qty_before,qty_after,created_at,user_id)"
                " VALUES (?,?,?,?,?,?,?)", (product_id, "REGISTER", stock, 0, stock, now(), user_id))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return get_product(conn, product_id)


def delete_product(conn, product_id):
    """Remove a product that has no sales or delivery history."""
    product_id = (product_id or "").strip()
    if not product_id:
        raise StockError("Product ID is required.")
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT * FROM products WHERE product_id=?", (product_id,)).fetchone()
        if row is None:
            raise StockError(f"Product '{product_id}' was not found.")
        history = conn.execute(
            "SELECT (SELECT COUNT(*) FROM sales WHERE product_id=?) + "
            "(SELECT COUNT(*) FROM deliveries WHERE product_id=?)",
            (product_id, product_id)).fetchone()[0]
        if history:
            raise StockError(f"{row['name']} has sales or delivery history and cannot be "
                             "deleted. Keep it so past reports stay accurate.")
        conn.execute("DELETE FROM barcodes WHERE product_id=?", (product_id,))
        conn.execute("DELETE FROM inventory_transactions WHERE product_id=?", (product_id,))
        conn.execute("DELETE FROM products WHERE product_id=?", (product_id,))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return dict(row)


def set_image_ref(conn, product_id, image_ref):
    conn.execute("UPDATE products SET image_ref=? WHERE product_id=?", (image_ref, product_id))


# ---------- monitoring & reports ----------
def low_stock(conn, limit=4):
    """Stock checker: products ranked by stock / reorder level, lowest first."""
    rows = conn.execute(
        "SELECT * FROM products ORDER BY (CAST(stock AS REAL)/NULLIF(reorder_level,0)) ASC, stock ASC LIMIT ?",
        (limit,)).fetchall()
    return [_row(row) for row in rows]


def low_stock_count(conn):
    return conn.execute("SELECT COUNT(*) FROM products WHERE stock <= reorder_level").fetchone()[0]


def stock_summary(conn):
    row = conn.execute(
        "SELECT COUNT(*) AS products, COALESCE(SUM(stock),0) AS units, "
        "COALESCE(SUM(CASE WHEN stock=0 THEN 1 ELSE 0 END),0) AS out_of_stock, "
        "COALESCE(SUM(CASE WHEN stock>0 AND stock<=reorder_level THEN 1 ELSE 0 END),0) AS low_stock "
        "FROM products").fetchone()
    return dict(row)


def stock_attention(conn):
    """Every product at or below its reorder level, out-of-stock first."""
    rows = conn.execute(
        "SELECT * FROM products WHERE stock <= reorder_level "
        "ORDER BY CASE WHEN stock=0 THEN 0 ELSE 1 END, stock ASC, name ASC").fetchall()
    return [_row(row) for row in rows]


def sale_summary(conn, day):
    row = conn.execute(
        "SELECT COALESCE(SUM(total),0) AS total, COUNT(*) AS transactions, "
        "COALESCE(SUM(items),0) AS items FROM sales_batches "
        "WHERE substr(created_at,1,10)=?", (day,)).fetchone()
    return {"total": round(row["total"], 2), "transactions": row["transactions"],
            "items": row["items"]}


def hourly_sales(conn, day):
    """Two-hour sales buckets (8 AM to 8 PM) for one day."""
    labels = ["8–10 AM", "10–12 PM", "12–2 PM", "2–4 PM", "4–6 PM", "6–8 PM"]
    totals = [0.0] * len(labels)
    rows = conn.execute(
        "SELECT CAST(substr(created_at,12,2) AS INTEGER) AS hour, SUM(total) AS total "
        "FROM sales_batches WHERE substr(created_at,1,10)=? GROUP BY hour", (day,)).fetchall()
    for row in rows:
        hour = row["hour"] if row["hour"] is not None else 8
        index = min(len(labels) - 1, max(0, (hour - 8) // 2))
        totals[index] += row["total"] or 0
    return [{"label": labels[i], "total": round(totals[i], 2)} for i in range(len(labels))]


def top_products_for_date(conn, day, limit=6):
    rows = conn.execute(
        "SELECT s.product_id, p.name, SUM(s.quantity) AS quantity, SUM(s.total) AS revenue "
        "FROM sales s JOIN products p ON p.product_id=s.product_id "
        "WHERE substr(s.created_at,1,10)=? "
        "GROUP BY s.product_id ORDER BY quantity DESC, revenue DESC LIMIT ?",
        (day, limit)).fetchall()
    return [dict(row) for row in rows]


def recent_sales(conn, day, limit=8):
    rows = conn.execute(
        "SELECT b.id, b.total, b.items, b.created_at, u.username FROM sales_batches b "
        "LEFT JOIN users u ON u.id=b.user_id "
        "WHERE substr(b.created_at,1,10)=? ORDER BY b.id DESC LIMIT ?",
        (day, limit)).fetchall()
    return [{"sale_id": row["id"], "sale_number": f"S-{row['id']:03d}",
             "total": row["total"], "items": row["items"],
             "created_at": row["created_at"], "username": row["username"]}
            for row in rows]


def product_movements(conn, product_id, limit=6):
    rows = conn.execute(
        "SELECT t.id, t.type, t.qty_change, t.qty_before, t.qty_after, t.created_at, "
        "t.ref_id, u.username, s.batch_id, d.reference "
        "FROM inventory_transactions t "
        "LEFT JOIN users u ON u.id=t.user_id "
        "LEFT JOIN sales s ON t.type='SALE' AND s.id=t.ref_id "
        "LEFT JOIN deliveries d ON t.type='DELIVERY' AND d.id=t.ref_id "
        "WHERE t.product_id=? ORDER BY t.id DESC LIMIT ?", (product_id, limit)).fetchall()
    movements = []
    for row in rows:
        data = dict(row)
        if data["type"] == "SALE":
            data["reference"] = f"S-{data['batch_id']:03d}" if data["batch_id"] else "Sale"
        elif data["type"] == "DELIVERY":
            data["reference"] = data["reference"] or "Delivery"
        else:
            data["reference"] = "Initial stock"
        movements.append(data)
    return movements


def daily_sales(conn, days=7):
    """Sales totals for the last `days` days (including today), zero-filled."""
    start = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    got = {row["d"]: row["t"] for row in conn.execute(
        "SELECT substr(created_at,1,10) AS d, SUM(total) AS t FROM sales "
        "WHERE substr(created_at,1,10)>=? GROUP BY d", (start,))}
    out = []
    for i in range(days):
        day = datetime.now() - timedelta(days=days - 1 - i)
        key = day.strftime("%Y-%m-%d")
        out.append({"date": key, "label": day.strftime("%a"), "total": got.get(key, 0)})
    return out


def sales_today(conn):
    today = datetime.now().strftime("%Y-%m-%d")
    row = conn.execute("SELECT COALESCE(SUM(total),0) AS t FROM sales WHERE substr(created_at,1,10)=?",
                       (today,)).fetchone()
    return row["t"]


def top_products(conn, days=7, limit=5):
    """Best-selling products by quantity and revenue within the period."""
    start = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT s.product_id, p.name, SUM(s.quantity) AS quantity, SUM(s.total) AS revenue "
        "FROM sales s JOIN products p ON p.product_id=s.product_id "
        "WHERE substr(s.created_at,1,10)>=? GROUP BY s.product_id ORDER BY quantity DESC, revenue DESC LIMIT ?",
        (start, limit)).fetchall()
    return [dict(row) for row in rows]


def transaction_history(conn, limit=50):
    rows = conn.execute(
        "SELECT t.id, t.product_id, p.name, t.type, t.qty_change, t.qty_before, t.qty_after, "
        "t.created_at, u.username FROM inventory_transactions t "
        "JOIN products p ON p.product_id=t.product_id "
        "LEFT JOIN users u ON u.id=t.user_id ORDER BY t.id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]


def totals(conn, days=7):
    start = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    sales = conn.execute("SELECT COALESCE(SUM(total),0) AS revenue, COALESCE(SUM(quantity),0) AS items "
                         "FROM sales WHERE substr(created_at,1,10)>=?", (start,)).fetchone()
    deliveries = conn.execute("SELECT COALESCE(SUM(quantity),0) AS items FROM deliveries "
                              "WHERE substr(created_at,1,10)>=?", (start,)).fetchone()
    return {"revenue": sales["revenue"], "items_sold": sales["items"], "items_received": deliveries["items"]}
