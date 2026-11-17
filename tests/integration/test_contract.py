"""Engine contract enforcement: what the bus and the remote client refuse to accept.

Mutation is declared in engine.metadata["mutates"] (default False), frozen by the bus
when it is built. Local engines: the workflow author may grant it. Remote engines: the
workflow must ask AND the registry entry must approve.

These run in-process (no subprocess) because they test the Python contract itself.
"""
import json
import logging
import os
import tempfile
import threading
import unittest
from types import MappingProxyType
from http.server import BaseHTTPRequestHandler, HTTPServer

from kostral.adapters.remote import HTTPModuleClient
from kostral.adapters.remote.client import RemoteEngineError
from kostral.adapters.remote.registry import from_registry
from kostral.cli.helper import load_yaml_irs
from kostral.core.base import Module, with_metadata
from kostral.core.bus import EngineContractViolation, ServiceBus
from kostral.core.context import RunContext
from kostral.modules.optimizer.engine import OptimizerEngine
from kostral.modules.security.engine import SecurityEngine
from kostral.modules.validator.engine import ValidatorEngine

from .helpers import ROOT

logging.disable(logging.CRITICAL)
BAD = os.path.join(ROOT, "examples/demo/bad.yaml")
GOOD = os.path.join(ROOT, "examples/demo/good.yaml")


def make_ctx(path=BAD):
    return RunContext(irs=load_yaml_irs(path, logging.getLogger()), opts={})


class TestEngine(Module):
    name = "test-engine"

    def __init__(self, mutates, report=False):
        self.metadata = MappingProxyType({"mutates": mutates})
        self.report = report

    def process(self, ctx):
        for ir in ctx.irs:
            if hasattr(ir, "replicas"):
                ir.replicas = 99
        if self.report:
            ctx.report.optimization("r", "x", "res", "changed replicas")


class DeletesFindings(Module):
    name = "deletes-findings"

    def process(self, ctx):
        ctx.report.events.clear()


class BusEnforcementTests(unittest.TestCase):
    def test_checks_phase_refuses_a_mutating_engine(self):
        with self.assertRaises(ValueError):
            ServiceBus([], parallel_checks=[OptimizerEngine()], seq_after=[])

    def test_engine_that_changes_manifests_without_declaring_it_is_rejected(self):
        bus = ServiceBus([TestEngine(mutates=False)], parallel_checks=[], seq_after=[])
        with self.assertRaisesRegex(EngineContractViolation, "mutates=False"):
            bus.run(make_ctx(GOOD))

    def test_mutating_engine_must_report_what_it_changed(self):
        bus = ServiceBus([TestEngine(mutates=True, report=False)], parallel_checks=[], seq_after=[])
        with self.assertRaisesRegex(EngineContractViolation, "without reporting"):
            bus.run(make_ctx(GOOD))

    def test_mutating_engine_that_reports_is_accepted(self):
        ServiceBus([TestEngine(mutates=True, report=True)], parallel_checks=[], seq_after=[]).run(make_ctx(GOOD))

    def test_engine_cannot_delete_earlier_findings(self):
        bus = ServiceBus([], parallel_checks=[ValidatorEngine()], seq_after=[DeletesFindings()])
        with self.assertRaisesRegex(EngineContractViolation, "removed or modified"):
            bus.run(make_ctx())

    def test_engine_metadata_is_per_instance(self):
        a = with_metadata(ValidatorEngine(), mutates=True)
        b = ValidatorEngine()
        self.assertTrue(a.metadata["mutates"])
        self.assertFalse(b.metadata["mutates"])
        self.assertFalse(ValidatorEngine.metadata["mutates"])

    def test_workflow_can_grant_mutation_to_a_local_engine(self):
        engine = with_metadata(TestEngine(mutates=False, report=True), mutates=True)
        ServiceBus([engine], parallel_checks=[], seq_after=[]).run(make_ctx(GOOD))
        self.assertTrue(engine.metadata["mutates"])
        
    def test_workflow_cannot_put_a_mutating_engine_in_parallel_checks(self):
        engine = with_metadata(ValidatorEngine(), mutates=True)
        with self.assertRaisesRegex(ValueError, "parallel_checks"):
            ServiceBus([], parallel_checks=[engine], seq_after=[])

    def test_engine_cannot_edit_its_metadata_in_place(self):
        with self.assertRaises(TypeError):
            ValidatorEngine().metadata["mutates"] = True

    def test_engine_cannot_grant_itself_mutation_during_a_run(self):
        class SelfApproving(TestEngine):
            name = "self-approving"

            def process(self, ctx):
                self.metadata = {"mutates": True}      # too late: the bus froze it
                super().process(ctx)

        bus = ServiceBus([SelfApproving(mutates=False, report=True)], parallel_checks=[], seq_after=[])
        with self.assertRaisesRegex(EngineContractViolation, "mutates=False"):
            bus.run(make_ctx(GOOD))

    def test_a_typo_in_metadata_is_an_error_not_silently_ignored(self):
        with self.assertRaisesRegex(ValueError, "unknown metadata"):
            with_metadata(ValidatorEngine(), mutate=True)
        with self.assertRaisesRegex(ValueError, "must be True or False"):
            with_metadata(ValidatorEngine(), mutates="yes")

    def test_bus_rejects_an_engine_with_unknown_metadata(self):
        class Odd(Module):
            name = "odd"
            metadata = {"mutates": False, "frobnicate": 1}
            def process(self, ctx): pass
        with self.assertRaisesRegex(ValueError, "unknown metadata"):
            ServiceBus([Odd()], parallel_checks=[], seq_after=[])

    def test_parallel_checks_run_in_list_order(self):
        order = []

        class Rec(Module):
            def __init__(self, n): self.name = n
            def process(self, ctx): order.append(self.name)

        ServiceBus([], parallel_checks=[Rec("a"), Rec("b"), Rec("c")], seq_after=[]).run(RunContext())
        self.assertEqual(order, ["a", "b", "c"])


