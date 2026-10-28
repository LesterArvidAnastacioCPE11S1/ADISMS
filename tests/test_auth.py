"""Account tests: sign-up, email login, settings and password change."""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app import database as db

ACCOUNT = {
    "username": "cashier01",
    "email": "cashier01@example.com",
    "phone": "+63 917 123 4567",
    "password": "secret123",
    "confirm_password": "secret123",
}


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({
            "DB_PATH": os.path.join(self.tmp, "auth.db"),
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

    def register(self, **overrides):
        return self.client.post("/api/register", json={**ACCOUNT, **overrides})

    def login(self, identifier, password="secret123"):
        return self.client.post("/api/login",
                                json={"username": identifier, "password": password})

    def test_register_signs_in_and_stores_contact(self):
        response = self.register(role="Owner")
        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["username"], "cashier01")
        self.assertEqual(body["email"], "cashier01@example.com")
        self.assertEqual(body["role"], "Employee")  # role injection ignored
        self.assertTrue(body["created_at"])
        me = self.client.get("/api/me").get_json()
        self.assertEqual(me["phone"], "+63 917 123 4567")

    def test_register_rejects_duplicates(self):
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(self.register(email="other@example.com").status_code, 400)
        self.assertEqual(self.register(**{"username": "cashier02",
                                          "phone": None}).status_code, 400)

    def test_register_validates_fields(self):
        self.assertEqual(self.register(email="not-an-email").status_code, 400)
        self.assertEqual(self.register(phone="123").status_code, 400)
        self.assertEqual(self.register(password="short").status_code, 400)
        self.assertEqual(self.register(confirm_password="different").status_code, 400)
        self.assertEqual(self.register(**{"username": "hi"}).status_code, 400)
        self.assertEqual(self.register(**{"username": "bad name"}).status_code, 400)
        self.assertEqual(self.register(**{"email": "Owner@ArvidDryGoods.Local"}).status_code, 400)

    def test_non_string_inputs_are_rejected_not_crashed(self):
        response = self.client.post("/api/register", json={
            "username": 123, "email": "valid@example.com",
            "password": "password123", "confirm_password": "password123"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post(
            "/api/login", json={"username": 123, "password": 123}).status_code, 400)

    def test_login_by_username_or_email(self):
        self.register()
        self.client.post("/api/logout")
        self.assertEqual(self.login("CASHIER01").status_code, 200)
        self.client.post("/api/logout")
        self.assertEqual(self.login("Cashier01@Example.com").status_code, 200)
        self.assertEqual(self.login("cashier01@example.com", "wrong").status_code, 401)
        self.assertEqual(self.client.post("/api/login", json={}).status_code, 400)

    def test_settings_require_login(self):
        self.assertEqual(self.client.get("/api/settings").status_code, 401)
        self.assertEqual(self.client.patch("/api/settings",
                                           json={"email": "x@example.com"}).status_code, 401)
        self.assertEqual(self.client.post("/api/settings/password", json={}).status_code, 401)

    def test_settings_update_email_and_phone(self):
        self.register()
        before = self.client.get("/api/settings").get_json()
        self.assertEqual(before["username"], "cashier01")
        response = self.client.patch("/api/settings", json={
            "email": "New.Address@Example.com", "phone": "0917-000-1111"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["email"], "new.address@example.com")
        self.assertEqual(response.get_json()["phone"], "0917-000-1111")

        self.client.post("/api/logout")
        self.assertEqual(self.login("new.address@example.com").status_code, 200)
        self.assertEqual(self.login("cashier01").status_code, 200)

    def test_settings_rejects_bad_or_taken_email(self):
        self.register()
        self.assertEqual(self.client.patch("/api/settings",
                                           json={"email": "nope"}).status_code, 400)
        self.assertEqual(self.client.patch(
            "/api/settings", json={"email": "employee@arviddrygoods.local"}).status_code, 400)
        self.assertEqual(self.client.patch("/api/settings",
                                           json={"email": ""}).status_code, 400)

    def test_settings_can_clear_phone_but_keeps_email_required(self):
        self.register()
        response = self.client.patch("/api/settings",
                                     json={"email": ACCOUNT["email"], "phone": ""})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json()["phone"])

    def test_change_password(self):
        self.register()
        self.assertEqual(self.client.post("/api/settings/password", json={
            "current_password": "wrong-one", "new_password": "newsecret123",
            "confirm_password": "newsecret123"}).status_code, 400)
        self.assertEqual(self.client.post("/api/settings/password", json={
            "current_password": "secret123", "new_password": "secret123",
            "confirm_password": "secret123"}).status_code, 400)
        self.assertEqual(self.client.post("/api/settings/password", json={
            "current_password": "secret123", "new_password": "newsecret123",
            "confirm_password": "mismatch"}).status_code, 400)
        self.assertEqual(self.client.post("/api/settings/password", json={
            "current_password": "secret123", "new_password": "newsecret123",
            "confirm_password": "newsecret123"}).status_code, 200)
        self.client.post("/api/logout")
        self.assertEqual(self.login("cashier01", "secret123").status_code, 401)
        self.assertEqual(self.login("cashier01", "newsecret123").status_code, 200)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_legacy_users_table_is_upgraded_without_losing_accounts(self):
        path = os.path.join(self.tmp, "legacy.db")
        conn = sqlite3.connect(path)
        conn.executescript(
            "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, "
            "role TEXT NOT NULL CHECK (role IN ('Owner','Employee')));"
            "INSERT INTO users(username,password_hash,role) VALUES ('owner','hash','Owner');"
            "INSERT INTO users(username,password_hash,role) VALUES ('employee','hash','Employee');")
        conn.commit()
        conn.close()

        conn = db.connect(path)
        try:
            db.init_db(conn)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
            self.assertTrue({"email", "phone", "created_at"} <= columns)
            rows = {row["username"]: row for row in conn.execute("SELECT * FROM users")}
            self.assertEqual(set(rows), {"owner", "employee"})
            self.assertEqual(rows["owner"]["email"], "owner@arviddrygoods.local")
            self.assertEqual(rows["employee"]["email"], "employee@arviddrygoods.local")
            self.assertTrue(rows["owner"]["created_at"])
            self.assertIsNotNone(db.find_user_for_login(conn, "employee@arviddrygoods.local"))
            with self.assertRaises(db.StockError):
                db.create_user(conn, "second", "OWNER@arviddrygoods.local", "password123")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
