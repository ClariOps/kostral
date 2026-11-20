"""Shared fakes for the remote-engine tests: a descriptor, a registry entry that
pins it, and a tiny fake engine server."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def descriptor(name="r", mutates=False, version="1.0.0", kinds=("Deployment",)):
    return {"name": name, "version": version, "contract_version": 1,
            "mutates": mutates, "input_kinds": list(kinds)}


def pinned_entry(url, name="r", mutates=None, version="1.0.0", kinds=("Deployment",)):
    entry = {"name": name, "endpoint": url,
             "descriptor": {"version": version, "input_kinds": list(kinds)}}
    if mutates is not None:
        entry["metadata"] = {"mutates": mutates}
    return entry


def _serve(responder, declared=None, log=None):
    """A fake engine server. `declared` is what GET /describe returns; `log`
    collects 'GET /describe' / 'POST /process' in the order they arrive."""
    declared = declared or descriptor()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if log is not None:
                log.append(f"GET {self.path}")
            raw = json.dumps(declared).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            if log is not None:
                log.append(f"POST {self.path}")
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            code, out = responder(body)
            raw = json.dumps(out).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/process"