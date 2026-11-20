"""Hold-back: a remote engine receives only the kinds it declared.

Everything else, above all Secrets, stays in this process, is never serialized,
and is put back in its original position after the call. (Not redaction: a
redacted value coming back would overwrite the real one.)

  input_kinds ["Deployment"]            -> Deployments only
  input_kinds ["*"]                     -> every kind EXCEPT Secret
  input_kinds ["Deployment", "Secret"]  -> Secrets only because they are named
"""
import json
import logging
import os
import threading
import unittest
from http.server import HTTPServer

from kostral.adapters.remote import HTTPModuleClient
from kostral.adapters.remote.client import RemoteEngineError, merge_back, split_for_engine
from kostral.adapters.remote.registry import from_registry
from kostral.adapters.remote.server import _create_handler, describe
from kostral.cli.helper import load_yaml_irs
from kostral.core.base import Module
from kostral.core.bus import ServiceBus
from kostral.core.context import RunContext
from kostral.core.contract import kind_accepted

from .fakes import _serve, descriptor, pinned_entry
from .helpers import ROOT

logging.disable(logging.CRITICAL)
RESOURCES = os.path.join(ROOT, "examples/resources")       # ConfigMap, Deployment, Ingress, PVC, Secret, Service
SECRET_VALUE = "c3VwZXJzZWNyZXQ="                           # base64 of the example password


def make_ctx():
    return RunContext(irs=load_yaml_irs(RESOURCES, logging.getLogger()), opts={})


def kinds_of(irs):
    return [ir.to_manifest()["kind"] for ir in irs]


class KindRuleTests(unittest.TestCase):
    def test_named_kinds_are_accepted(self):
        self.assertTrue(kind_accepted(["Deployment"], "Deployment"))
        self.assertFalse(kind_accepted(["Deployment"], "Service"))

    def test_a_wildcard_means_everything_except_secrets(self):
        self.assertTrue(kind_accepted(["*"], "StatefulSet"))
        self.assertTrue(kind_accepted(["*"], "ConfigMap"))
        self.assertFalse(kind_accepted(["*"], "Secret"))

    def test_a_secret_needs_to_be_named(self):
        self.assertTrue(kind_accepted(["*", "Secret"], "Secret"))
        self.assertTrue(kind_accepted(["Secret"], "Secret"))


class SplitAndMergeTests(unittest.TestCase):
    def test_split_keeps_the_held_documents_with_their_positions(self):
        irs = make_ctx().irs
        to_send, held = split_for_engine(irs, ["Deployment", "Service"])
        self.assertEqual(kinds_of(to_send), ["Deployment", "Service"])
        self.assertEqual({i: irs[i].to_manifest()["kind"] for i in held},
                         {0: "ConfigMap", 2: "Ingress", 3: "PersistentVolumeClaim", 4: "Secret"})

    def test_merge_restores_the_original_list(self):
        irs = make_ctx().irs
        to_send, held = split_for_engine(irs, ["Deployment", "Service"])
        merged = merge_back(to_send, held, len(irs))
        self.assertEqual([i.to_manifest() for i in merged], [i.to_manifest() for i in irs])

    def test_a_wildcard_still_holds_back_the_secret(self):
        to_send, held = split_for_engine(make_ctx().irs, ["*"])
        self.assertNotIn("Secret", kinds_of(to_send))
        self.assertEqual([ir.to_manifest()["kind"] for ir in held.values()], ["Secret"])

    def test_nothing_declared_means_nothing_sent(self):
        irs = make_ctx().irs
        to_send, held = split_for_engine(irs, ["CronJob"])
        self.assertEqual(to_send, [])
        self.assertEqual(len(held), len(irs))


