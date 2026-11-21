"""Shared fakes for the remote-engine tests: a descriptor, a registry entry that
pins it (and names a token variable), and a tiny fake engine server."""
import json, os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import traceback
# Tokens come from the environment, like in real use. Tests that build registry
# entries get this one by default.
TEST_TOKEN_ENV = "KOSTRAL_TEST_TOKEN"
TEST_TOKEN = "test-token-0123456789-abcdef"
os.environ.setdefault(TEST_TOKEN_ENV, TEST_TOKEN)

def descriptor(name="r", mutates=False, version="1.0.0", kinds=("Deployment",)):
    return {"name": name, "version": version, "contract_version": 1,
            "mutates": mutates, "input_kinds": list(kinds)}


def pinned_entry(url, name="r", mutates=None, version="1.0.0", kinds=("Deployment",), token_env=TEST_TOKEN_ENV):
    entry = {"name": name, "endpoint": url,"token_env": token_env,
             "descriptor": {"version": version, "input_kinds": list(kinds)}}
    if mutates is not None:
        entry["metadata"] = {"mutates": mutates}
    return entry


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def shutdown(self):
        super().shutdown()
        self.server_close()             # do not leave the listening socket open


def _serve(responder, declared=None, log=None, token=None, headers=None):
    """A fake engine server.

    declared : what GET /describe returns
    log      : collects 'GET /describe' / 'POST /process' (and '... 401') in arrival order
    token    : if given, every request must carry 'Authorization: Bearer <token>'
    headers  : if given, the Authorization header of every request is appended to it

    A failure inside the fake (a bad responder, say) is answered with a 500 that
    carries the traceback, so a test shows the cause instead of a dropped connection.
    """
    declared = declared or descriptor()

    class H(BaseHTTPRequestHandler):
        def _json(self, code, payload):
            raw = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def _allowed(self, verb):
            if headers is not None:
                headers.append(self.headers.get("Authorization"))
            ok = token is None or self.headers.get("Authorization") == f"Bearer {token}"
           
            if log is not None:
              log.append(f"{verb} {self.path}" + ("" if ok else " 401"))
            if not ok:
                self._json(401, {"error": "unauthorized"})
            return ok

        def do_GET(self):
            if self._allowed("GET"):
                self._json(200, declared)

        def do_POST(self):
            if not self._allowed("POST"):
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                code, out = responder(body)
                self._json(code, out)
            except Exception:
                self._json(500, {"error": traceback.format_exc()})
 
        def log_message(self, *a):
            pass

    server = _Server(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/process"