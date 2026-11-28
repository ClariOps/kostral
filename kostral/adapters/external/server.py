"""Serve an external scanner over HTTP: GET /describe, POST /process.

The server is a thin wrapper around `run_tool`: it receives documents, runs the
pinned command and returns the tool's SARIF log untouched. It never maps and never
knows KOSTRAL's report, so any tool that can write SARIF can sit behind it.
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from kostral.adapters.remote.auth import is_authorized, read_token
from kostral.core.contract import CONTRACT_VERSION, check_descriptor, check_kinds, kind_accepted

from .runner import DEFAULT_TIMEOUT, MAX_OUTPUT_BYTES, ToolError, check_command, run_tool

MAX_REQUEST_BYTES = 10 * 1024 * 1024
_ERROR_TEXT = 500


def describe(name, version, input_kinds):
    """What this server tells a client about itself. It is always read-only."""
    check_kinds(list(input_kinds), name)
    return check_descriptor({
        "name": name, "version": version, "contract_version": CONTRACT_VERSION,
        "mutates": False, "input_kinds": list(input_kinds), "profile": "external",
    }, name)


def _create_handler(descriptor, command, token, *, timeout, max_request_bytes, max_output_bytes):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, payload):
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            if code == 401:
                self.send_header("WWW-Authenticate", "Bearer")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _authorized(self):
            # First thing every request does, before routing or reading a body.
            if is_authorized(self.headers.get("Authorization"), token):
                return True
            self._send(401, {"error": "unauthorized"})
            return False

        def do_GET(self):
            if not self._authorized():
                return
            if self.path != "/describe":
                return self._send(404, {"error": "not found"})
            self._send(200, descriptor)

        def do_POST(self):
            if not self._authorized():
                return
            if self.path != "/process":
                return self._send(404, {"error": "not found"})
            length = self.headers.get("Content-Length", "")
            if not length.isdigit():
                return self._send(411, {"error": "Content-Length is required"})
            if int(length) > max_request_bytes:
                return self._send(413, {"error": f"request is larger than {max_request_bytes} bytes"})
            try:
                data = json.loads(self.rfile.read(int(length)))
            except ValueError:
                return self._send(400, {"error": "body is not JSON"})
            documents = data.get("documents") if isinstance(data, dict) else None
            if (not isinstance(documents, list) or not documents
                    or not all(isinstance(d, dict) for d in documents)):
                return self._send(400, {"error": "body must be {\"documents\": [<manifest>, ...]}"})
            for document in documents:                 # defense in depth, as the native server does
                if not kind_accepted(descriptor["input_kinds"], document.get("kind")):
                    return self._send(400, {"error": f"kind '{document.get('kind')}' is not accepted by this engine"})
            try:
                sarif = run_tool(command, documents, timeout=timeout, max_output_bytes=max_output_bytes)
            except ToolError as exc:
                return self._send(502, {"error": str(exc)[:_ERROR_TEXT]})
            self._send(200, {"sarif": sarif})

        def log_message(self, format, *args):          # nothing about the request is printed
            pass

    return Handler


def serve(name, *, version, input_kinds, command, token_env, host="127.0.0.1", port=9100,
          timeout=DEFAULT_TIMEOUT, max_request_bytes=MAX_REQUEST_BYTES,
          max_output_bytes=MAX_OUTPUT_BYTES):
    """Serve one scanner. No defaults for what identifies it, and the server
    refuses to start without a usable token: it never runs open."""
    command = check_command(command, name)
    token = read_token(token_env, name)
    handler = _create_handler(describe(name, version, input_kinds), command, token, timeout=timeout,
                              max_request_bytes=max_request_bytes, max_output_bytes=max_output_bytes)
    server = HTTPServer((host, port), handler)
    print(f"Serving external scanner {name} on http://{host}:{port}/process")
    server.serve_forever()