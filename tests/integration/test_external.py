"""External scanners: the `external` profile.

Three layers, tested separately so a failure says which one broke:
  1. the SARIF mapper (pure),
  2. running a tool (`run_tool`) and the local / remote engines built on it,
  3. the contract: profile handshake, read-only, findings only appended.

No real scanner is needed: `examples/external/example_scanner.py` writes SARIF the
way Trivy does. The Trivy fixture is generated (see its `properties.fixture`).
"""
import copy
import itertools
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import HTTPServer
from pathlib import Path

import requests

from kostral.adapters.external.apply import documents_for
from kostral.adapters.external.client import RemoteExternalClient
from kostral.adapters.external.engine import ExternalToolEngine
from kostral.adapters.external.runner import ToolError, run_tool
from kostral.adapters.external.sarif import (DEFAULT_PROFILE, SarifMappingError, SarifProfile,
                                             sarif_to_findings)
from kostral.adapters.external.server import _create_handler, describe
from kostral.adapters.remote import HTTPModuleClient
from kostral.adapters.remote.client import RemoteEngineError
from kostral.adapters.remote.registry import from_registry
from kostral.cli.helper import load_yaml_irs
from kostral.core.base import Module, Report
from kostral.core.bus import EngineContractViolation, ServiceBus
from kostral.core.context import RunContext
from kostral.core.contract import check_descriptor, verify_descriptor

from .fakes import TEST_TOKEN, TEST_TOKEN_ENV, _serve, descriptor, pinned_entry
from .helpers import EXIT_CRASH, EXIT_FINDINGS, ROOT, koss

logging.disable(logging.CRITICAL)

BAD = str(ROOT / "examples/demo/bad.yaml")
SCANNER = str(ROOT / "examples/external/example_scanner.py")
SCANNER_CMD = [sys.executable, SCANNER, "{dir}"]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "trivy-good.sarif.json"
HELP_TOO = SarifProfile.from_dict({"fix_sources": ["fixes", "help", "help_uri"]})  # the example scanner uses rule.help


def external(**kw):
    return {**descriptor(**kw), "profile": "external"}


def sarif(results=None, rules=None):
    return {"version": "2.1.0",
            "runs": [{"tool": {"driver": {"name": "t", "version": "9", "rules": rules or []}},
                      "results": [] if results is None else results}]}


def result(rule="R1", level="error", text="bad thing", uri="0000.yaml", line=3, **extra):
    return {"ruleId": rule, "level": level, "message": {"text": text},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": uri}, "region": {"startLine": line}}}],
            **extra}


RULE_R1 = {"id": "R1", "helpUri": "https://example.invalid/R1"}


def ctx_for(path=BAD):
    return RunContext(irs=load_yaml_irs(str(path), logging.getLogger()), opts={})


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --------------------------------------------------------------------------- 1. mapper

