# KOSTRAL integration tests

These tests run the real `koss` CLI on your example manifests and check exit code,
output and stderr. They use only the Python standard library (`unittest`), so they
also run under `pytest`.

## Run

    pip install -e .
    python -m unittest discover -s tests -t . -v

## What is covered

- `test_matrix.py`: every manifest in `examples/cases`, `examples/demo` and
  `examples/resources`, four runs each (explain json, optimize json, optimize yaml,
  and a "degraded" copy with worse inputs). Each run must exit 0, print nothing on
  stderr, and match its saved snapshot.
- `test_guarantees.py`: same input gives the same output (also from another folder
  and in any file order), source files are never modified, exit codes, input modes.
- `test_remote.py`: starts the three example servers (ports 9001-9003) and compares
  the remote workflow with the local result; a missing server must be an error.
- `test_external.py`: the external profile. The SARIF mapper (pure), running a tool, the local and remote engines, the profile handshake, and the CLI exit codes. It needs no real scanner: `examples/external/example_scanner.py` writes SARIF like Trivy does, and the Trivy fixture in `fixtures/` is generated bu `python tests/integration/regen-trivy-fixture.py`. Port 9011 is used for one CLI round trip and skipped if busy.

## Report

    python tests/report.py

runs the suite and writes `docs/transparency/test-report.md` (add `--yaml file.yaml` for a YAML copy):
summary, the known-failure table with reasons, results per use case. The report is generated; do not edit it by hand.
Show which guarantee a test checks by adding a line `Guarantee: ...` to its docstring.

## Snapshots

Saved outputs live in `tests/integration/snapshots/`. They freeze today's behavior,
including behavior that may be wrong, so review them once. To refresh after an
intended change:

    UPDATE_SNAPSHOTS=1 python -m unittest discover -s tests -t .

then review the git diff before committing.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Run completed, no error-level findings |
| 1 | Run completed, the report has errors (status FAILED), or a deploy failed |
| 2 | Usage error (bad flag, file not found) |
| 3 | koss itself failed (engine, remote server, internal error) |

Tests accept 0 or 1 for "the analysis ran" and check that the code matches the
reported status. 3 is never an acceptable result for a normal run.

## Known failures (marked `@unittest.expectedFailure`)

None at the moment. When a new known problem is found, add a test for the behavior
it should have, mark it `@unittest.expectedFailure`, and list it here. When it is
fixed the run reports "unexpected success": delete the marker.
