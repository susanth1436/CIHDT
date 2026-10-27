#!/usr/bin/env python
"""Start the CIHDT console.

    python run.py                 # http://127.0.0.1:8000
    python run.py --port 9000
"""
from __future__ import annotations

import argparse
import webbrowser


def main() -> None:
    ap = argparse.ArgumentParser(description="CIHDT operator console")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reload", action="store_true",
                    help="auto-reload on source changes (development)")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    import uvicorn

    # Importing the app creates the first account if none exists; the
    # generated password is printed once, here, and nowhere else.
    from cihdt.server import auth

    url = f"http://{args.host}:{args.port}"
    print("=" * 66)
    print("  CIHDT -- Counterfactual Immunization of Holographic Digital Twins")
    print(f"  Console : {url}")
    print(f"  API docs: {url}/docs")
    print("=" * 66)
    print("  Nothing runs on its own. Open the console and start at Step 1.")
    print()
    auth.announce_initial_password()

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    uvicorn.run("cihdt.server.api:app", host=args.host, port=args.port,
                reload=args.reload, log_level="info")


if __name__ == "__main__":
    main()
