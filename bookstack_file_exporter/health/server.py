"""Opt-in /healthz HTTP server (F4): stdlib ThreadingHTTPServer on a daemon
thread. Liveness-only — returns 200 while the daemon is alive; the scrape
signal lives in last_run.status. No new dependency."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bookstack_file_exporter.health.status import RunStatus


class HealthHandler(BaseHTTPRequestHandler):
    """Serves GET /healthz as a JSON snapshot; any other path → 404.

    The bound RunStatus is injected as a class attribute on a per-server
    subclass (see start_health_server)."""
    status: RunStatus = None  # set on the per-server subclass

    # do_GET name is mandated by BaseHTTPRequestHandler
    def do_GET(self):  # pylint: disable=invalid-name
        """Serve GET /healthz as JSON; 404 for all other paths."""
        if self.path == "/healthz":
            body = json.dumps(self.status.snapshot()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *args):  # silence per-request stderr logging
        pass


def start_health_server(host: str, port: int, status: RunStatus) -> ThreadingHTTPServer:
    """Start the health server on a daemon thread and return the server handle
    so the caller can shut it down via server.shutdown()."""
    handler_cls = type("BoundHealthHandler", (HealthHandler,), {"status": status})
    server = ThreadingHTTPServer((host, port), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
