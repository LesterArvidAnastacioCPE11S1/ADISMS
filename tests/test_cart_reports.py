"""Cart sales, delivery metadata, stock board, daily reports and schema migration."""
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app import database as db
from tests.helpers import seed_products


class CartSaleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmp, "cart.db"))
        db.init_db(self.conn)
        seed_products(self.conn)
        db.create_owner(self.conn, "tester", "tester@example.com", "password123")

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cart_is_atomic_and_merged(self):
        receipt = db.record_cart_sale(self.conn, [
            {"product_id": "P001", "quantity": 2},
            {"product_id": "P002", "quantity": 1},
            {"product_id": "P001", "quantity": 1},
        ], user_id=1)
        self.assertEqual(receipt["sale_number"], "S-001")
        self.assertEqual(receipt["item_count"], 4)
        self.assertEqual(receipt["total"], 18 * 3 + 28)
        self.assertEqual(len(receipt["lines"]), 2)
        line = [l for l in receipt["lines"] if l["product_id"] == "P001"][0]
        self.assertEqual((line["qty_before"], line["qty_after"]), (6, 3))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sales_batches").fetchone()[0], 1)
        self.assertEqual(db.get_product(self.conn, "P001")["stock"], 3)
        self.assertEqual(db.get_product(self.conn, "P002")["stock"], 33)

    def test_short_line_rolls_back_everything(self):
        with self.assertRaises(db.StockError):
            db.record_cart_sale(self.conn, [
                {"product_id": "P001", "quantity": 1},
                {"product_id": "P003", "quantity": 99},
            ])
        self.assertEqual(db.get_product(self.conn, "P001")["stock"], 6)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sales_batches").fetchone()[0], 0)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM inventory_transactions").fetchone()[0], 0)

    def test_invalid_carts_rejected(self):
        for items in ([], None, [{"product_id": "P001", "quantity": 0}],
                      [{"product_id": "", "quantity": 1}],
                      [{"product_id": "P999", "quantity": 1}],
                      ["P001"]):
            with self.assertRaises(db.StockError):
                db.record_cart_sale(self.conn, items)

    def test_movements_reference_batch_and_delivery(self):
        db.record_cart_sale(self.conn, [{"product_id": "P002", "quantity": 2}], user_id=1)
        db.record_delivery(self.conn, "P002", 5, user_id=1,
                           reference="DR-1028", received_on=datetime.now().strftime("%Y-%m-%d"))
        movements = db.product_movements(self.conn, "P002")
        self.assertEqual(movements[0]["type"], "DELIVERY")
        self.assertEqual(movements[0]["reference"], "DR-1028")
        self.assertEqual(movements[1]["type"], "SALE")
        self.assertEqual(movements[1]["reference"], "S-001")
        self.assertEqual((movements[1]["qty_before"], movements[1]["qty_after"]), (34, 32))


class DeliveryMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmp, "delivery.db"))
        db.init_db(self.conn)
        seed_products(self.conn)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reference_and_date_saved(self):
        day = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        db.record_delivery(self.conn, "P001", 4, reference="  D-012  ", received_on=day)
        row = self.conn.execute("SELECT reference, created_at FROM deliveries").fetchone()
        self.assertEqual(row["reference"], "D-012")
        self.assertTrue(row["created_at"].startswith(day))

    def test_rejects_future_date_and_long_reference(self):
        future = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        with self.assertRaises(db.StockError):
            db.record_delivery(self.conn, "P001", 1, received_on=future)
        with self.assertRaises(db.StockError):
            db.record_delivery(self.conn, "P001", 1, reference="x" * 61)
        with self.assertRaises(db.StockError):
            db.record_delivery(self.conn, "P001", 1, received_on="29/10/2026")
        self.assertEqual(db.get_product(self.conn, "P001")["stock"], 6)


class OldSchemaMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "old.db")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_old_database_is_upgraded_with_batches(self):
        conn = db.connect(self.path)
        conn.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, role TEXT NOT NULL);
            CREATE TABLE products (
                product_id TEXT PRIMARY KEY, name TEXT NOT NULL, price REAL NOT NULL,
                stock INTEGER NOT NULL DEFAULT 0, reorder_level INTEGER NOT NULL DEFAULT 10,
                image_ref TEXT);
            CREATE TABLE sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT NOT NULL,
                quantity INTEGER NOT NULL, unit_price REAL NOT NULL, total REAL NOT NULL,
                created_at TEXT NOT NULL, user_id INTEGER);
            CREATE TABLE deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT NOT NULL,
                quantity INTEGER NOT NULL, created_at TEXT NOT NULL, user_id INTEGER);
            INSERT INTO products VALUES ('P001', 'Old Item', 10, 5, 2, NULL);
            INSERT INTO sales(product_id, quantity, unit_price, total, created_at)
                VALUES ('P001', 2, 10, 20, '2026-01-02 09:00:00');
        """)
        db.init_db(conn)
        sale_columns = {row["name"] for row in conn.execute("PRAGMA table_info(sales)")}
        delivery_columns = {row["name"] for row in conn.execute("PRAGMA table_info(deliveries)")}
        user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        self.assertIn("batch_id", sale_columns)
        self.assertIn("reference", delivery_columns)
        self.assertTrue({"email", "phone", "created_at"} <= user_columns)
        sale = conn.execute("SELECT batch_id FROM sales").fetchone()
        batch = conn.execute("SELECT total, items FROM sales_batches WHERE id=?",
                             (sale["batch_id"],)).fetchone()
        self.assertEqual((batch["total"], batch["items"]), (20, 2))
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(sales)")}
        self.assertIn("idx_sales_batch", indexes)
        conn.close()


class NewApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({
            "DB_PATH": os.path.join(self.tmp, "app.db"),
            "DATA_DIR": self.tmp,
            "PRODUCT_IMAGE_DIR": os.path.join(self.tmp, "products"),
            "TEST_IMAGE_DIR": os.path.join(self.tmp, "test"),
            "MODEL_DIR": os.path.join(self.tmp, "models"),
            "EVAL_DIR": os.path.join(self.tmp, "eval"),
            "TESTING": True,
        })
        self.client = self.app.test_client()
        seed_products(self.app.config["DB_PATH"])
        self.client.post("/api/register", json={
            "username": "owner", "email": "owner@example.com",
            "password": "owner123", "confirm_password": "owner123"})
        self.client.post("/api/login", json={"username": "owner", "password": "owner123"})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cart_sale_receipt_and_stock(self):
        response = self.client.post("/api/sales/cart", json={"items": [
            {"product_id": "P001", "quantity": 1},
            {"product_id": "P002", "quantity": 2},
        ]})
        self.assertEqual(response.status_code, 201)
        receipt = response.get_json()
        self.assertEqual(receipt["total"], 18 + 28 * 2)
        self.assertEqual(receipt["item_count"], 3)
        self.assertEqual(len(receipt["lines"]), 2)
        detail = self.client.get("/api/products/P002").get_json()
        self.assertEqual(detail["stock"], 32)
        self.assertEqual(detail["movements"][0]["reference"], "S-001")

    def test_failed_cart_changes_nothing(self):
        response = self.client.post("/api/sales/cart", json={"items": [
            {"product_id": "P001", "quantity": 1},
            {"product_id": "P003", "quantity": 50},
        ]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/api/products/P001").get_json()["stock"], 6)
        self.assertEqual(self.client.get("/api/reports/day").get_json()["summary"]["total"], 0)

    def test_stock_board(self):
        board = self.client.get("/api/stock").get_json()
        self.assertEqual(board["summary"]["products"], 8)
        self.assertEqual([p["product_id"] for p in board["attention"]],
                         ["P003", "P001", "P006"])
        self.assertEqual(len(board["above"]), 5)

    def test_daily_report(self):
        self.client.post("/api/sales/cart", json={"items": [
            {"product_id": "P002", "quantity": 2},
            {"product_id": "P001", "quantity": 1},
        ]})
        report = self.client.get("/api/reports/day").get_json()
        self.assertRegex(report["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(report["summary"], {"total": 74.0, "transactions": 1, "items": 3})
        self.assertEqual(len(report["hourly"]), 6)
        self.assertEqual(sum(h["total"] for h in report["hourly"]), 74)
        self.assertEqual(report["top_products"][0]["product_id"], "P002")
        self.assertEqual(report["recent"][0]["sale_number"], "S-001")
        self.assertEqual(self.client.get("/api/reports/day?date=29-10-2026").status_code, 400)

    def test_delivery_metadata_over_api(self):
        today = datetime.now().strftime("%Y-%m-%d")
        response = self.client.post("/api/deliveries", json={
            "product_id": "P003", "quantity": 5,
            "reference": "DR-77", "received_on": today})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["stock"], 8)
        movement = self.client.get("/api/products/P003").get_json()["movements"][0]
        self.assertEqual(movement["reference"], "DR-77")
        future = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
        self.assertEqual(self.client.post("/api/deliveries", json={
            "product_id": "P003", "quantity": 1, "received_on": future}).status_code, 400)

    def test_new_endpoints_require_login(self):
        anon = self.app.test_client()
        for path in ("/api/stock", "/api/reports/day", "/api/products/P001"):
            self.assertEqual(anon.get(path).status_code, 401)


class DeleteProductTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({
            "DB_PATH": os.path.join(self.tmp, "app.db"),
            "DATA_DIR": self.tmp,
            "PRODUCT_IMAGE_DIR": os.path.join(self.tmp, "products"),
            "TEST_IMAGE_DIR": os.path.join(self.tmp, "test"),
            "MODEL_DIR": os.path.join(self.tmp, "models"),
            "EVAL_DIR": os.path.join(self.tmp, "eval"),
            "TESTING": True,
        })
        self.client = self.app.test_client()
        seed_products(self.app.config["DB_PATH"])
        self.client.post("/api/register", json={
            "username": "owner", "email": "owner@example.com",
            "password": "owner123", "confirm_password": "owner123"})
        self.client.post("/api/login", json={"username": "owner", "password": "owner123"})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _register(self, pid="P900"):
        response = self.client.post("/api/products", json={
            "name": "Delete Me", "product_id": pid, "price": 12,
            "stock": 4, "reorder_level": 2, "barcode": "9990001"})
        self.assertEqual(response.status_code, 201)

    def test_owner_deletes_product_with_photos_and_barcode(self):
        self._register()
        folder = Path(self.tmp) / "products" / "P900"
        folder.mkdir(parents=True)
        (folder / "photo.jpg").write_bytes(b"photo")
        response = self.client.delete("/api/products/P900")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["product_id"], "P900")
        self.assertEqual(self.client.get("/api/products/P900").status_code, 404)
        self.assertEqual(self.client.get("/api/barcode/9990001").status_code, 404)
        self.assertFalse(folder.exists())

    def test_sold_product_is_kept_for_reports(self):
        self.client.post("/api/sales/cart", json={"items": [
            {"product_id": "P001", "quantity": 1}]})
        response = self.client.delete("/api/products/P001")
        self.assertEqual(response.status_code, 400)
        self.assertIn("history", response.get_json()["error"])
        self.assertEqual(self.client.get("/api/products/P001").status_code, 200)
        self.assertEqual(self.client.get("/api/reports/day").get_json()["summary"]["total"], 18)

    def test_employee_cannot_delete(self):
        self._register()
        self.client.post("/api/staff", json={
            "username": "employee", "email": "employee@example.com",
            "password": "employee123", "confirm_password": "employee123"})
        employee = self.app.test_client()
        employee.post("/api/login", json={
            "username": "employee", "password": "employee123"})
        self.assertEqual(employee.delete("/api/products/P900").status_code, 403)
        self.assertEqual(self.client.get("/api/products/P900").status_code, 200)

    def test_unknown_product_and_anonymous(self):
        self.assertEqual(self.client.delete("/api/products/P999").status_code, 404)
        anon = self.app.test_client()
        self.assertEqual(anon.delete("/api/products/P001").status_code, 401)

    def test_delete_cleans_initial_stock_ledger(self):
        self._register()
        conn = db.connect(os.path.join(self.tmp, "app.db"))
        try:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM inventory_transactions WHERE product_id='P900'"
            ).fetchone()[0], 1)
            db.delete_product(conn, "P900")
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM products WHERE product_id='P900'").fetchone()[0], 0)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM inventory_transactions WHERE product_id='P900'"
            ).fetchone()[0], 0)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM barcodes WHERE product_id='P900'").fetchone()[0], 0)
            with self.assertRaises(db.StockError):
                db.delete_product(conn, "P900")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
