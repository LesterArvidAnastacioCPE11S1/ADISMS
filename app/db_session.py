"""One SQLite connection per Flask request."""
from flask import current_app, g

from . import database as db


def get_conn():
    if "conn" not in g:
        g.conn = db.connect(current_app.config["DB_PATH"])
    return g.conn


def close_conn(_=None):
    conn = g.pop("conn", None)
    if conn is not None:
        conn.close()
