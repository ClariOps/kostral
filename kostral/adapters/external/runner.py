"""run(): start an external tool on the documents and return its SARIF log.

Everything that can go wrong OUTSIDE KOSTRAL's control is handled here and nowhere
else, and every failure is a ToolError (the run ends with exit 3): a missing binary,
a timeout, a non-zero exit, output that is too big or is not JSON. A tool that finds
problems must still exit 0 (for Trivy: do not pass --exit-code), because a non-zero
exit is how this function recognises a tool that broke.
"""
import json
import os
import shutil
import subprocess
import tempfile

import yaml

DIR_PLACEHOLDER = "{dir}"
DEFAULT_TIMEOUT = 60
MAX_OUTPUT_BYTES = 10 * 1024 * 1024
_STDERR_TAIL = 500


class ToolError(RuntimeError):
    """The external tool could not be run, or did not deliver a usable result."""


def document_filename(index):
    """Document N of the request is written as 000N.yaml. The client resolves a
    finding's file uri back to a resource with this same rule."""
    return f"{index:04d}.yaml"


def check_command(command, who="external tool"):
    if (not isinstance(command, (list, tuple)) or not command
            or not all(isinstance(a, str) and a for a in command)):
        raise ValueError(f"{who}: command must be a non-empty list of strings (no shell)")
    if not any(DIR_PLACEHOLDER in a for a in command):
        raise ValueError(f"{who}: command must contain {DIR_PLACEHOLDER} where the documents' folder goes")
    return list(command)


def run_tool(command, manifests, *, timeout=DEFAULT_TIMEOUT, max_output_bytes=MAX_OUTPUT_BYTES):
    """Write each manifest to its own file, in order, run `command` with {dir}
    replaced by that folder, and return the parsed SARIF log (a dict)."""
    command = check_command(command)
    if shutil.which(command[0]) is None:
        raise ToolError(f"'{command[0]}' is not installed or not on PATH")

    with tempfile.TemporaryDirectory(prefix="kostral-scan-") as tmp:
        docs = os.path.join(tmp, "docs")
        os.mkdir(docs)
        for index, manifest in enumerate(manifests):
            with open(os.path.join(docs, document_filename(index)), "w", encoding="utf-8") as handle:
                yaml.safe_dump(manifest, handle, sort_keys=False)

        out_path = os.path.join(tmp, "out.sarif")          # outside docs/, so it is never scanned
        argv = [a.replace(DIR_PLACEHOLDER, docs) for a in command]
        try:
            with open(out_path, "wb") as out:
                done = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=out,
                                      stderr=subprocess.PIPE, timeout=timeout, cwd=tmp)
        except subprocess.TimeoutExpired as exc:
            raise ToolError(f"'{command[0]}' did not finish within {timeout}s") from exc
        except OSError as exc:
            raise ToolError(f"'{command[0]}' could not be started: {exc}") from exc

        if done.returncode != 0:
            tail = done.stderr.decode("utf-8", "replace").strip()[-_STDERR_TAIL:]
            raise ToolError(f"'{command[0]}' exited with {done.returncode}: {tail}")
        if os.path.getsize(out_path) > max_output_bytes:
            raise ToolError(f"'{command[0]}' wrote more than {max_output_bytes} bytes")
        with open(out_path, "rb") as handle:
            raw = handle.read()
    try:
        log = json.loads(raw)
    except ValueError as exc:
        raise ToolError(f"'{command[0]}' did not write JSON (SARIF) to stdout") from exc
    if not isinstance(log, dict):
        raise ToolError(f"'{command[0]}' wrote JSON that is not a SARIF object")
    return log