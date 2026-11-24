"""KostralRunner: system responsibilities sit on top of the user's workflow.

    KostralRunner(workflow).run(ctx)
        1. CoverageEngine reports every document no rule can analyze (mandatory)
        2. the user-composed workflow (ServiceBus) runs

What these tests pin down
  * coverage is reported whatever the workflow contains (even no validator at all)
  * it runs first, exactly once, and a workflow cannot switch it off or erase it
  * the contract (snapshot/verify) treats opaque documents as untouchable by ANY
    engine, including engines that are allowed to mutate

If an import below fails, edit RUNNER_MODULES / COVERAGE_MODULES: they list where
the classes live in your tree. COVERAGE_RULE is the rule id the report uses.
"""
import importlib
import json
import logging
import os
import tempfile
import unittest
from types import MappingProxyType

from kostral.cli.helper import load_yaml_irs, KostralRunner
from kostral.core.base import Module
from kostral.core.bus import EngineContractViolation, ServiceBus
from kostral.core.context import RunContext
from kostral.modules.optimizer.engine import OptimizerEngine
from kostral.modules.renderer.engine import RendererEngine
from kostral.modules.security.engine import SecurityEngine
from kostral.modules.validator.engine import ValidatorEngine
from kostral.modules.coverage.engine import CoverageEngine
from .helpers import EXIT_OK, ROOT, koss

# ---- where things live in your tree (edit if needed) ----------------------------
COVERAGE_RULE = "unanalyzed-resource-kind"
# ---------------------------------------------------------------------------------



logging.disable(logging.CRITICAL)
CASE = os.path.join(ROOT, "examples/cases/coverage/unmodeled-kinds.yaml")
GOOD = os.path.join(ROOT, "examples/demo/good.yaml")
OPAQUE_NAMES = ["db", "app-runner", "nightly"]          # document order in CASE
OPAQUE_RESOURCES = [
    "StatefulSet/db",
    "ServiceAccount/app-runner",
    "CronJob/nightly",
]

def make_ctx(path=CASE, opts=None):
    return RunContext(irs=load_yaml_irs(path, logging.getLogger()), opts=opts or {})


def docs(ctx):
    return [ir.to_manifest() for ir in ctx.irs]


def coverage_events(ctx):
    return [e for e in ctx.report.events if e.rule == COVERAGE_RULE]


def is_opaque(ir):
    return getattr(ir, "is_opaque", False)


class Probe(Module):
    """Records what the report looked like when the workflow started."""
    name = "probe"
    metadata = MappingProxyType({"mutates": False})

    def __init__(self):
        self.calls = 0
        self.rules_seen = None

    def process(self, ctx):
        self.calls += 1
        self.rules_seen = [e.rule for e in ctx.report.events]


class CoverageEngineTests(unittest.TestCase):
    def test_one_warning_per_unanalyzed_document_in_document_order(self):
        ctx = make_ctx()
        CoverageEngine().process(ctx)
        self.assertEqual([e.resource for e in coverage_events(ctx)], OPAQUE_RESOURCES)
        self.assertEqual({e.level for e in coverage_events(ctx)}, {"warning"})

    def test_nothing_to_say_when_every_document_is_modeled(self):
        ctx = make_ctx(GOOD)
        CoverageEngine().process(ctx)
        self.assertEqual(ctx.report.events, [])

    def test_it_never_changes_the_documents(self):
        ctx = make_ctx()
        before = docs(ctx)
        CoverageEngine().process(ctx)
        self.assertEqual(docs(ctx), before)

    def test_it_only_appends_to_the_report(self):
        ctx = make_ctx()
        ctx.report.warning(engine="x", category="generic", severity="low", rule="earlier",
                           resource="r", issue="i", impact="m", fix="f")
        CoverageEngine().process(ctx)
        self.assertEqual(ctx.report.events[0].rule, "earlier")
        self.assertEqual(len(ctx.report.events), 1 + len(OPAQUE_NAMES))

    def test_opaque_documents_are_flagged_and_typed_ones_are_not(self):
        flags = {ir.name: is_opaque(ir) for ir in make_ctx().irs}
        self.assertEqual(flags, {"db": True, "app-runner": True, "web": False, "nightly": True})