class SarifMapperTests(unittest.TestCase):
    def map(self, log, profile=DEFAULT_PROFILE, **kw):
        return sarif_to_findings(log, profile, engine="t", **kw)

    def test_levels_follow_the_profile_table(self):
        """Guarantee: an external finding's level and severity come from a pinned table, never from a guess."""
        log = sarif([result("A", "error"), result("B", "warning", uri="b"), result("C", "note", uri="c")],
                    rules=[{"id": r, "helpUri": "u"} for r in "ABC"])
        got = {f["rule"]: (f["level"], f["severity"]) for f in self.map(log)}
        self.assertEqual(got, {"A": ("error", "HIGH"), "B": ("warning", "medium"), "C": ("warning", "low")})

    def test_a_profile_can_decide_differently_and_it_is_explicit(self):
        strict = SarifProfile.from_dict({"levels": {"note": ["error", "HIGH"]}})
        log = sarif([result("A", "note")], rules=[{"id": "A", "helpUri": "u"}])
        self.assertEqual(self.map(log, strict)[0]["level"], "error")

    def test_findings_are_exactly_what_the_report_accepts(self):
        log = sarif([result("R1", "error"), result("R1", "note", uri="x")], rules=[RULE_R1])
        report = Report()
        report.extend(self.map(log))                 # same validation every local rule goes through
        self.assertEqual([e.level for e in report.events], ["error", "warning"])
        self.assertTrue(report.has_errors())

    def test_order_never_depends_on_the_tool(self):
        """Guarantee: the order of external findings does not depend on the order the tool used."""
        results = [result("R1", "error", uri="0001.yaml", line=9), result("R1", "note", uri="0000.yaml", line=2),
                   result("R1", "warning", uri="0000.yaml", line=1, text="zzz")]
        outputs = {json.dumps(self.map(sarif(list(p), rules=[RULE_R1])))
                   for p in itertools.permutations(results)}
        self.assertEqual(len(outputs), 1)

    def test_level_falls_back_to_the_rule_default_then_to_warning(self):
        no_level = result("R1")
        del no_level["level"]
        with_default = sarif([no_level], rules=[{**RULE_R1, "defaultConfiguration": {"level": "error"}}])
        self.assertEqual(self.map(with_default)[0]["level"], "error")
        self.assertEqual(self.map(sarif([no_level], rules=[RULE_R1]))[0]["level"], "warning")   # SARIF's default

    def test_an_unmapped_level_is_an_error_not_a_guess(self):
        """Guarantee: an unmapped scanner result is an error (exit 3), never a silently shorter report."""
        for level in ("none", "critical"):
            with self.subTest(level=level):
                with self.assertRaisesRegex(SarifMappingError, "not in the mapping"):
                    self.map(sarif([result("R1", level)], rules=[RULE_R1]))
     
    def test_fix_comes_only_from_the_sources_the_profile_lists(self):
        with_fixes = result("R1", fixes=[{"description": {"text": "do the thing"}}])
        helpful = [{"id": "R1", "help": {"text": "Read this\nfirst"}, "helpUri": "https://example.invalid/R1"}]
        # default sources: fixes, then help_uri. rule.help is NOT used (some tools put metadata there)
        self.assertEqual(self.map(sarif([with_fixes], rules=helpful))[0]["fix"], "do the thing")
        self.assertEqual(self.map(sarif([result("R1")], rules=helpful))[0]["fix"], "see https://example.invalid/R1")
        self.assertEqual(self.map(sarif([result("R1")], rules=helpful), HELP_TOO)[0]["fix"], "Read this first")

    def test_no_source_for_fix_is_an_error_unless_the_profile_names_a_default(self):
        """Guarantee: KOSTRAL never invents a fix for an external finding."""
        log = sarif([result("R1")], rules=[{"id": "R1"}])
        with self.assertRaisesRegex(SarifMappingError, "does not invent"):
            self.map(log)
        named = SarifProfile.from_dict({"default_fix": "see the tool's documentation"})
        self.assertEqual(self.map(log, named)[0]["fix"], "see the tool's documentation")

    def test_a_log_that_cannot_be_trusted_is_an_error_never_an_empty_report(self):
        """Guarantee: an untrustworthy scanner log is an error, never an empty result."""
        good = sarif([])
        broken = {
            "not an object": "x",
            "wrong version": {**good, "version": "2.0.0"},
            "no runs": {"version": "2.1.0", "runs": []},
            "results absent (analysis not performed)": {"version": "2.1.0", "runs": [{"tool": {"driver": {"name": "t"}}}]},
            "results null": {"version": "2.1.0", "runs": [{"tool": {"driver": {"name": "t"}}, "results": None}]},
            "result without rule": sarif([{"level": "error", "message": {"text": "x"}}]),
            "result without message": sarif([{"ruleId": "R1", "level": "error"}], rules=[RULE_R1]),
        }
        for label, log in broken.items():
            with self.subTest(label):
                with self.assertRaises(SarifMappingError):
                    self.map(log)

    def test_an_empty_results_list_is_a_clean_run(self):
        self.assertEqual(self.map(sarif([])), [])

    def test_resource_comes_from_the_document_and_is_never_parsed_from_the_message(self):
        log = sarif([result("R1", text="Container 'x' of Deployment 'liar' is bad", uri="0001.yaml")], rules=[RULE_R1])
        names = {"0001.yaml": "real-name"}
        self.assertEqual(self.map(log, resolve=names.get)[0]["resource"], "real-name")
        self.assertEqual(self.map(log)[0]["resource"], "0001.yaml")            # not resolvable: the uri, as given
        nowhere = result("R1")
        del nowhere["locations"]
        self.assertEqual(self.map(sarif([nowhere], rules=[RULE_R1]))[0]["resource"], "<unlocated>")

    def test_profile_rejects_what_it_does_not_understand(self):
        for bad in ({"level": {}}, {"levels": {"error": ["info", "HIGH"]}}, {"levels": {"error": ["error", "SEVERE"]}},
                    {"levels": {}}, {"fix_sources": ["fixes", "fixes"]}, {"fix_sources": ["magic"]},
                    {"default_fix": ""}, {"category": "vibes"}, "nope"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    SarifProfile.from_dict(bad)

    def test_the_trivy_shaped_fixture_maps_to_two_errors_and_eight_warnings(self):
        """Ids, messages and lines are from a real Trivy 0.76.2 run on examples/demo/good.yaml; the SARIF
        envelope is synthetic. It proves the mapping rules, not Trivy's SARIF."""
        log = json.loads(FIXTURE.read_text())
        findings = self.map(log, SarifProfile.from_dict({"fix_sources": ["fixes", "help_uri"]}))
        self.assertEqual(len(findings), 10)
        self.assertEqual(sorted(f["level"] for f in findings), ["error"] * 2 + ["warning"] * 8)
        self.assertEqual({f["rule"] for f in findings if f["level"] == "error"}, {"KSV-0014", "KSV-0118"})
        self.assertTrue(all(f["fix"].startswith("see https://avd.aquasec.com/") for f in findings))
        self.assertEqual(findings, self.map(copy.deepcopy(log), SarifProfile.from_dict({"fix_sources": ["fixes", "help_uri"]})))


# --------------------------------------------------------------------------- 2. running a tool

class RunToolTests(unittest.TestCase):
    def py(self, code):
        return [sys.executable, "-c", code, "{dir}"]

    def run_it(self, command, manifests=({"kind": "Deployment"},), **kw):
        return run_tool(command, list(manifests), **kw)

    def test_each_document_is_its_own_file_in_order(self):
        code = ("import sys,os,json;print(json.dumps({'files':sorted(os.listdir(sys.argv[1])),"
                "'first':open(sys.argv[1]+'/0000.yaml').read()}))")
        out = self.run_it(self.py(code), [{"kind": "Deployment", "a": 1}, {"kind": "Service"}])
        self.assertEqual(out["files"], ["0000.yaml", "0001.yaml"])
        self.assertIn("kind: Deployment", out["first"])

    def test_every_way_a_tool_can_break_is_a_tool_error(self):
        """Guarantee: a missing, failing, slow or garbled scanner is an error, never an empty result."""
        cases = {
            "not installed": (["no-such-tool-xyz", "{dir}"], {}, "not installed"),
            "non-zero exit": (self.py("import sys; sys.stderr.write('boom'); sys.exit(2)"), {}, "exited with 2: boom"),
            "timeout": (self.py("import time; time.sleep(5)"), {"timeout": 0.3}, "did not finish"),
            "not JSON": (self.py("print('hello')"), {}, "did not write JSON"),
            "JSON but not an object": (self.py("print('[1]')"), {}, "not a SARIF object"),
            "too much output": (self.py("print('{\"x\": \"'  'a'*5000 + '\"}')"), {"max_output_bytes": 100}, "more than 100 bytes"),
        }
        for label, (command, kw, message) in cases.items():
            with self.subTest(label):
                with self.assertRaisesRegex(ToolError, message):
                    self.run_it(command, **kw)

    def test_the_command_must_say_where_the_documents_are(self):
        for bad in ([], "trivy config", ["trivy", "config"], ["trivy", ""]):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.run_it(bad)

    def test_unmodeled_kinds_reach_the_scanner_and_a_secret_does_not_unless_named(self):
        """ADR1: a scanner must see what the user wrote, not only what KOSTRAL models."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.yaml"
            path.write_text("kind: StatefulSet\nmetadata: {name: db}\n---\nkind: Secret\nmetadata: {name: s}\n"
                            "data: {k: dg==}\n---\nkind: Deployment\nmetadata: {name: web}\n")
            ctx = ctx_for(path)
        kinds = lambda wanted: [d["kind"] for d in documents_for(ctx, wanted)]
        self.assertEqual(kinds(["*"]), ["StatefulSet", "Deployment"])                  # original order, no Secret
        self.assertEqual(kinds(["*", "Secret"]), ["StatefulSet", "Secret", "Deployment"])
        self.assertEqual(kinds(["Deployment"]), ["Deployment"])


class LocalExternalEngineTests(unittest.TestCase):
    def engine(self, name="example-scanner", **kw):
        return ExternalToolEngine(name, SCANNER_CMD, mapping=HELP_TOO, **kw)

    def test_findings_are_appended_after_what_was_already_reported(self):
        class First(Module):
            name = "first"
            def process(self, ctx):
                ctx.report.warning(rule="pre", engine="first", resource="backend", issue="i", fix="f")
        ctx = ctx_for()
        ServiceBus([], parallel_checks=[First(), self.engine()]).run(ctx)
        self.assertEqual(ctx.report.events[0].rule, "pre")
        self.assertEqual({e.rule for e in ctx.report.events[1:]}, {"EX001", "EX002"})
        self.assertEqual({e.resource for e in ctx.report.events[1:]}, {"backend"})   # from the document, not the message
        self.assertTrue(ctx.report.has_errors())

    def test_documents_are_untouched_and_the_raw_log_is_namespaced_by_engine(self):
        ctx = ctx_for()
        before = [ir.to_manifest() for ir in ctx.irs]
        ServiceBus([], parallel_checks=[self.engine(keep_raw=True)]).run(ctx)
        self.assertEqual([ir.to_manifest() for ir in ctx.irs], before)
        art = ctx.artifacts["example-scanner"]
        self.assertEqual((art["tool"], art["version"], art["documents_sent"]), ("example-scanner", "1.0.0", 2))   # bad.yaml: a Deployment and a Service
        self.assertIn("runs", art["raw"])

    def test_it_is_read_only_so_it_may_sit_in_parallel_checks_and_cannot_be_granted_mutation_by_accident(self):
        self.assertFalse(self.engine().metadata["mutates"])
        ServiceBus([], parallel_checks=[self.engine()])            # builds: read-only engines are allowed there

    def test_same_input_same_findings(self):
        runs = []
        for _ in range(2):
            ctx = ctx_for()
            self.engine().process(ctx)
            runs.append([e.to_dict() for e in ctx.report.events])
        self.assertEqual(runs[0], runs[1])

    def test_a_broken_tool_raises_it_is_not_an_empty_report(self):
        broken = ExternalToolEngine("broken", [sys.executable, "-c", "import sys; sys.exit(3)", "{dir}"])
        ctx = ctx_for()
        with self.assertRaises(ToolError):
            ServiceBus([], parallel_checks=[broken]).run(ctx)
        self.assertEqual(ctx.report.events, [])

    def test_a_bad_log_changes_nothing(self):
        bad = ExternalToolEngine("bad", [sys.executable, "-c", "print('{\"version\": \"2.1.0\", \"runs\": []}')", "{dir}"])
        ctx = ctx_for()
        with self.assertRaises(SarifMappingError):
            bad.process(ctx)
        self.assertEqual((ctx.report.events, ctx.artifacts), ([], {}))

    def test_nothing_of_an_accepted_kind_means_no_scan_and_the_artifact_says_so(self):
        never_run = ExternalToolEngine("never", ["no-such-tool-xyz", "{dir}"], input_kinds=["StatefulSet"])
        ctx = ctx_for()
        never_run.process(ctx)
        self.assertEqual(ctx.artifacts["never"]["documents_sent"], 0)
        self.assertEqual(ctx.report.events, [])

    def test_two_engines_cannot_share_a_name_and_overwrite_each_other(self):
        ctx = ctx_for()
        self.engine().process(ctx)
        with self.assertRaisesRegex(ValueError, "engine names must be unique"):
            self.engine().process(ctx)


# --------------------------------------------------------------------------- 3. contract

class ProfileHandshakeTests(unittest.TestCase):
    def test_descriptor_profile_is_optional_and_checked(self):
        self.assertEqual(check_descriptor(descriptor()), descriptor())                    # old engines: unchanged
        self.assertEqual(check_descriptor(external())["profile"], "external")
        with self.assertRaises(ValueError):
            check_descriptor({**descriptor(), "profile": "magic"})

    def test_verify_refuses_a_profile_mismatch_in_both_directions(self):
        with self.assertRaisesRegex(EngineContractViolation, "'external' profile"):
            verify_descriptor(external(), name="r", pins=None, mutates=False)             # native client, external server
        with self.assertRaisesRegex(EngineContractViolation, "'native' profile"):
            verify_descriptor(descriptor(), name="r", pins=None, mutates=False, profile="external")

    def test_an_external_scanner_cannot_declare_mutation(self):
        with self.assertRaisesRegex(EngineContractViolation, "read-only"):
            verify_descriptor(external(mutates=True), name="r", pins=None, mutates=True, profile="external")

    def test_registry_builds_the_right_client_and_refuses_nonsense(self):
        url = "http://127.0.0.1:1/process"
        self.assertIsInstance(from_registry({**pinned_entry(url), "profile": "external"}), RemoteExternalClient)
        self.assertNotIsInstance(from_registry(pinned_entry(url)), RemoteExternalClient)
        self.assertIsInstance(from_registry(pinned_entry(url)), HTTPModuleClient)
        for label, entry, meta in (
                ("unknown profile", {**pinned_entry(url), "profile": "magic"}, None),
                ("mapping on a native entry", {**pinned_entry(url), "mapping": {}}, None),
                ("bad mapping", {**pinned_entry(url), "profile": "external", "mapping": {"levels": {}}}, None),
                ("approved mutation", {**pinned_entry(url, mutates=True), "profile": "external"}, None),
                ("requested mutation", {**pinned_entry(url, mutates=True), "profile": "external"}, {"mutates": True})):
            with self.subTest(label), self.assertRaises(ValueError):
                from_registry(entry, metadata=meta)


class RemoteExternalClientTests(unittest.TestCase):
    def setUp(self):
        self.servers = []
        self.addCleanup(lambda: [s.shutdown() for s in self.servers])

    def serve(self, responder, declared=None, log=None):
        server, url = _serve(responder, declared=declared or external(), log=log)
        self.servers.append(server)
        return url

    def client(self, url, **kw):
        return from_registry({**pinned_entry(url, **kw), "profile": "external", "mapping": {"fix_sources": ["help_uri"]}})

    @staticmethod
    def good(body):
        return 200, {"sarif": sarif([result("R1", "error")], rules=[RULE_R1])}

    def test_it_sends_documents_only_and_appends_what_comes_back(self):
        seen = []
        def responder(body):
            seen.append(body)
            return self.good(body)
        ctx = ctx_for()
        ctx.opts = {"allow_rules": ["secret-option"]}
        self.client(self.serve(responder)).process(ctx)
        self.assertEqual(set(seen[0]), {"documents"})                           # no irs, no opts, no report
        self.assertEqual(seen[0]["documents"][0]["kind"], "Deployment")          # raw manifest, not an IR class name
        (event,) = ctx.report.events
        self.assertEqual((event.engine, event.rule, event.level, event.resource), ("r", "R1", "error", "backend"))
        self.assertEqual(ctx.artifacts["r"]["tool"], "t")

    def test_a_secret_is_held_back_by_the_wildcard_and_sent_only_when_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.yaml"
            path.write_text("kind: Deployment\nmetadata: {name: web}\n---\nkind: Secret\nmetadata: {name: s}\ndata: {k: dg==}\n")
            for kinds, expected in ((("*",), ["Deployment"]), (("*", "Secret"), ["Deployment", "Secret"])):
                with self.subTest(kinds=kinds):
                    seen = []
                    url = self.serve(lambda b: (seen.append(b), self.good(b))[1], declared=external(kinds=kinds))
                    self.client(url, kinds=kinds).process(ctx_for(path))
                    self.assertEqual([d["kind"] for d in seen[0]["documents"]], expected)

    def test_a_reply_is_a_sarif_log_and_nothing_else(self):
        """Guarantee: an external reply cannot replace the report or change a manifest.
        No `findings` to replace the report with, no `irs` to change the manifests."""
        log = sarif([])
        for label, reply in {"with findings": {"sarif": log, "findings": []}, "with irs": {"sarif": log, "irs": []},
                             "native shaped": {"irs": [], "findings": []}, "sarif not an object": {"sarif": "x"},
                             "list": [log]}.items():
            with self.subTest(label):
                ctx = ctx_for()
                with self.assertRaisesRegex(RemoteEngineError, "must be exactly"):
                    self.client(self.serve(lambda b, r=reply: (200, r))).process(ctx)
                self.assertEqual(ctx.report.events, [])

    def test_every_bad_answer_is_an_error_and_leaves_the_report_alone(self):
        cases = {"server error": lambda b: (500, {"error": "tool blew up"}),
                 "bad SARIF": lambda b: (200, {"sarif": {"version": "2.1.0", "runs": []}}),
                 "unmapped level": lambda b: (200, {"sarif": sarif([result("R1", "none")], rules=[RULE_R1])})}
        for label, responder in cases.items():
            with self.subTest(label):
                ctx = ctx_for()
                with self.assertRaises(RemoteEngineError):
                    self.client(self.serve(responder)).process(ctx)
                self.assertEqual((ctx.report.events, ctx.artifacts), ([], {}))

    def test_a_reply_over_the_size_limit_is_refused(self):
        client = self.client(self.serve(lambda b: (200, {"sarif": sarif([result("R1")] * 200, rules=[RULE_R1])})))
        client.max_response_bytes = 1000
        with self.assertRaisesRegex(RemoteEngineError, "larger than 1000"):
            client.process(ctx_for())

    def test_a_native_server_is_refused_before_anything_is_sent(self):
        """Guarantee: a server of the wrong profile gets no document."""
        log = []
        url = self.serve(self.good, declared=descriptor(), log=log)                  # native descriptor
        with self.assertRaisesRegex(EngineContractViolation, "'native' profile"):
            self.client(url).process(ctx_for())
        self.assertEqual(log, ["GET /describe"])                                     # no POST: no document left

    def test_an_external_server_is_refused_by_a_native_client(self):
        log = []
        url = self.serve(self.good, declared=external(), log=log)
        with self.assertRaisesRegex(EngineContractViolation, "'external' profile"):
            from_registry(pinned_entry(url)).process(ctx_for())
        self.assertEqual(log, ["GET /describe"])

    def test_a_scanner_that_claims_it_mutates_is_refused(self):
        """Guarantee: an external scanner is read-only."""
        log = []
        url = self.serve(self.good, declared=external(mutates=True), log=log)
        with self.assertRaisesRegex(EngineContractViolation, "read-only"):
            self.client(url).process(ctx_for())
        self.assertEqual(log, ["GET /describe"])

    def test_an_unreachable_scanner_is_an_error_not_an_empty_report(self):
        url = f"http://127.0.0.1:{free_port()}/process"
        with self.assertRaises(RemoteEngineError):
            self.client(url).process(ctx_for())

    def test_it_cannot_erase_earlier_findings_through_the_bus(self):
        class First(Module):
            name = "first"
            def process(self, ctx):
                ctx.report.error(rule="pre", engine="first", resource="backend", issue="i", fix="f")
        ctx = ctx_for()
        ServiceBus([], parallel_checks=[First(), self.client(self.serve(lambda b: (200, {"sarif": sarif([])})))]).run(ctx)
        self.assertEqual([e.rule for e in ctx.report.events], ["pre"])               # clean scan adds nothing, removes nothing
        self.assertTrue(ctx.report.has_errors())


class RealExternalServerTests(unittest.TestCase):
    """The shipped server around the example scanner, over real HTTP."""

    def start(self, command=None, **kw):
        handler = _create_handler(describe("example-scanner", "1.0.0", ["*"]), command or SCANNER_CMD, TEST_TOKEN,
                                  **{"timeout": 30, "max_request_bytes": 1_000_000, "max_output_bytes": 1_000_000, **kw})
        server = HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close()))
        return f"http://127.0.0.1:{server.server_port}"

    def client(self, base):
        return from_registry({**pinned_entry(base + "/process", name="example-scanner", kinds=("*",)),
                              "profile": "external", "mapping": {"fix_sources": ["fixes", "help", "help_uri"]}})

    def test_remote_gives_the_same_findings_as_local(self):
        """Guarantee: a remote scanner run matches the local run for the same input."""
        remote_ctx, local_ctx = ctx_for(), ctx_for()
        self.client(self.start()).process(remote_ctx)
        ExternalToolEngine("example-scanner", SCANNER_CMD, mapping=HELP_TOO).process(local_ctx)
        self.assertEqual([e.to_dict() for e in remote_ctx.report.events], [e.to_dict() for e in local_ctx.report.events])
        self.assertEqual(len(remote_ctx.report.events), 2)

    def test_the_descriptor_declares_the_external_profile_and_read_only(self):
        base = self.start()
        declared = requests.get(base + "/describe", headers={"Authorization": f"Bearer {TEST_TOKEN}"}, timeout=5).json()
        self.assertEqual((declared["profile"], declared["mutates"]), ("external", False))

    def test_every_request_needs_the_token_including_unknown_paths(self):
        base = self.start()
        for method, path in (("GET", "/describe"), ("POST", "/process"), ("GET", "/nope")):
            with self.subTest(path=path):
                self.assertEqual(requests.request(method, base + path, timeout=5).status_code, 401)

    def test_what_the_server_refuses(self):
        base = self.start(max_request_bytes=300)
        auth = {"Authorization": f"Bearer {TEST_TOKEN}"}
        post = lambda body, **kw: requests.post(base + "/process", headers=auth, timeout=5, **kw, **({"json": body} if body is not None else {}))
        self.assertEqual(post({"documents": [{"kind": "Deployment", "pad": "x" * 500}]}).status_code, 413)
        self.assertEqual(post({"nothing": 1}).status_code, 400)
        self.assertEqual(post({"documents": []}).status_code, 400)
        self.assertEqual(requests.post(base + "/process", headers=auth, data=b"{nope", timeout=5).status_code, 400)

    def test_a_kind_the_server_did_not_declare_gets_400(self):
        handler = _create_handler(describe("s", "1.0.0", ["Deployment"]), SCANNER_CMD, TEST_TOKEN,
                                  timeout=30, max_request_bytes=10_000, max_output_bytes=10_000)
        server = HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close()))
        reply = requests.post(f"http://127.0.0.1:{server.server_port}/process", timeout=5,
                              headers={"Authorization": f"Bearer {TEST_TOKEN}"}, json={"documents": [{"kind": "Secret"}]})
        self.assertEqual(reply.status_code, 400)

    def test_a_broken_tool_behind_the_server_is_a_502_and_an_error_for_the_client(self):
        base = self.start(command=[sys.executable, "-c", "import sys; sys.stderr.write('scanner crashed'); sys.exit(1)", "{dir}"])
        with self.assertRaisesRegex(RemoteEngineError, "502.*scanner crashed"):
            self.client(base).process(ctx_for())


# --------------------------------------------------------------------------- the CLI end to end

def _write_workflow(directory, command_expr):
    path = Path(directory) / "wf.py"
    path.write_text(
        "import sys\n"
        "from kostral.adapters.external.engine import ExternalToolEngine\n"
        "from kostral.modules.renderer.engine import RendererEngine\n"
        f"workflow = {{'seq_before': [], 'parallel_checks': [ExternalToolEngine('broken', {command_expr})],\n"
        "            'seq_after': [RendererEngine()]}\n")
    return path


class ExternalCliTests(unittest.TestCase):
    def test_findings_are_exit_1_and_the_output_is_deterministic(self):
        runs = [koss("remote", "examples/demo/bad.yaml", "--exec", "examples/external/local_workflow.py", "--output", "json")
                for _ in range(2)]
        self.assertEqual(runs[0].rc, EXIT_FINDINGS, str(runs[0]))
        self.assertEqual(runs[0].out, runs[1].out)
        rules = {e["rule"] for e in json.loads(runs[0].out)["resources"]["backend"]["errors"]}
        self.assertIn("EX001", rules)

    def test_a_broken_scanner_is_exit_3_not_exit_1_and_not_a_pass(self):
        """CI must tell "the manifest failed" (1) from "the scanner broke" (3)."""
        with tempfile.TemporaryDirectory() as tmp:
            for label, expr in (("exits 2", "[sys.executable, '-c', 'import sys; sys.exit(2)', '{dir}']"),
                                ("not installed", "['no-such-tool-xyz', '{dir}']")):
                with self.subTest(label):
                    res = koss("remote", "examples/demo/good.yaml", "--exec", _write_workflow(tmp, expr), "--output", "json")
                    self.assertEqual(res.rc, EXIT_CRASH, str(res))
                    self.assertNotIn('"status"', res.out)


class RemoteExternalCliTests(unittest.TestCase):
    PORT = 9011

    @classmethod
    def setUpClass(cls):
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", cls.PORT)) == 0:
                raise unittest.SkipTest(f"port {cls.PORT} is already in use")
        cls.token = "scanner-token-0123456789abcdef"
        os.environ["KOSTRAL_TOKEN_SCANNER"] = cls.token
        cls.addClassCleanup(os.environ.pop, "KOSTRAL_TOKEN_SCANNER", None)
        cls.proc = subprocess.Popen([sys.executable, str(ROOT / "examples/external/scanner_server.py")], cwd=str(ROOT),
                                    env=dict(os.environ, PYTHONPATH=str(ROOT)),
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 15
        while time.time() < deadline:
            with socket.socket() as s:
                s.settimeout(0.3)
                if s.connect_ex(("127.0.0.1", cls.PORT)) == 0:
                    return
            time.sleep(0.2)
        cls.tearDownClass()
        raise unittest.SkipTest("example scanner server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.proc.kill()

    def test_remote_run_matches_the_local_run(self):
        remote = koss("remote", "examples/demo/bad.yaml", "--exec", "examples/external/workflow.py", "--output", "json")
        local = koss("remote", "examples/demo/bad.yaml", "--exec", "examples/external/local_workflow.py", "--output", "json")
        self.assertEqual(remote.rc, EXIT_FINDINGS, str(remote))
        self.assertEqual((remote.rc, remote.out), (local.rc, local.out))


if __name__ == "__main__":
    unittest.main()
