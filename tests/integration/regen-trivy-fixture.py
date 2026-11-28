"""Regenerate the Trivy fixtures from the REAL trivy binary. Run by hand, from anywhere:

    python tests/integration/regen_trivy_fixture.py

Not a test (the name does not match test*.py). Commit the output, then review the diff:
a changed fixture means Trivy's output changed, and that is a decision, not a refresh.
Requires `trivy` on PATH (pin the version in examples/external/registry.json).
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from kostral.adapters.external.runner import document_filename  # same file names the adapter writes

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CASES = {                                   # fixture name -> source manifest
    "trivy-good.sarif.json": ROOT / "examples/demo/good.yaml",
}


def regenerate(source, target):
    with tempfile.TemporaryDirectory(prefix="kostral-scan-") as tmp:
        scan_dir = Path(tmp) / "docs"
        scan_dir.mkdir()
        documents = [d for d in yaml.safe_load_all(source.read_text(encoding="utf-8")) if d is not None]
        for index, doc in enumerate(documents):          # contiguous 0000, 0001, ... like run_tool
            (scan_dir / document_filename(index)).write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

        done = subprocess.run(["trivy", "config", "--format", "sarif", "--quiet", str(scan_dir)],
                              capture_output=True, check=True, timeout=300)
        json.loads(done.stdout)                           # refuse to save anything that is not JSON
        if str(scan_dir).encode() in done.stdout:
            print(f"WARNING {target.name}: the output contains this machine's temp path; "
                  f"it will differ on every regeneration", file=sys.stderr)

    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".tmp")
    partial.write_bytes(done.stdout)
    os.replace(partial, target)                           # never leave a half-written fixture
    print(f"wrote {target.relative_to(ROOT)} ({len(documents)} documents)")


if __name__ == "__main__":
    for name, source in CASES.items():
        regenerate(source, FIXTURES / name)