class RunnerOrderingTests(unittest.TestCase):
    def test_coverage_runs_before_any_workflow_engine(self):
        probe = Probe()
        KostralRunner(ServiceBus([probe], parallel_checks=[], seq_after=[])).run(make_ctx())
        self.assertEqual(probe.rules_seen, [COVERAGE_RULE] * len(OPAQUE_NAMES))

    def test_workflow_and_coverage_each_run_exactly_once(self):
        probe, ctx = Probe(), make_ctx()
        KostralRunner(ServiceBus([probe], parallel_checks=[], seq_after=[])).run(ctx)
        self.assertEqual(probe.calls, 1)
        self.assertEqual(len(coverage_events(ctx)), len(OPAQUE_NAMES))

    def test_the_runner_hands_back_what_the_workflow_returns(self):
        ctx = make_ctx()
        self.assertIs(KostralRunner(ServiceBus([], parallel_checks=[], seq_after=[])).run(ctx), ctx)

    def test_any_object_with_run_is_a_workflow(self):
        class Fake:
            def run(self, ctx):
                return "result"
        self.assertEqual(KostralRunner(Fake()).run(make_ctx()), "result")

    def test_workflow_errors_are_not_swallowed(self):
        class Boom(Module):
            name = "boom"
            def process(self, ctx):
                raise RuntimeError("engine failed")
        with self.assertRaises(RuntimeError):
            KostralRunner(ServiceBus([Boom()], parallel_checks=[], seq_after=[])).run(make_ctx())


class CoverageIsMandatoryTests(unittest.TestCase):
    def test_a_workflow_without_a_validator_still_reports_the_gap(self):
        ctx = make_ctx()
        KostralRunner(ServiceBus([], parallel_checks=[], seq_after=[RendererEngine()])).run(ctx)
        self.assertEqual(len(coverage_events(ctx)), len(OPAQUE_NAMES))

    def test_an_empty_workflow_still_reports_the_gap(self):
        ctx = make_ctx()
        KostralRunner(ServiceBus([], parallel_checks=[], seq_after=[])).run(ctx)
        self.assertEqual(len(coverage_events(ctx)), len(OPAQUE_NAMES))

    def test_skip_rules_and_allow_rules_cannot_hide_it(self):
        """DECISION encoded here: coverage is a system responsibility, so the
        user's rule filters (which only apply to workflow rules) do not touch it."""
        for opts in ({"skip_rules": [COVERAGE_RULE]}, {"allow_rules": ["run-as-root"]}):
            with self.subTest(opts=opts):
                ctx = make_ctx(opts=opts)
                KostralRunner(ServiceBus([], parallel_checks=[ValidatorEngine(), SecurityEngine()],
                                         seq_after=[])).run(ctx)
                self.assertEqual(len(coverage_events(ctx)), len(OPAQUE_NAMES))

    def test_a_full_workflow_does_not_report_the_same_gap_twice(self):
        """Catches a leftover validator rule that duplicates the system report."""
        ctx = make_ctx()
        KostralRunner(ServiceBus([OptimizerEngine()],
                                 parallel_checks=[ValidatorEngine(), SecurityEngine()],
                                 seq_after=[RendererEngine()])).run(ctx)
        self.assertEqual([e.resource for e in coverage_events(ctx)], OPAQUE_RESOURCES)

    def test_an_engine_cannot_erase_the_coverage_findings(self):
        class Eraser(Module):
            name = "eraser"
            def process(self, ctx):
                ctx.report.events[:] = [e for e in ctx.report.events if e.rule != COVERAGE_RULE]
        with self.assertRaises(EngineContractViolation):
            KostralRunner(ServiceBus([], parallel_checks=[], seq_after=[Eraser()])).run(make_ctx())


