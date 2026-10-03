"""Serve the read-only C dashboard from the same JSON file used by B."""

import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from contribution_store import ContributionStore


ROOT = Path(__file__).with_name("dashboard")


def make_handler(db_path):
    class DashboardHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT), **kwargs)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/dashboard":
                try:
                    data = ContributionStore(db_path).dashboard_data("fintech")
                    self.send_json(200, data)
                except (ValueError, OSError, json.JSONDecodeError) as error:
                    self.send_json(500, {"error": str(error)})
                return
            if path == "/":
                self.path = "/index.html"
            super().do_GET()

        def send_json(self, status, data):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return DashboardHandler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path(__file__).with_name("demo.json"))
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.db))
    print(f"Dashboard: http://127.0.0.1:{args.port} (data: {args.db})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
