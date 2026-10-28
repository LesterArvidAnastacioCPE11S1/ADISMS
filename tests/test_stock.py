"""Stock update accuracy: 100% correct, including 100 random transactions."""
import os
import random
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app import database as db


class StockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "stock.db")
        self.conn = db.connect(self.path)
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sale_subtracts(self):
        self.assertEqual(db.record_sale(self.conn, "P002", 4)["stock"], 30)

    def test_delivery_adds(self):
        self.assertEqual(db.record_delivery(self.conn, "P001", 10)["stock"], 16)

    def test_negative_stock_rejected_and_unchanged(self):
        with self.assertRaises(db.StockError):
            db.record_sale(self.conn, "P003", 4)   # only 3 in stock
        self.assertEqual(db.get_product(self.conn, "P003")["stock"], 3)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 0)

    def test_invalid_quantities_rejected(self):
        for bad in (0, -5, 1.5, "3", None, True):
            with self.assertRaises(db.StockError):
                db.record_sale(self.conn, "P001", bad)

    def test_unknown_product_rejected(self):
        with self.assertRaises(db.StockError):
            db.record_delivery(self.conn, "P999", 1)

    def test_register_duplicate_rejected(self):
        with self.assertRaises(db.StockError):
            db.register_product(self.conn, "P001", "Dup", 1, 1, 1)

    def test_register_rejects_unsafe_product_id(self):
        with self.assertRaises(db.StockError):
            db.register_product(self.conn, "../evil", "Bad", 1, 1, 1)

    def test_register_and_barcode_lookup(self):
        db.register_product(self.conn, "P009", "Test Item", 10, 5, 3, barcode="123")
        self.assertEqual(db.find_by_barcode(self.conn, "123")["product_id"], "P009")
        self.assertEqual(db.get_product(self.conn, "P009")["stock"], 5)

    def test_low_stock_ranking(self):
        ranked = [p["product_id"] for p in db.low_stock(self.conn, 3)]
        self.assertEqual(ranked[0], "P003")     # 3/15 is the lowest ratio

    def test_100_random_transactions_match_expected(self):
        random.seed(1)
        expected = {p["product_id"]: p["stock"] for p in db.search_products(self.conn)}
        ok = total = 0
        for _ in range(100):
            pid = random.choice(list(expected))
            qty = random.randint(1, 15)
            sale = random.random() < 0.5
            total += 1
            try:
                got = (db.record_sale if sale else db.record_delivery)(self.conn, pid, qty)["stock"]
            except db.StockError:
                ok += expected[pid] < qty and sale
                continue
            expected[pid] += -qty if sale else qty
            ok += got == expected[pid]
        self.assertEqual(ok, total)
        for pid, stock in expected.items():
            last = self.conn.execute("SELECT qty_after FROM inventory_transactions WHERE product_id=? "
                                     "ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
            if last:
                self.assertEqual(last[0], stock)


class ApiStockTests(unittest.TestCase):
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

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/dashboard").status_code, 401)

    def test_login_sale_dashboard(self):
        self.assertEqual(self.client.post(
            "/api/login", json={"username": "owner", "password": "bad"}).status_code, 401)
        self.assertEqual(self.client.post(
            "/api/login", json={"username": "owner", "password": "owner123"}).status_code, 200)
        response = self.client.post("/api/sales", json={"product_id": "P002", "quantity": 2})
        self.assertEqual(response.get_json()["stock"], 32)
        self.assertEqual(self.client.post(
            "/api/sales", json={"product_id": "P003", "quantity": 99}).status_code, 400)
        dashboard = self.client.get("/api/dashboard").get_json()
        self.assertEqual(dashboard["sales_today"], 56)   # 2 x 28
        self.assertEqual(len(dashboard["daily_sales"]), 7)

    def test_delivery_updates_stock(self):
        self.client.post("/api/login", json={"username": "employee", "password": "employee123"})
        response = self.client.post("/api/deliveries", json={"product_id": "P003", "quantity": 5})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["stock"], 8)


if __name__ == "__main__":
    unittest.main()