class OpaqueIsUntouchableTests(unittest.TestCase):
    """The contract protects opaque documents from EVERY engine, even mutating ones."""

    def run_engine(self, process, mutates=False, report=False):
        class E(Module):
            name = "e"
            metadata = MappingProxyType({"mutates": mutates})
            def process(self, ctx):
                process(ctx)
                if report:
                    ctx.report.optimization("r", "x", "res", "changed something")
        ctx = make_ctx()
        ServiceBus([E()], parallel_checks=[], seq_after=[]).run(ctx)
        return ctx

    @staticmethod
    def first_opaque(ctx):
        return next(ir for ir in ctx.irs if is_opaque(ir))

    def test_editing_an_opaque_document_is_rejected(self):
        def edit(ctx):
            ir = self.first_opaque(ctx)
            changed = ir.to_manifest()
            changed["metadata"]["name"] = "tampered"
            ir.to_manifest = lambda: changed
        with self.assertRaises(EngineContractViolation):
            self.run_engine(edit)

    def test_editing_is_rejected_even_when_the_engine_may_mutate_and_reports_it(self):
        def edit(ctx):
            ir = self.first_opaque(ctx)
            changed = ir.to_manifest()
            changed["metadata"]["name"] = "tampered"
            ir.to_manifest = lambda: changed
        with self.assertRaisesRegex(EngineContractViolation, "opaque"):
            self.run_engine(edit, mutates=True, report=True)

    def test_removing_an_opaque_document_is_rejected(self):
        with self.assertRaisesRegex(EngineContractViolation, "opaque"):
            self.run_engine(lambda ctx: setattr(ctx, "irs", [ir for ir in ctx.irs if not is_opaque(ir)]),
                            mutates=True, report=True)

    def test_reordering_opaque_documents_is_rejected(self):
        def swap(ctx):
            idx = [i for i, ir in enumerate(ctx.irs) if is_opaque(ir)]
            ctx.irs[idx[0]], ctx.irs[idx[1]] = ctx.irs[idx[1]], ctx.irs[idx[0]]
        with self.assertRaisesRegex(EngineContractViolation, "opaque"):
            self.run_engine(swap, mutates=True, report=True)

    def test_a_mutating_engine_may_still_change_typed_documents_next_to_them(self):
        ctx = make_ctx()
        before = [ir.to_manifest() for ir in ctx.irs if is_opaque(ir)]
        KostralRunner(ServiceBus([OptimizerEngine()], parallel_checks=[], seq_after=[])).run(ctx)
        self.assertEqual([ir.to_manifest() for ir in ctx.irs if is_opaque(ir)], before)
        self.assertTrue(any(e.level == "optimization" for e in ctx.report.events))

    @unittest.expectedFailure
    def test_adding_a_typed_document_is_not_touching_the_opaque_ones(self):
        """KNOWN LIMITATION, DECISION NEEDED. The opaque snapshot records each
        document's absolute position, so a mutating engine that inserts a typed
        document ahead of them shifts every index and is rejected as if it had
        reordered them. Comparing the opaque documents as an ordered list (without
        the index) keeps the 'modified, removed or reordered' guarantee and avoids
        the false alarm. Remove the marker once you decide."""
        def add(ctx):
            from kostral.core.ir import ConfigMapIR
            ctx.irs.insert(0, ConfigMapIR(manifest={
                "apiVersion": "v1", "kind": "ConfigMap",
                "metadata": {"name": "added"}, "data": {"k": "v"}}))
        self.run_engine(add, mutates=True, report=True)


class CliGoesThroughTheRunnerTests(unittest.TestCase):
    """Black box: every command that analyzes manifests reports the gap."""

    @staticmethod
    def gap(out):
        data = json.loads(out)
        return sorted(
            (name, sum(1 for w in r["warnings"] if w["rule"] == COVERAGE_RULE))
            for name, r in data["resources"].items()
            if any(w["rule"] == COVERAGE_RULE for w in r["warnings"]))

    def expected(self):
        return sorted((n, 1) for n in OPAQUE_RESOURCES)

    def test_explain_and_optimize_report_each_gap_exactly_once(self):
        for cmd in (("explain", CASE, "--output", "json"),
                    ("optimize", CASE, "--dry-run", "--output", "json")):
            with self.subTest(cmd=cmd[0]):
                res = koss(*cmd)
                self.assertEqual(res.rc, EXIT_OK, str(res))
                self.assertEqual(self.gap(res.out), self.expected())

    def test_stdin_goes_through_the_runner_too(self):
        with open(CASE) as f:
            res = koss("explain", "-", "--output", "json", stdin=f.read())
        self.assertEqual(self.gap(res.out), self.expected(), str(res))

    def test_remote_with_a_workflow_that_has_no_validator_still_reports_the_gap(self):
        """The point of the layer: a workflow author cannot compose coverage away."""
        with tempfile.TemporaryDirectory() as d:
            wf = os.path.join(d, "workflow.py")
            with open(wf, "w") as f:
                f.write("from kostral.modules.renderer.engine import RendererEngine\n"
                        "workflow = {'seq_before': [], 'parallel_checks': [],\n"
                        "            'seq_after': [RendererEngine()]}\n")
            res = koss("remote", CASE, "--exec", wf, "--output", "json")
        self.assertEqual(res.rc, EXIT_OK, str(res))
        self.assertEqual(self.gap(res.out), self.expected())

    def test_the_runner_does_not_change_the_rendered_manifests(self):
        import yaml
        out = list(yaml.safe_load_all(koss("explain", CASE, "--output", "yaml").out))
        with open(CASE) as f:
            src = [d for d in yaml.safe_load_all(f) if d]
        self.assertEqual([d["kind"] for d in out], [d["kind"] for d in src])


if __name__ == "__main__":
    unittest.main()