class ClientSendsOnlyWhatWasDeclaredTests(unittest.TestCase):
    def run_client(self, kinds, *, mutates=False, responder=None, declared_kinds=None, pinned=True):
        bodies = []

        def echo(body):
            bodies.append(body)
            return 200, {"irs": body["irs"], "findings": []}

        server, url = _serve(responder or echo,
                             declared=descriptor(kinds=declared_kinds or kinds, mutates=mutates))
        self.addCleanup(server.shutdown)
        if pinned:
            client = from_registry(pinned_entry(url, kinds=kinds, mutates=mutates or None),
                                   metadata={"mutates": True} if mutates else None)
        else:
            client = HTTPModuleClient("r", url)
        ctx = make_ctx()
        before = [i.to_manifest() for i in ctx.irs]
        ServiceBus([client] if mutates else [], parallel_checks=[] if mutates else [client],
                   seq_after=[]).run(ctx)
        return ctx, before, bodies

    def test_the_engine_receives_only_its_declared_kinds(self):
        ctx, before, bodies = self.run_client(("Deployment", "Service"))
        self.assertEqual([i["manifest"]["kind"] for i in bodies[0]["irs"]], ["Deployment", "Service"])

    def test_a_secret_never_reaches_an_engine_that_did_not_ask_for_it(self):
        ctx, before, bodies = self.run_client(("Deployment",))
        raw = json.dumps(bodies[0])
        self.assertNotIn("SecretIR", raw)
        self.assertNotIn(SECRET_VALUE, raw)

    def test_a_wildcard_engine_gets_everything_but_the_secret(self):
        ctx, before, bodies = self.run_client(("*",))
        sent = [i["manifest"]["kind"] for i in bodies[0]["irs"]]
        self.assertEqual(sent, ["ConfigMap", "Deployment", "Ingress", "PersistentVolumeClaim", "Service"])
        self.assertNotIn(SECRET_VALUE, json.dumps(bodies[0]))

    def test_a_secret_is_sent_only_when_the_registry_names_it(self):
        ctx, before, bodies = self.run_client(("Deployment", "Secret"))
        self.assertEqual([i["manifest"]["kind"] for i in bodies[0]["irs"]], ["Deployment", "Secret"])
        self.assertIn(SECRET_VALUE, json.dumps(bodies[0]))

    def test_without_a_registry_a_server_cannot_ask_for_secrets_by_itself(self):
        ctx, before, bodies = self.run_client(("Deployment",), declared_kinds=("Deployment", "Secret"),
                                              pinned=False)
        self.assertNotIn("Secret", [i["manifest"]["kind"] for i in bodies[0]["irs"]])
        self.assertNotIn(SECRET_VALUE, json.dumps(bodies[0]))

    def test_held_documents_come_back_in_place_and_unchanged(self):
        ctx, before, bodies = self.run_client(("Deployment", "Service"))
        self.assertEqual([i.to_manifest() for i in ctx.irs], before)

    def test_a_mutating_engine_changes_its_documents_and_the_rest_stays_put(self):
        def edit(body):
            for item in body["irs"]:
                if item["manifest"]["kind"] == "Deployment":
                    item["manifest"]["spec"]["replicas"] = 99
            finding = {"engine": "remote", "level": "optimization", "rule": "r", "resource": "x",
                       "message": "replicas", "severity": "low", "category": "generic"}
            return 200, {"irs": body["irs"], "findings": [finding]}

        ctx, before, bodies = self.run_client(("Deployment",), mutates=True, responder=edit)
        after = [i.to_manifest() for i in ctx.irs]
        self.assertEqual(kinds_of(ctx.irs), [m["kind"] for m in before])     # same order
        for b, a in zip(before, after):
            if b["kind"] == "Deployment":
                self.assertEqual(a["spec"]["replicas"], 99)
            else:
                self.assertEqual(a, b)                                        # incl. the Secret


class BadRepliesAreRejectedTests(unittest.TestCase):
    def run_with(self, responder):
        server, url = _serve(responder, declared=descriptor(kinds=("Deployment", "Service")))
        self.addCleanup(server.shutdown)
        client = from_registry(pinned_entry(url, kinds=("Deployment", "Service")))
        ctx = make_ctx()
        before = [i.to_manifest() for i in ctx.irs]
        with self.assertRaises(RemoteEngineError):
            ServiceBus([], parallel_checks=[client], seq_after=[]).run(ctx)
        self.assertEqual([i.to_manifest() for i in ctx.irs], before)     # nothing was applied

    def test_fewer_documents_than_were_sent(self):
        self.run_with(lambda b: (200, {"irs": b["irs"][:1], "findings": []}))

    def test_an_extra_document_such_as_an_injected_secret(self):
        secret = {"kind": "SecretIR", "manifest": {"apiVersion": "v1", "kind": "Secret",
                                                   "metadata": {"name": "x"}, "data": {"k": "dg=="}}}
        self.run_with(lambda b: (200, {"irs": b["irs"] + [secret], "findings": []}))

    def test_documents_in_a_different_order(self):
        self.run_with(lambda b: (200, {"irs": list(reversed(b["irs"])), "findings": []}))

    def test_a_document_that_came_back_as_another_kind(self):
        def swap(body):
            items = [dict(i) for i in body["irs"]]
            items[0] = {"kind": "ServiceAccount", "manifest": {"kind": "ServiceAccount",
                        "apiVersion": "v1", "metadata": {"name": "x"}}}
            return 200, {"irs": items, "findings": []}
        self.run_with(swap)


class ServerRefusesUndeclaredKindsTests(unittest.TestCase):
    def serve(self, kinds):
        seen = []

        class Recorder(Module):
            name = "recorder"
            def process(self, ctx):
                seen.extend(kinds_of(ctx.irs))

        engine = Recorder()
        server = HTTPServer(("127.0.0.1", 0), _create_handler(engine, describe(engine, "1.0.0", kinds)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}", seen

    def test_a_real_server_only_ever_sees_its_declared_kinds(self):
        base, seen = self.serve(["Deployment", "Service"])
        client = HTTPModuleClient("recorder", f"{base}/process")
        ctx = make_ctx()
        ServiceBus([], parallel_checks=[client], seq_after=[]).run(ctx)
        self.assertEqual(seen, ["Deployment", "Service"])
        self.assertEqual(len(ctx.irs), 6)

    def test_the_server_answers_400_to_a_client_that_sends_more(self):
        import requests
        from kostral.adapters.remote.client import _serialize_irs
        base, seen = self.serve(["Deployment"])
        reply = requests.post(f"{base}/process", json={"irs": _serialize_irs(make_ctx().irs)}, timeout=5)
        self.assertEqual(reply.status_code, 400)
        self.assertIn("not accepted", reply.json()["error"])
        self.assertEqual(seen, [])                                     # the engine never ran


if __name__ == "__main__":
    unittest.main()
