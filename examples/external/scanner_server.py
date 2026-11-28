"""Serve the example scanner as a remote external engine on port 9011.

    export KOSTRAL_TOKEN_SCANNER=<at least 16 characters>
    python examples/external/scanner_server.py
"""
import pathlib
import sys

from kostral.adapters.external.server import serve

if __name__ == "__main__":
    scanner = pathlib.Path(__file__).resolve().parent / "example_scanner.py"
    serve("example-scanner", version="1.0.0", input_kinds=["*"],
          command=[sys.executable, str(scanner), "{dir}"],
          token_env="KOSTRAL_TOKEN_SCANNER", host="127.0.0.1", port=9011)