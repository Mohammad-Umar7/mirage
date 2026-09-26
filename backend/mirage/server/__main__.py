"""python -m mirage.server  →  uvicorn on MIRAGE_API_PORT (default 8000)."""

import os

import uvicorn

from ..config import load_dotenv


def main() -> None:
    load_dotenv()
    port = int(os.environ.get("MIRAGE_API_PORT", "8000"))
    host = os.environ.get("MIRAGE_API_HOST", "127.0.0.1")
    print(f"[mirage] backend on ws://{host}:{port}/ws")
    uvicorn.run("mirage.server.app:app", host=host, port=port, log_level="warning", ws="websockets")


if __name__ == "__main__":
    main()
