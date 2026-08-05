"""Regenerate the README preview image from the real demo page.

Drives the local docs/ build in headless Chromium: fires a burst so the chart
shows the token bucket draining and refilling, waits for the ramp, then
captures. Kept in the repo so the screenshot can be refreshed after a design
change instead of being a one-off artefact nobody can reproduce.

    python scripts/screenshot.py [--out docs/preview.png] [--dark]

Requires: pip install playwright && playwright install chromium
"""

import argparse
import http.server
import socketserver
import threading
from functools import partial
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def serve(directory: Path) -> tuple[socketserver.TCPServer, int]:
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DOCS / "preview.png"))
    parser.add_argument("--dark", action="store_true")
    parser.add_argument("--width", type=int, default=1200)
    parser.add_argument("--height", type=int, default=760)
    args = parser.parse_args()

    httpd, port = serve(DOCS)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(
                viewport={"width": args.width, "height": args.height},
                device_scale_factor=2,  # retina, so the image stays crisp in the README
                color_scheme="dark" if args.dark else "light",
            )
            page.goto(f"http://127.0.0.1:{port}/", wait_until="networkidle")
            page.wait_for_function("document.fonts.status === 'loaded'")

            # A slower refill makes the recovery ramp legible in a still image.
            page.fill("#refillRate", "1.2")
            page.dispatch_event("#refillRate", "change")
            page.wait_for_timeout(300)

            page.click("#fireBurst")  # drains the bucket: 10 allowed, 10 rejected
            page.wait_for_timeout(7000)  # let the refill ramp climb back up

            page.screenshot(path=args.out)
            browser.close()
    finally:
        httpd.shutdown()

    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
