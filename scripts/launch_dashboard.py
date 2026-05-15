from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from streamlit.web import cli as streamlit_cli


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _app_dir() -> Path:
    base = _base_dir()
    bundled = base / "app"
    return bundled if bundled.exists() else base


def _free_port(start: int = 8501, end: int = 8599) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No free local port found in 8501-8599.")


def _wait_for_health(port: int, timeout_seconds: int = 45) -> bool:
    deadline = time.monotonic() + timeout_seconds
    url = f"http://127.0.0.1:{port}/_stcore/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False


def main() -> int:
    app_dir = _app_dir()
    app_file = app_dir / "app.py"
    if not app_file.exists():
        print(f"Cannot find app.py at {app_file}")
        input("Press Enter to exit...")
        return 1

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update(
        {
            "STREAMLIT_SERVER_HEADLESS": "true",
            "STREAMLIT_SERVER_ADDRESS": "127.0.0.1",
            "STREAMLIT_SERVER_PORT": str(port),
        }
    )

    print("Starting City Air Quality Dashboard...")
    print(f"Opening {url}")
    print("Keep this window open while using the dashboard.")
    print("Press Ctrl+C to stop the app.")

    def open_browser_when_ready() -> None:
        if not _wait_for_health(port):
            print(f"Streamlit is still starting. Open {url} manually if the browser does not appear.")
        webbrowser.open(url)

    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    os.chdir(app_dir)
    os.environ.update(env)
    sys.argv = [
        "streamlit",
        "run",
        str(app_file),
        "--server.address",
        "127.0.0.1",
        "--server.port",
        str(port),
        "--browser.gatherUsageStats",
        "false",
        "--global.developmentMode",
        "false",
    ]
    return streamlit_cli.main()


if __name__ == "__main__":
    raise SystemExit(main())
