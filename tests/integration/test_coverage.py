"""Coverage: a kind KOSTRAL has no model for is never silently dropped.

Before OpaqueIR a privileged StatefulSet gave PASSED with no findings, and
`--output yaml` deleted it from the rendered manifests.

Black box: these tests use only the CLI, load_yaml_irs and the bus, so they hold
for any implementation of the opaque document class and of the coverage report.
(How the runner and the coverage engine are layered is tested in test_runner.py.)
"""
import json
import logging
import os
import tempfile
import unittest

import yaml

from kostral.cli.helper import load_yaml_irs

from .helpers import EXIT_OK, ROOT, koss



logging.disable(logging.CRITICAL)
CASE = "examples/cases/coverage/unmodeled-kinds.yaml"
UNMODELED = ["StatefulSet", "ServiceAccount", "CronJob"]
COVERAGE_RULE = "unanalyzed-resource-kind"


def source_docs():
    with open(os.path.join(ROOT, CASE)) as f:
        return [d for d in yaml.safe_load_all(f) if d]


def load_tmp(text):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "m.yaml")
        with open(path, "w") as f:
            f.write(text)
        return load_yaml_irs(path, logging.getLogger())


class UnanalyzedKindReportTests(unittest.TestCase):
    def report(self, *args, **kw):
        res = koss(*args, **kw)
        return res, json.loads(res.out)

    @staticmethod
    def unanalyzed(data):
        """Names of the resources that carry an unanalyzed-kind warning."""
        return sorted(name for name, r in data["resources"].items()
                      if any(w["rule"] == COVERAGE_RULE for w in r["warnings"]))

    def test_every_unmodeled_document_is_reported(self):
        res, data = self.report("explain", CASE, "--output", "json")
        self.assertEqual(self.unanalyzed(data), ['CronJob/nightly', 'ServiceAccount/app-runner', 'StatefulSet/db'], res.out)

    def test_the_text_report_names_the_unanalyzed_kind(self):
        out = koss("explain", CASE, "--verbose").out
        for kind in UNMODELED:
            self.assertIn(f"Kind '{kind}' is not analyzed", out)

    def test_modeled_kinds_are_not_reported_as_unanalyzed(self):
        res, data = self.report("explain", "examples/demo/good.yaml", "--output", "json")
        self.assertEqual(self.unanalyzed(data), [])

    def test_unanalyzed_kind_is_a_warning_so_ci_still_passes(self):
        res, data = self.report("explain", CASE, "--output", "json")
        self.assertEqual(res.rc, EXIT_OK, str(res))
        self.assertEqual(data["status"], "PASSED")

    def test_the_gap_is_visible_for_piped_input_too(self):
        with open(os.path.join(ROOT, CASE)) as f:
            res = koss("explain", "-", "--output", "json", stdin=f.read())
        self.assertEqual(self.unanalyzed(json.loads(res.out)), ['CronJob/nightly', 'ServiceAccount/app-runner', 'StatefulSet/db'], str(res))


class PassThroughTests(unittest.TestCase):
    def test_unmodeled_documents_are_rendered_unchanged_and_in_order(self):
        for cmd in (("optimize", CASE, "--dry-run", "--output", "yaml"),
                    ("explain", CASE, "--output", "yaml")):
            with self.subTest(cmd=cmd[0]):
                out = list(yaml.safe_load_all(koss(*cmd).out))
                src = source_docs()
                self.assertEqual([d["kind"] for d in out], [d["kind"] for d in src])
                for got, want in zip(out, src):
                    if want["kind"] in UNMODELED:
                        self.assertEqual(got, want)       # verbatim, annotations included

    def test_an_unmodeled_document_loads_and_renders_back_verbatim(self):
        text = ("apiVersion: v1\nkind: ServiceAccount\n"
                "metadata: {name: x, annotations: {a: b}}\nextra: [1, {z: null}]\n")
        (ir,) = load_tmp(text)
        want = yaml.safe_load(text)
        self.assertEqual(ir.to_manifest(), want)
        copy = ir.to_manifest()
        copy["metadata"]["name"] = "changed"
        self.assertEqual(ir.to_manifest(), want)            # callers get a copy

    def test_a_document_without_a_name_does_not_break_the_run(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "m.yaml")
            with open(path, "w") as f:
                f.write("apiVersion: v1\nkind: ConfigMapList\n")
            res = koss("explain", path, "--output", "json")
        self.assertEqual(res.rc, EXIT_OK, str(res))
        data = json.loads(res.out)
        self.assertEqual(sum(1 for r in data["resources"].values()
                             for w in r["warnings"] if w["rule"] == COVERAGE_RULE), 1)

    def test_documents_that_are_not_kubernetes_resources_are_still_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "values.yaml"), "w") as f:
                f.write("replicaCount: 2\nimage: {tag: latest}\n")
            with open(os.path.join(d, "empty.yaml"), "w") as f:
                f.write("# only a comment\n---\n")
            self.assertEqual(load_yaml_irs(d, logging.getLogger()), [])


if __name__ == "__main__":
    unittest.main()
