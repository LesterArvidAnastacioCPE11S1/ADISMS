"""Login, sign-up, account settings and route guards."""
import re
from functools import wraps

from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from . import database as db
from .db_session import get_conn

bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"[A-Za-z0-9_.-]{3,32}")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"[0-9+()\-\s]{7,20}")


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify(error="Please log in."), 401
        return fn(*args, **kwargs)
    return wrapper


def role_required(*roles):
    """Use for management-only endpoints, e.g. @role_required("Owner")."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if session.get("role") not in roles:
                return jsonify(error="You do not have permission to do that."), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---------- validation ----------
def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _clean_username(value):
    username = _text(value)
    if not USERNAME_RE.fullmatch(username):
        raise db.StockError("Username must be 3-32 characters using letters, numbers, "
                            "dots, hyphens or underscores.")
    return username


def _clean_email(value):
    email = _text(value).lower()
    if len(email) > 120 or not EMAIL_RE.fullmatch(email):
        raise db.StockError("Enter a valid email address.")
    return email


def _clean_phone(value):
    phone = _text(value)
    if not phone:
        return None
    if not PHONE_RE.fullmatch(phone) or not 7 <= len(re.sub(r"\D", "", phone)) <= 15:
        raise db.StockError("Enter a valid phone number (7-15 digits) or leave it blank.")
    return phone


def _clean_password(value, confirm=None):
    password = value if isinstance(value, str) else ""
    if not 8 <= len(password) <= 128:
        raise db.StockError("Password must be 8-128 characters.")
    if confirm is not None and password != (confirm if isinstance(confirm, str) else ""):
        raise db.StockError("Passwords do not match.")
    return password


# ---------- session helpers ----------
def _account(user):
    return {key: user[key] for key in ("id", "username", "email", "phone", "role", "created_at")}


def _sign_in(user):
    session.clear()
    session.update(user_id=user["id"], username=user["username"], role=user["role"])


def _current_user():
    user = db.get_user(get_conn(), session["user_id"])
    if user is None:
        session.clear()
    return user


def _log(conn, action, user=None, detail=None, identifier=None):
    db.log_activity(conn, action,
                    user_id=user["id"] if user is not None else None,
                    username=user["username"] if user is not None else identifier,
                    role=user["role"] if user is not None else None,
                    detail=detail, ip=request.remote_addr)


# ---------- endpoints ----------
@bp.get("/api/setup")
def setup_state():
    """Public: tells the sign-in screen whether the Owner account exists yet."""
    return jsonify(needs_owner=not db.has_owner(get_conn()))


@bp.post("/api/register")
def register():
    """First-run owner sign-up. The new owner must then sign in separately."""
    data = request.get_json(silent=True) or {}
    username = _clean_username(data.get("username"))
    email = _clean_email(data.get("email"))
    phone = _clean_phone(data.get("phone"))
    password = _clean_password(data.get("password"), data.get("confirm_password"))
    user = db.create_owner(get_conn(), username, email, password, phone)
    _log(get_conn(), "OWNER_SETUP", user=user, detail=email)
    return jsonify(_account(user)), 201


@bp.get("/api/staff")
@login_required
@role_required("Owner")
def list_staff():
    return jsonify(db.staff_overview(get_conn(),
                                     activity_limit=current_app.config["STAFF_ACTIVITY_LIMIT"]))


@bp.post("/api/staff")
@login_required
@role_required("Owner")
def create_staff():
    data = request.get_json(silent=True) or {}
    username = _clean_username(data.get("username"))
    email = _clean_email(data.get("email"))
    phone = _clean_phone(data.get("phone"))
    password = _clean_password(data.get("password"), data.get("confirm_password"))
    conn = get_conn()
    user = db.create_user(conn, username, email, password, phone, role="Employee")
    _log(conn, "STAFF_CREATED", user=db.get_user(conn, session["user_id"]),
         detail="@" + user["username"])
    return jsonify(_account(user)), 201


@bp.get("/api/staff/logs")
@login_required
@role_required("Owner")
def staff_logs():
    """Owner-only audit trail of sign-ins, sales, stock and account changes."""
    try:
        limit = max(1, min(200, int(request.args.get("limit", 100))))
    except (TypeError, ValueError):
        limit = 100
    action = (request.args.get("action") or "").strip().upper() or None
    return jsonify(entries=db.activity_entries(get_conn(), limit=limit, action=action))


@bp.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    identifier = _text(data.get("username") or data.get("identifier"))
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    if not identifier or not password:
        return jsonify(error="Enter your username or email and your password."), 400
    conn = get_conn()
    user = db.find_user_for_login(conn, identifier)
    if user is None:
        _log(conn, "LOGIN_FAILED", identifier=identifier[:120],
             detail="Unknown username or email")
        return jsonify(error="Invalid username/email or password."), 401
    if not check_password_hash(user["password_hash"], password):
        _log(conn, "LOGIN_FAILED", user=user, detail="Wrong password")
        return jsonify(error="Invalid username/email or password."), 401
    _sign_in(user)
    _log(conn, "LOGIN", user=user)
    return jsonify(_account(user))


@bp.post("/api/logout")
def logout():
    if session.get("user_id"):
        db.log_activity(get_conn(), "LOGOUT", user_id=session["user_id"],
                        username=session.get("username"), role=session.get("role"),
                        ip=request.remote_addr)
    session.clear()
    return jsonify(ok=True)


@bp.get("/api/me")
def me():
    if "user_id" not in session:
        return jsonify(error="Please log in."), 401
    user = _current_user()
    if user is None:
        return jsonify(error="Please log in."), 401
    return jsonify(_account(user))


@bp.get("/api/settings")
@login_required
def get_settings():
    user = _current_user()
    if user is None:
        return jsonify(error="Please log in."), 401
    return jsonify(_account(user))


@bp.patch("/api/settings")
@login_required
def update_settings():
    data = request.get_json(silent=True) or {}
    email = _clean_email(data.get("email"))
    phone = _clean_phone(data.get("phone"))
    user = db.update_user_contact(get_conn(), session["user_id"], email, phone)
    _log(get_conn(), "SETTINGS_UPDATED", user=user, detail="Contact details updated")
    return jsonify(_account(user))


@bp.post("/api/settings/password")
@login_required
def change_password():
    data = request.get_json(silent=True) or {}
    new_password = _clean_password(data.get("new_password"), data.get("confirm_password"))
    row = get_conn().execute("SELECT * FROM users WHERE id=?",
                             (session["user_id"],)).fetchone()
    if row is None:
        session.clear()
        return jsonify(error="Please log in."), 401
    if not check_password_hash(row["password_hash"], data.get("current_password")
                               if isinstance(data.get("current_password"), str) else ""):
        return jsonify(error="Your current password is incorrect."), 400
    if check_password_hash(row["password_hash"], new_password):
        return jsonify(error="Choose a password different from your current one."), 400
    db.update_password(get_conn(), row["id"], generate_password_hash(new_password))
    _log(get_conn(), "PASSWORD_CHANGED", user=db.get_user(get_conn(), row["id"]))
    return jsonify(ok=True)