def _serve(responder):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            code, out = responder(body)
            raw = json.dumps(out).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/process"


class RemoteClientTests(unittest.TestCase):
    def run_remote(self, responder):
        server, url = _serve(responder)
        self.addCleanup(server.shutdown)
        ctx = make_ctx()
        ServiceBus([], parallel_checks=[ValidatorEngine(), SecurityEngine()],
                   seq_after=[HTTPModuleClient("r", url)]).run(ctx)
        return ctx

    def test_remote_engine_cannot_erase_findings(self):
        """Old behavior: an empty 'report' in the reply turned FAILED into PASSED."""
        local = make_ctx()
        ServiceBus([], parallel_checks=[ValidatorEngine(), SecurityEngine()], seq_after=[]).run(local)
        self.assertTrue(local.report.has_errors())

        ctx = self.run_remote(lambda b: (200, {"irs": b["irs"], "findings": [], "report": {"events": []}}))
        self.assertEqual(len(ctx.report.events), len(local.report.events))
        self.assertTrue(ctx.report.has_errors())

    def test_remote_findings_are_appended(self):
        finding = {"engine": "remote", "level": "warning", "rule": "r1", "resource": "x",
                   "issue": "i", "fix": "f", "severity": "low", "category": "generic"}
        ctx = self.run_remote(lambda b: (200, {"irs": b["irs"], "findings": [finding]}))
        self.assertEqual(ctx.report.events[-1].rule, "r1")

    def test_reply_without_findings_is_an_error_not_an_empty_result(self):
        with self.assertRaises(RemoteEngineError):
            self.run_remote(lambda b: (200, {"irs": b["irs"]}))

    def test_malformed_finding_is_an_error(self):
        with self.assertRaises(RemoteEngineError):
            self.run_remote(lambda b: (200, {"irs": b["irs"], "findings": [{"level": "error"}]}))

    def test_remote_mutation_needs_workflow_request_and_registry_approval(self):
        url = "http://127.0.0.1:1/process"
        ask = {"mutates": True}
        with self.assertRaisesRegex(ValueError, "not approved"):
            from_registry({"name": "r", "endpoint": url}, metadata=ask)
        with self.assertRaisesRegex(ValueError, "not approved"):
            from_registry(
                {"name": "r", "endpoint": url, "metadata": {"mutates": False}}, metadata=ask)
        ok = from_registry(
            {"name": "r", "endpoint": url, "metadata": {"mutates": True}}, metadata=ask)
        self.assertTrue(ok.metadata["mutates"])

    def test_constructor_is_not_a_way_around_the_registry(self):
        """One obvious way: the plain constructor takes no permissions at all."""
        with self.assertRaises(TypeError):
            HTTPModuleClient("r", "http://127.0.0.1:1/process", metadata={"mutates": True})
        self.assertFalse(HTTPModuleClient("r", "http://127.0.0.1:1/process").metadata["mutates"])

    def test_registry_with_unknown_metadata_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "unknown metadata"):
            from_registry(
                {"name": "r", "endpoint": "http://x/p", "metadata": {"mutate": True}})

    def test_registry_approval_alone_does_not_make_an_engine_mutating(self):
        client = from_registry(
            {"name": "r", "endpoint": "http://127.0.0.1:1/process", "metadata": {"mutates": True}})
        self.assertFalse(client.metadata["mutates"])

    def test_approved_remote_mutation_is_accepted_when_reported(self):
        def edit(body):
            for item in body["irs"]:
                if item["kind"] == "DeploymentIR":
                    item["manifest"]["spec"]["replicas"] = 99
            finding = {"engine": "remote", "level": "optimization", "rule": "r1", "resource": "x",
                       "message": "changed replicas", "severity": "low", "category": "generic"}
            return 200, {"irs": body["irs"], "findings": [finding]}

        server, url = _serve(edit)
        self.addCleanup(server.shutdown)
        client = from_registry(
            {"name": "r", "endpoint": url, "metadata": {"mutates": True}}, metadata={"mutates": True})
        ServiceBus([client], parallel_checks=[], seq_after=[]).run(make_ctx())

    def test_remote_that_changes_manifests_without_permission_is_rejected(self):
        def tamper(body):
            for item in body["irs"]:
                item["manifest"].setdefault("metadata", {})["labels"] = {"tampered": "yes"}
            return 200, {"irs": body["irs"], "findings": []}
        with self.assertRaises(EngineContractViolation):
            self.run_remote(tamper)


class LoaderOrderTests(unittest.TestCase):
    def test_directory_input_is_read_in_sorted_filename_order(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("c", "a", "b"):
                with open(os.path.join(d, f"{name}.yaml"), "w") as f:
                    f.write(f"apiVersion: v1\nkind: ConfigMap\nmetadata: {{name: {name}}}\ndata: {{k: v}}\n")
            names = [ir.name for ir in load_yaml_irs(d, logging.getLogger())]
        self.assertEqual(names, ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
