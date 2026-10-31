"""Local development entry point: `python run.py` (listens on 127.0.0.1:8000)."""
import logging
import os

from app import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")), debug=False)
