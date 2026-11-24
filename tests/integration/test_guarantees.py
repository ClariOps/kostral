"""Tests that state a guarantee in plain terms.

Exit codes: 0 = clean, 1 = error-level findings, 2 = usage error, 3 = koss itself failed.

Tests marked @unittest.expectedFailure describe behavior KOSTRAL is supposed to have
but does not have today. When the code is fixed the test reports "unexpected success":
remove the marker, and the guarantee is enforced. (Currently there are none.)
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from .helpers import (ANALYSIS_OK, EXIT_CRASH, EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, ROOT,
                      check_snapshot, exit_for_status, file_sha, koss, manifests, sha, slug)


class DeterminismTests(unittest.TestCase):
    """Same input, same output, every time (and from any working directory)."""

    def test_same_output_twice_from_different_directories(self):
        """Guarantee: same manifest, same output, from any working directory."""
        with tempfile.TemporaryDirectory() as elsewhere:
            for rel in manifests():
                for fmt in ("json", "yaml"):
                    with self.subTest(file=rel, fmt=fmt):
                        a = koss("optimize", rel, "--dry-run", "--output", fmt)
                        b = koss("optimize", ROOT / rel, "--dry-run", "--output", fmt, cwd=elsewhere)
                        self.assertIn(a.rc, ANALYSIS_OK, str(a))
                        self.assertEqual(a.rc, b.rc, f"exit code differs for {rel}")
                        self.assertEqual(sha(a.out), sha(b.out), f"output differs for {rel}")

    def test_directory_input_does_not_depend_on_file_order(self):
        """A folder of manifests must give identical output however the files were created."""
        names = sorted(p.name for p in (ROOT / "examples/resources").glob("*.yaml"))
        outputs = []
        with tempfile.TemporaryDirectory() as tmp:
            for label, order in (("forward", names), ("reverse", list(reversed(names)))):
                d = Path(tmp) / label
                d.mkdir()
                for n in order:
                    shutil.copy(ROOT / "examples/resources" / n, d / n)
                res = koss("optimize", d, "--dry-run", "--output", "yaml")
                self.assertIn(res.rc, ANALYSIS_OK, str(res))
                outputs.append((res.rc, res.out))
        self.assertEqual(outputs[0], outputs[1])


class ReadOnlyTests(unittest.TestCase):
    def test_source_files_are_never_modified(self):
        """Guarantee: koss never rewrites the user's files."""
        for rel in manifests():
            with self.subTest(file=rel):
                before = file_sha(ROOT / rel)
                koss("optimize", rel, "--dry-run", "--output", "json")
                koss("explain", rel, "--output", "json")
                self.assertEqual(before, file_sha(ROOT / rel))

    def test_explain_yaml_returns_the_manifest_unchanged(self):
        """`explain` is analysis only, but its yaml output is not the input: labels are added,
        a container is renamed and protocol: TCP is added.

        Guarantee: analysis commands do not change the manifest."""
        for rel in manifests():
            with self.subTest(file=rel):
                res = koss("explain", rel, "--output", "yaml")
                self.assertIn(res.rc, ANALYSIS_OK, str(res))
                original = list(yaml.safe_load_all((ROOT / rel).read_text(encoding="utf-8")))
                rendered = list(yaml.safe_load_all(res.out))
                self.assertEqual(original, rendered)


class ExitCodeTests(unittest.TestCase):
    def test_good_manifest_exits_zero(self):
        res = koss("optimize", "examples/demo/good.yaml", "--dry-run", "--output", "json")
        self.assertEqual(json.loads(res.out)["status"], "PASSED")
        self.assertEqual(res.rc, 0)

    def test_failed_status_exits_nonzero(self):
        """bad.yaml reports status FAILED but the exit code is 0, so CI cannot use koss to block a deployment.

        Guarantee: a failed check is reported by a non-zero exit code."""
        res = koss("optimize", "examples/demo/bad.yaml", "--dry-run", "--output", "json")
        self.assertEqual(json.loads(res.out)["status"], "FAILED")
        self.assertEqual(res.rc, EXIT_FINDINGS)

    def test_exit_code_does_not_depend_on_dry_run_or_output_format(self):
        """Guarantee: same input, same decision, whatever the flags or renderer.

        The exit code is derived from the report only, never from --dry-run or
        --output, so CI gets the same answer in every mode."""
        for rel in manifests():
            with self.subTest(file=rel):
                status = json.loads(
                    koss("explain", rel, "--output", "json").out)["status"]
                want = exit_for_status(status)
                runs = {
                    "explain text": ("explain", rel),
                    "explain yaml": ("explain", rel, "--output", "yaml"),
                    "optimize json": ("optimize", rel, "--dry-run", "--output", "json"),
                    "optimize yaml": ("optimize", rel, "--dry-run", "--output", "yaml"),
                    "optimize text": ("optimize", rel, "--dry-run"),
                }
                for label, args in runs.items():
                    self.assertEqual(koss(*args).rc, want, f"{label} exit code for {rel}")

    def test_findings_and_crash_have_different_exit_codes(self):
        """Guarantee: CI can tell "the manifest failed" (1) from "koss broke" (3).

        With the example servers down, the remote workflow cannot run at all."""
        failed = koss("optimize", "examples/demo/bad.yaml", "--dry-run", "--output", "json")
        self.assertEqual(failed.rc, EXIT_FINDINGS)
        crashed = koss("remote", "examples/demo/bad.yaml",
                       "--exec", "examples/remote/workflow.py", "--output", "json")
        if crashed.rc == EXIT_OK:
            self.skipTest("remote example servers are running")
        self.assertEqual(crashed.rc, EXIT_CRASH, str(crashed))

    def test_missing_file_is_a_clear_error(self):
        res = koss("optimize", "does-not-exist.yaml")
        self.assertEqual(res.rc, 2)
        self.assertIn("File not found", res.err)

    def test_no_command_is_an_error(self):
        self.assertEqual(koss().rc, 2)

    def test_invalid_output_format_is_an_error(self):
        res = koss("explain", "examples/demo/good.yaml", "--output", "xml")
        self.assertEqual(res.rc, 2)
        self.assertIn("invalid choice", res.err)

    def test_version_flag(self):
        res = koss("--version")
        self.assertEqual(res.rc, 0)
        self.assertTrue(res.out.startswith("koss"), res.out)


class InputModeTests(unittest.TestCase):
    def test_directory_input_reads_every_manifest(self):
        res = koss("explain", "examples/resources", "--output", "json")
        self.assertIn(res.rc, ANALYSIS_OK, str(res))
        check_snapshot(self, "dir__examples_resources.explain-json.json", res.out)

    def test_manifest_can_be_piped_through_stdin(self):
        """The loader supports '-' for stdin (the Helm workflow `helm template ... | koss optimize -`),
        but the CLI rejects '-' with 'File not found: -' before the loader is reached.

        Guarantee: Helm-rendered YAML can be piped in."""
        text = (ROOT / "examples/demo/bad.yaml").read_text(encoding="utf-8")
        piped = koss("optimize", "-", "--dry-run", "--output", "json", stdin=text)
        direct = koss("optimize", "examples/demo/bad.yaml", "--dry-run", "--output", "json")
        self.assertEqual(piped.rc, direct.rc, str(piped))
        self.assertEqual(piped.rc, EXIT_FINDINGS)      # bad.yaml has an error
        self.assertEqual(piped.out, direct.out)


if __name__ == "__main__":
    unittest.main()
