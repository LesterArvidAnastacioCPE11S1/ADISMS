"""Account tests: owner set-up, login, settings, staff management and migration."""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app import database as db
from tests.helpers import seed_products

OWNER = {
    "username": "storeowner",
    "email": "storeowner@example.com",
    "phone": "+63 917 123 4567",
    "password": "secret123",
    "confirm_password": "secret123",
}

STAFF = {
    "username": "cashier01",
    "email": "cashier01@example.com",
    "phone": "0917-000-1111",
    "password": "staffpass1",
    "confirm_password": "staffpass1",
}


def make_app(tmp, name="auth.db"):
    return create_app({
        "DB_PATH": os.path.join(tmp, name),
        "DATA_DIR": tmp,
        "PRODUCT_IMAGE_DIR": os.path.join(tmp, "products"),
        "TEST_IMAGE_DIR": os.path.join(tmp, "test"),
        "MODEL_DIR": os.path.join(tmp, "models"),
        "EVAL_DIR": os.path.join(tmp, "eval"),
        "TESTING": True,
    })


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = make_app(self.tmp)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def register(self, **overrides):
        return self.client.post("/api/register", json={**OWNER, **overrides})

    def login(self, identifier, password="secret123"):
        return self.client.post("/api/login",
                                json={"username": identifier, "password": password})

    def test_setup_reports_when_owner_is_needed(self):
        self.assertTrue(self.client.get("/api/setup").get_json()["needs_owner"])
        self.assertEqual(self.register().status_code, 201)
        self.assertFalse(self.client.get("/api/setup").get_json()["needs_owner"])

    def test_first_sign_up_creates_owner_and_stores_contact(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["username"], "storeowner")
        self.assertEqual(body["email"], "storeowner@example.com")
        self.assertEqual(body["role"], "Owner")
        self.assertTrue(body["created_at"])
        # Signing up creates the account but does not start a session.
        self.assertEqual(self.client.get("/api/me").status_code, 401)
        self.assertEqual(self.login("storeowner").status_code, 200)
        me = self.client.get("/api/me").get_json()
        self.assertEqual(me["phone"], "+63 917 123 4567")

    def test_only_the_first_account_becomes_owner(self):
        self.assertEqual(self.register().status_code, 201)
        self.client.post("/api/logout")
        self.assertEqual(self.register(**{
            "username": "secondowner", "email": "second@example.com"}).status_code, 400)
        conn = db.connect(os.path.join(self.tmp, "auth.db"))
        try:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM users WHERE role='Owner'").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
        finally:
            conn.close()

    def test_register_validates_fields(self):
        self.assertEqual(self.register(email="not-an-email").status_code, 400)
        self.assertEqual(self.register(phone="123").status_code, 400)
        self.assertEqual(self.register(password="short").status_code, 400)
        self.assertEqual(self.register(confirm_password="different").status_code, 400)
        self.assertEqual(self.register(**{"username": "hi"}).status_code, 400)
        self.assertEqual(self.register(**{"username": "bad name"}).status_code, 400)

    def test_register_rejects_duplicate_contact_details(self):
        self.assertEqual(self.register().status_code, 201)
        self.client.post("/api/logout")
        # The owner gate comes first, but a second sign-up must never succeed.
        self.assertEqual(self.register(**{
            "username": "secondowner", "email": "second@example.com"}).status_code, 400)
        self.assertEqual(self.client.get("/api/setup").get_json()["needs_owner"], False)

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
        self.assertEqual(self.login("STOREOWNER").status_code, 200)
        self.client.post("/api/logout")
        self.assertEqual(self.login("StoreOwner@Example.com").status_code, 200)
        self.assertEqual(self.login("storeowner@example.com", "wrong").status_code, 401)
        self.assertEqual(self.client.post("/api/login", json={}).status_code, 400)

    def test_settings_require_login(self):
        self.assertEqual(self.client.get("/api/settings").status_code, 401)
        self.assertEqual(self.client.patch("/api/settings",
                                           json={"email": "x@example.com"}).status_code, 401)
        self.assertEqual(self.client.post("/api/settings/password", json={}).status_code, 401)

    def test_settings_update_email_and_phone(self):
        self.register()
        self.login("storeowner")
        before = self.client.get("/api/settings").get_json()
        self.assertEqual(before["username"], "storeowner")
        response = self.client.patch("/api/settings", json={
            "email": "New.Address@Example.com", "phone": "0917-000-1111"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["email"], "new.address@example.com")
        self.assertEqual(response.get_json()["phone"], "0917-000-1111")

        self.client.post("/api/logout")
        self.assertEqual(self.login("new.address@example.com").status_code, 200)
        self.assertEqual(self.login("storeowner").status_code, 200)

    def test_settings_rejects_bad_or_taken_email(self):
        self.register()
        self.login("storeowner")
        self.assertEqual(self.client.post("/api/staff", json=STAFF).status_code, 201)
        self.assertEqual(self.client.patch("/api/settings",
                                           json={"email": "nope"}).status_code, 400)
        self.assertEqual(self.client.patch(
            "/api/settings", json={"email": STAFF["email"]}).status_code, 400)
        self.assertEqual(self.client.patch("/api/settings",
                                           json={"email": ""}).status_code, 400)

    def test_settings_can_clear_phone_but_keeps_email_required(self):
        self.register()
        self.login("storeowner")
        response = self.client.patch("/api/settings",
                                     json={"email": OWNER["email"], "phone": ""})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json()["phone"])

    def test_change_password(self):
        self.register()
        self.login("storeowner")
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
        self.assertEqual(self.login("storeowner", "secret123").status_code, 401)
        self.assertEqual(self.login("storeowner", "newsecret123").status_code, 200)


class StaffApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = make_app(self.tmp, "staff.db")
        self.client = self.app.test_client()
        seed_products(self.app.config["DB_PATH"])
        self.assertEqual(self.client.post("/api/register", json=OWNER).status_code, 201)
        self.assertEqual(self.client.post("/api/login", json={
            "username": "storeowner", "password": "secret123"}).status_code, 200)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def create_staff(self, **overrides):
        return self.client.post("/api/staff", json={**STAFF, **overrides})

    def login(self, identifier, password):
        return self.client.post("/api/login",
                                json={"username": identifier, "password": password})

    def test_owner_sees_staff_and_their_activity(self):
        created = self.create_staff()
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.get_json()["role"], "Employee")
        overview = self.client.get("/api/staff").get_json()
        self.assertEqual({u["username"] for u in overview["staff"]},
                         {"storeowner", "cashier01"})
        self.assertEqual(overview["activity"], [])

        self.client.post("/api/logout")
        self.assertEqual(self.login("cashier01", "staffpass1").status_code, 200)
        self.assertEqual(self.client.post(
            "/api/deliveries", json={"product_id": "P003", "quantity": 2}).status_code, 201)
        self.client.post("/api/logout")
        self.assertEqual(self.login("storeowner", "secret123").status_code, 200)

        overview = self.client.get("/api/staff").get_json()
        cashier = next(u for u in overview["staff"] if u["username"] == "cashier01")
        self.assertEqual(cashier["actions"], 1)
        self.assertTrue(cashier["last_active"])
        activity = overview["activity"]
        self.assertEqual(activity[0]["username"], "cashier01")
        self.assertEqual(activity[0]["type"], "DELIVERY")
        self.assertEqual(activity[0]["qty_change"], 2)

    def test_employees_cannot_manage_staff(self):
        self.create_staff()
        self.client.post("/api/logout")
        self.assertEqual(self.login("cashier01", "staffpass1").status_code, 200)
        self.assertEqual(self.client.get("/api/staff").status_code, 403)
        self.assertEqual(self.client.post("/api/staff", json={
            "username": "cashier02", "email": "cashier02@example.com",
            "password": "staffpass2", "confirm_password": "staffpass2"}).status_code, 403)

    def test_staff_endpoints_require_login(self):
        self.client.post("/api/logout")
        self.assertEqual(self.client.get("/api/staff").status_code, 401)
        self.assertEqual(self.client.post("/api/staff", json=STAFF).status_code, 401)

    def test_staff_creation_validates_and_ignores_role(self):
        response = self.create_staff(role="Owner")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["role"], "Employee")

        self.assertEqual(self.create_staff(**{
            "username": STAFF["username"], "email": "another@example.com"}).status_code, 400)
        self.assertEqual(self.create_staff(**{
            "username": "cashier02",
            "email": STAFF["email"]}).status_code, 400)
        self.assertEqual(self.create_staff(**{
            "username": "cashier02", "email": "cashier02@example.com",
            "password": "short"}).status_code, 400)
        self.assertEqual(self.create_staff(**{
            "username": "cashier02", "email": "not-an-email"}).status_code, 400)
        self.assertEqual(self.create_staff(**{
            "username": "bad name",
            "email": "cashier02@example.com"}).status_code, 400)


class StaffLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app = make_app(self.tmp, "logs.db")
        self.client = self.app.test_client()
        self.assertEqual(self.client.post("/api/register", json=OWNER).status_code, 201)
        seed_products(self.app.config["DB_PATH"])
        self.assertEqual(self.client.post("/api/login", json={
            "username": "storeowner", "password": "secret123"}).status_code, 200)
        self.assertEqual(self.client.post("/api/staff", json=STAFF).status_code, 201)
        self.client.post("/api/logout")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def login(self, identifier, password):
        return self.client.post("/api/login",
                                json={"username": identifier, "password": password})

    def test_owner_sees_sign_ins_and_staff_actions(self):
        self.assertEqual(self.login("cashier01", "staffpass1").status_code, 200)
        self.assertEqual(self.client.post(
            "/api/sales", json={"product_id": "P002", "quantity": 1}).status_code, 201)
        self.client.post("/api/logout")
        self.assertEqual(self.login("cashier01", "wrong-pass").status_code, 401)
        self.assertEqual(self.login("storeowner", "secret123").status_code, 200)

        entries = self.client.get("/api/staff/logs").get_json()["entries"]
        actions = [entry["action"] for entry in entries]
        self.assertIn("OWNER_SETUP", actions)
        self.assertIn("STAFF_CREATED", actions)
        self.assertIn("SALE", actions)
        self.assertIn("LOGIN_FAILED", actions)
        self.assertIn("LOGOUT", actions)
        self.assertEqual(entries[0]["action"], "LOGIN")
        self.assertEqual(entries[0]["username"], "storeowner")

        staff_entry = next(e for e in entries if e["action"] == "STAFF_CREATED")
        self.assertEqual(staff_entry["username"], "storeowner")
        self.assertIn("cashier01", staff_entry["detail"])
        failed = next(e for e in entries if e["action"] == "LOGIN_FAILED")
        self.assertEqual(failed["username"], "cashier01")
        sale = next(e for e in entries if e["action"] == "SALE")
        self.assertEqual(sale["username"], "cashier01")
        self.assertEqual(sale["role"], "Employee")

    def test_action_filter_and_limit(self):
        self.login("storeowner", "secret123")
        filtered = self.client.get("/api/staff/logs?action=owner_setup").get_json()["entries"]
        self.assertEqual([e["action"] for e in filtered], ["OWNER_SETUP"])
        limited = self.client.get("/api/staff/logs?limit=2").get_json()["entries"]
        self.assertEqual(len(limited), 2)

    def test_employees_and_guests_cannot_read_logs(self):
        self.login("storeowner", "secret123")
        self.assertEqual(self.client.get("/api/staff/logs").status_code, 200)
        self.client.post("/api/logout")
        self.assertEqual(self.client.get("/api/staff/logs").status_code, 401)
        self.assertEqual(self.login("cashier01", "staffpass1").status_code, 200)
        self.assertEqual(self.client.get("/api/staff/logs").status_code, 403)


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
            self.assertIsNone(rows["owner"]["email"])
            self.assertTrue(rows["owner"]["created_at"])
            self.assertIsNotNone(db.find_user_for_login(conn, "employee"))
            self.assertTrue(db.has_owner(conn))
            with self.assertRaises(db.StockError):
                db.create_owner(conn, "second", "owner2@example.com", "password123")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
