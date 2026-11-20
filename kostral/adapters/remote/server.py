import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from kostral.core.base import Report
from kostral.adapters.remote.client import _deserialize_irs
from kostral.core.contract import CONTRACT_VERSION, check_descriptor, check_metadata, kind_accepted


def describe(engine, version, input_kinds):
    """What this server tells a client about itself (GET /describe)."""
    return check_descriptor({
        "name": engine.name,
        "version": version,
        "contract_version": CONTRACT_VERSION,
        "mutates": check_metadata(getattr(engine, "metadata", {}), engine.name)["mutates"],
        "input_kinds": list(input_kinds),
    }, engine.name)
        

def _create_handler(engine, descriptor):
    class EngineHandler(BaseHTTPRequestHandler):
        
        def _send_json(self, code, payload):
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):

            if self.path != "/describe":
                self.send_error(404)
                return

            self._send_json(200, descriptor)


        def do_POST(self):

            if self.path != "/process":
                self.send_error(404)
                return

            try:
                content_length = int(
                    self.headers.get("Content-Length", 0)
                )

                body = self.rfile.read(content_length)

                data = json.loads(body)
                
                ctx_irs = _deserialize_irs(
                    data.get("irs", [])
                )

                # Defense in depth: never process a kind this engine did not declare.
                for ir in ctx_irs:
                    kind = ir.to_manifest().get("kind")
                    if not kind_accepted(descriptor["input_kinds"], kind):
                        self._send_json(400, {"error": f"kind '{kind}' is not accepted by this engine"})
                        return

                # Import here to avoid unnecessary coupling at module load time.
                from kostral.core.context import RunContext

                ctx = RunContext(
                    irs=ctx_irs,
                    opts=data.get("opts", {}),
                    report=Report()
                )

                engine.process(ctx)

                response = {
                    "irs": [
                        {
                            "kind": ir.kind,
                            "manifest": ir.to_manifest(),
                        }
                        for ir in ctx.irs
                    ],
                    "findings": [
                        event.to_dict()
                        for event in ctx.report.events
                    ],
                }
                
                self._send_json(200, response)

            except Exception as exc:
                import traceback
                traceback.print_exc()

                self._send_json(500, {"error": str(exc)})

        def log_message(self, format, *args):
            print(
                f"[remote-server] {self.address_string()} - {format % args}"
            )

    return EngineHandler


def serve(
    engine,
    *,
    version,
    input_kinds,
    host="127.0.0.1",
    port=9000,
):

    server = HTTPServer(
        (host, port),
        _create_handler(engine, describe(engine, version, input_kinds)),
    )

    print(
        f"Serving {engine.name} "
        f"on http://{host}:{port}/process"
    )

    server.serve_forever()