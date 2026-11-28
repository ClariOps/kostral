"""The same scanner run as a subprocess, no server and no token.

    koss remote examples/demo/bad.yaml --exec examples/external/local_workflow.py
"""
import sys
from pathlib import Path

from kostral.adapters.external.engine import ExternalToolEngine
from kostral.adapters.external.sarif import SarifProfile
from kostral.modules.renderer.engine import RendererEngine
from kostral.modules.security.engine import SecurityEngine

scanner = Path(__file__).resolve().parent / "example_scanner.py"

workflow = {
    "seq_before": [],
    "parallel_checks": [
        SecurityEngine(),
        # this scanner puts its fix text in rule.help, so the mapping says so explicitly
        ExternalToolEngine("example-scanner", [sys.executable, str(scanner), "{dir}"],
                           mapping=SarifProfile.from_dict({"fix_sources": ["fixes", "help", "help_uri"]})),
    ],
    "seq_after": [RendererEngine()],
}