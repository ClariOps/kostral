"""A remote external scanner next to the built-in engines. Start the scanner first:

    export KOSTRAL_TOKEN_SCANNER=$(python -c "import secrets; print(secrets.token_hex(16))")
    python examples/external/scanner_server.py &
    koss remote examples/demo/bad.yaml --exec examples/external/workflow.py
"""
import json
from pathlib import Path

from kostral.adapters.remote.registry import from_registry
from kostral.modules.renderer.engine import RendererEngine
from kostral.modules.security.engine import SecurityEngine

with open(Path(__file__).resolve().parent / "registry.json") as handle:
    registry = json.load(handle)

workflow = {
    "seq_before": [],
    "parallel_checks": [SecurityEngine(), from_registry(registry["example-scanner"])],  # both read-only
    "seq_after": [RendererEngine()],
}