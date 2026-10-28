"""Development entry point.

    python run.py

For anything beyond local testing set ADISMS_SECRET_KEY in the environment.
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
