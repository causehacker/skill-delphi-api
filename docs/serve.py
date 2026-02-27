#!/usr/bin/env python3
"""
Local proxy server for the Delphi V3 API Reference page.

Serves api-reference.html and proxies /api/* requests to https://api.delphi.ai/*,
bypassing CORS restrictions so the Send buttons work in the browser.

Usage:
    python3 docs/serve.py            # default port 8787
    python3 docs/serve.py --port 9000
"""
import argparse
import http.server
import json
import os
import ssl
import urllib.error
import urllib.request

DELPHI_BASE = "https://api.delphi.ai"
DOCS_DIR = os.path.dirname(os.path.abspath(__file__))


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DOCS_DIR, **kwargs)

    # ── Proxy: /api/* → https://api.delphi.ai/* ──

    def _is_proxy(self):
        return self.path.startswith("/api/")

    def _build_request(self):
        """Shared: build upstream request from incoming proxy call."""
        target = DELPHI_BASE + self.path[4:]  # strip /api prefix
        body = None
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len:
            body = self.rfile.read(content_len)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "DelphiAPIReference/1.0",
        }
        api_key = self.headers.get("x-api-key")
        if api_key:
            headers["x-api-key"] = api_key
        return target, body, headers

    def _proxy(self, method):
        target, body, headers = self._build_request()
        req = urllib.request.Request(target, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_body = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(resp_body)
        except urllib.error.HTTPError as e:
            resp_body = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp_body)
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _proxy_stream(self):
        """SSE streaming proxy: forward chunks as they arrive."""
        target, body, headers = self._build_request()
        headers["Accept"] = "text/event-stream"
        req = urllib.request.Request(target, data=body, headers=headers, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            self.send_response(resp.status)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            # Stream line-by-line
            try:
                for raw_line in resp:
                    self.wfile.write(raw_line)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                resp.close()
        except urllib.error.HTTPError as e:
            resp_body = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp_body)
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_GET(self):
        if self._is_proxy():
            self._proxy("GET")
        else:
            super().do_GET()

    def do_POST(self):
        if self._is_proxy():
            if self.path.startswith("/api/v3/stream"):
                self._proxy_stream()
            else:
                self._proxy("POST")
        else:
            self.send_response(405)
            self.end_headers()

    def do_PUT(self):
        if self._is_proxy():
            self._proxy("PUT")
        else:
            self.send_response(405)
            self.end_headers()

    def do_PATCH(self):
        if self._is_proxy():
            self._proxy("PATCH")
        else:
            self.send_response(405)
            self.end_headers()

    def do_DELETE(self):
        if self._is_proxy():
            self._proxy("DELETE")
        else:
            self.send_response(405)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "x-api-key, Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def log_message(self, fmt, *args):
        method = args[0].split()[0] if args else ""
        path = args[0].split()[1] if args and len(args[0].split()) > 1 else ""
        status = args[1] if len(args) > 1 else ""
        if path.startswith("/api/"):
            print(f"  \033[36mproxy\033[0m {method} {path} → {status}")
        elif not path.startswith(("/favicon", "/.")) :
            print(f"  \033[90mstatic\033[0m {path}")


def main():
    ap = argparse.ArgumentParser(description="Local proxy for Delphi API Reference")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()

    server = http.server.HTTPServer(("127.0.0.1", args.port), ProxyHandler)
    print(f"\n  \033[1mDelphi V3 API Reference\033[0m")
    print(f"  \033[32m→\033[0m http://localhost:{args.port}/api-reference.html")
    print(f"  \033[90mProxy: /api/* → {DELPHI_BASE}/*\033[0m")
    print(f"  \033[90mPress Ctrl+C to stop\033[0m\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
