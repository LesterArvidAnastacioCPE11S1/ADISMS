"""API-level tests: auth, products, photos, reports, recognition."""
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from tests.helpers import build_dataset, image_bytes, seed_products


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.products_dir = os.path.join(self.tmp, "products")
        self.test_dir = os.path.join(self.tmp, "test")
        build_dataset(self.products_dir, self.test_dir, references=1)
        self.app = create_app({
            "DB_PATH": os.path.join(self.tmp, "api.db"),
            "DATA_DIR": self.tmp,
            "PRODUCT_IMAGE_DIR": self.products_dir,
            "TEST_IMAGE_DIR": self.test_dir,
            "MODEL_DIR": os.path.join(self.tmp, "models"),
            "EVAL_DIR": os.path.join(self.tmp, "eval"),
            "TESTING": True,
        })
        self.client = self.app.test_client()
        seed_products(self.app.config["DB_PATH"])
        self.client.post("/api/register", json={
            "username": "owner", "email": "owner@example.com",
            "password": "owner123", "confirm_password": "owner123"})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def login(self, username="owner", password="owner123"):
        return self.client.post("/api/login", json={"username": username, "password": password})

    def test_login_and_logout(self):
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get("/api/me").get_json()["role"], "Owner")
        self.assertEqual(self.client.post("/api/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/me").status_code, 401)

    def test_product_search_and_barcode(self):
        self.login()
        products = self.client.get("/api/products?q=Kopiko").get_json()
        self.assertEqual(products[0]["product_id"], "P004")
        self.assertEqual(self.client.get("/api/barcode/4800010001").get_json()["product_id"], "P002")
        self.assertEqual(self.client.get("/api/barcode/nope").status_code, 404)

    def test_register_product_and_reject_duplicate(self):
        self.login()
        response = self.client.post("/api/products", json={
            "product_id": "P009", "name": "Test Item", "price": 10, "stock": 5,
            "reorder_level": 2, "barcode": "999",
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["stock"], 5)
        self.assertEqual(self.client.post("/api/products", json={
            "product_id": "P009", "name": "Again"}).status_code, 400)

    def test_upload_product_photo_and_serve_it(self):
        self.login()
        response = self.client.post(
            f"/api/products/P001/images",
            data={"image": (io.BytesIO(image_bytes("P001", 0)), "p001.png")},
            content_type="multipart/form-data")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.get_json()["images"]), 1)
        photo = self.client.get("/api/products/P001/image")
        self.assertEqual(photo.status_code, 200)
        photo.close()

    def test_upload_rejects_non_image(self):
        self.login()
        response = self.client.post(
            "/api/products/P001/images",
            data={"image": (io.BytesIO(b"not an image"), "notes.txt")},
            content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)

    def test_reports_summary(self):
        self.login()
        self.client.post("/api/sales", json={"product_id": "P001", "quantity": 3})
        summary = self.client.get("/api/reports/summary?days=30").get_json()
        self.assertEqual(summary["totals"]["items_sold"], 3)
        self.assertEqual(summary["top_products"][0]["product_id"], "P001")
        self.assertTrue(summary["transactions"])

    def test_recognize_with_template_engine(self):
        self.login()
        response = self.client.post(
            "/api/recognize",
            data={"engine": "template",
                  "image": (io.BytesIO(image_bytes("P003", 9)), "query.png")},
            content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["accepted"])
        self.assertEqual(payload["product"]["product_id"], "P003")
        self.assertEqual(payload["engine"], "template")
        self.assertGreater(payload["elapsed_ms"], 0)

    def test_recognize_requires_image(self):
        self.login()
        self.assertEqual(self.client.post("/api/recognize", data={}).status_code, 400)

    def test_recognize_rejects_unreadable_image(self):
        self.login()
        response = self.client.post(
            "/api/recognize",
            data={"engine": "template", "image": (io.BytesIO(b"junk"), "x.png")},
            content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)

    def test_recognize_reports_unavailable_cnn(self):
        self.login()
        response = self.client.post(
            "/api/recognize",
            data={"engine": "cnn", "image": (io.BytesIO(image_bytes("P001")), "x.png")},
            content_type="multipart/form-data")
        self.assertEqual(response.status_code, 503)

    def test_recognition_engine_list(self):
        self.login()
        payload = self.client.get("/api/recognition/engines").get_json()
        states = {engine["name"]: engine["available"] for engine in payload["engines"]}
        self.assertTrue(states["template"])
        self.assertTrue(states["orb"])


if __name__ == "__main__":
    unittest.main()
