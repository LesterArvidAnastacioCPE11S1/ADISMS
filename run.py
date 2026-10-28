"""Entry point.

    python run.py

Environment variables:
    ADISMS_HOST        bind address (default 127.0.0.1; 0.0.0.0 lets phones and
                       other devices on the same network connect)
    ADISMS_PORT        port (default 5000)
    ADISMS_DEBUG       set to 1 to enable the Flask debugger and reloader
    ADISMS_SECRET_KEY  set a long random value for shared/network use
"""
import os

from app import create_app

app = create_app()


def _flag(name):
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    host = os.environ.get("ADISMS_HOST", "127.0.0.1")
    port = int(os.environ.get("ADISMS_PORT", "5000"))
    app.run(host=host, port=port, debug=_flag("ADISMS_DEBUG"))
