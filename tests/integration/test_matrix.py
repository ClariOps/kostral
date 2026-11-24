"""Every example manifest, run through four different use cases.

  explain-json    koss explain F --output json
  optimize-json   koss optimize F --dry-run --output json
  optimize-yaml   koss optimize F --dry-run --output yaml
  degraded-json   the same file with its inputs made worse (no resources, no probes,
                  :latest tag, 1 replica, NodePort), then optimize --dry-run --output json

Each run must exit 0 (PASSED) or 1 (FAILED, matching the reported status), print nothing on stderr, and match the saved snapshot.
Create or refresh snapshots with:  UPDATE_SNAPSHOTS=1 python -m unittest discover -s tests -t .
"""
import json
import tempfile
import unittest

from .helpers import (ANALYSIS_OK, check_snapshot, degraded_copy, exit_for_status,
                      has_degraded_variant, koss, manifests, slug)

VARIANTS = {
    "explain-json": (lambda f: ["explain", f, "--output", "json"], "json"),
    "optimize-json": (lambda f: ["optimize", f, "--dry-run", "--output", "json"], "json"),
    "optimize-yaml": (lambda f: ["optimize", f, "--dry-run", "--output", "yaml"], "yaml"),
}


class MatrixTests(unittest.TestCase):
    def assert_clean_run(self, res, fmt):
        self.assertEqual(res.err, "", f"unexpected stderr output\n{res}")
        if fmt == "json":
            data = json.loads(res.out)
            self.assertIn(data["status"], ("PASSED", "FAILED"))
            # the exit code must agree with the status printed in the report
            self.assertEqual(set(data["summary"]), {"errors", "warnings", "optimizations"})
            self.assertEqual(res.rc, exit_for_status(data["status"]), str(res))
        else:
            self.assertIn(res.rc, ANALYSIS_OK, str(res))


def _plain_test(rel, variant):
    build, fmt = VARIANTS[variant]

    def test(self):
        res = koss(*build(rel))
        self.assert_clean_run(res, fmt)
        check_snapshot(self, f"{slug(rel)}.{variant}.{fmt}", res.out)
    return test


def _degraded_test(rel):
    def test(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = degraded_copy(rel, tmp)
            res = koss("optimize", path, "--dry-run", "--output", "json")
        self.assert_clean_run(res, "json")
        check_snapshot(self, f"{slug(rel)}.degraded-json.json", res.out)
    return test


for _rel in manifests():
    for _variant in VARIANTS:
        setattr(MatrixTests, f"test_{slug(_rel)}__{slug(_variant)}", _plain_test(_rel, _variant))
    if has_degraded_variant(_rel):
        setattr(MatrixTests, f"test_{slug(_rel)}__degraded_json", _degraded_test(_rel))


class SanityTests(unittest.TestCase):
    def test_examples_found(self):
        self.assertGreater(len(manifests()), 20, "example manifests not found; run from the repo root")


if __name__ == "__main__":
    unittest.main()
