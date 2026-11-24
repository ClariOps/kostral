"""Shared helpers for the KOSTRAL integration tests.

Every test runs the real CLI in a subprocess (`python -m kostral.cli.main`)
and checks exit code, stdout and stderr. Nothing here imports kostral internals,
so these tests keep working when the architecture changes.
"""
import copy
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SNAP_DIR = Path(__file__).resolve().parent / "snapshots"
UPDATE = os.environ.get("UPDATE_SNAPSHOTS") == "1"
TIMEOUT = 90

MANIFEST_GLOBS = [
    "examples/cases/**/*.yaml",
    "examples/demo/*.yaml",
    "examples/resources/*.yaml",
]


# Exit-code contract (see kostral/cli/helper.py)
EXIT_OK, EXIT_FINDINGS, EXIT_USAGE, EXIT_CRASH = 0, 1, 2, 3
ANALYSIS_OK = (EXIT_OK, EXIT_FINDINGS)   # the run completed; 1 just means "errors found"


def exit_for_status(status):
    """FAILED -> 1, PASSED -> 0."""
    return EXIT_FINDINGS if status == "FAILED" else EXIT_OK


class Result:
    def __init__(self, cmd, rc, out, err):
        self.cmd, self.rc, self.out, self.err = cmd, rc, out, err

    def __str__(self):
        return (f"command: {' '.join(self.cmd)}\nexit code: {self.rc}\n"
                f"--- stdout ---\n{self.out}\n--- stderr ---\n{self.err}")


def koss(*args, cwd=None, stdin=None):
    """Run `koss <args>` and return a Result. Prints nothing, raises nothing."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    cmd = [sys.executable, "-m", "kostral.cli.main", *[str(a) for a in args]]
    p = subprocess.run(cmd, cwd=str(cwd or ROOT), env=env, input=stdin,
                       capture_output=True, text=True, timeout=TIMEOUT)
    return Result(cmd, p.returncode, p.stdout, p.stderr)


def manifests():
    """Relative paths of every example manifest, sorted, so test ids are stable."""
    found = []
    for pattern in MANIFEST_GLOBS:
        found += sorted(ROOT.glob(pattern))
    return [p.relative_to(ROOT).as_posix() for p in found]


def slug(text):
    return re.sub(r"\W+", "_", text).strip("_")


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_snapshot(case, name, text):
    """Compare `text` with tests/integration/snapshots/<name>.

    UPDATE_SNAPSHOTS=1 rewrites the file instead of comparing. Review the
    diff in git before committing: a snapshot freezes today's behavior,
    including behavior that may be wrong.
    """
    path = SNAP_DIR / name
    if UPDATE:
        path.write_text(text, encoding="utf-8")
        return
    if not path.exists():
        case.fail(f"No snapshot '{name}'. Run with UPDATE_SNAPSHOTS=1 to create it, then review it.")
    case.assertMultiLineEqual(path.read_text(encoding="utf-8"), text,
                              f"Output differs from snapshot '{name}'")


# ---- input variants (the "changing inputs" use case) -----------------------

def _degrade_image(image):
    last = image.rsplit("/", 1)[-1]
    base = image[: len(image) - len(last)] + last.split(":", 1)[0].split("@", 1)[0]
    return base + ":latest"


def degrade(docs):
    """Return a worse copy of the manifests: Deployments lose resources and probes,
    get a :latest image tag and 1 replica; Services become NodePort.
    Other kinds are left alone."""
    docs = copy.deepcopy(docs)
    for d in docs:
        if not isinstance(d, dict):
            continue
        if d.get("kind") == "Deployment":
            spec = d.setdefault("spec", {})
            spec["replicas"] = 1
            for c in spec.get("template", {}).get("spec", {}).get("containers", []):
                c["image"] = _degrade_image(c.get("image", "app"))
                for key in ("resources", "readinessProbe", "livenessProbe"):
                    c.pop(key, None)
        elif d.get("kind") == "Service":
            d.setdefault("spec", {})["type"] = "NodePort"
    return docs


def degraded_copy(rel_path, directory):
    """Write a degraded copy of manifest `rel_path` into `directory`.
    Returns the new path, or None if degrading changes nothing (e.g. a ConfigMap)."""
    original = list(yaml.safe_load_all((ROOT / rel_path).read_text(encoding="utf-8")))
    changed = degrade(original)
    if changed == original:
        return None
    target = Path(directory) / Path(rel_path).name
    target.write_text(yaml.safe_dump_all(changed, sort_keys=False), encoding="utf-8")
    return target


def has_degraded_variant(rel_path):
    with tempfile.TemporaryDirectory() as tmp:
        return degraded_copy(rel_path, tmp) is not None
