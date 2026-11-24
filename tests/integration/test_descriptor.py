"""The engine descriptor and the /describe handshake.

A remote engine publishes who it is (name, version, contract_version, mutates,
input_kinds). Before the FIRST document is sent, the client reads that and
checks it against what the workflow and the registry expect. No match, no data.
"""
import json
import logging
import os
import threading
import unittest
from http.server import HTTPServer
from unittest import mock

import requests

from kostral.adapters.remote import HTTPModuleClient
from kostral.adapters.remote.client import RemoteEngineError
from kostral.adapters.remote.registry import from_registry
from kostral.adapters.remote.server import _create_handler, describe, serve
from kostral.cli.helper import load_yaml_irs
from kostral.core.bus import EngineContractViolation, ServiceBus
from kostral.core.context import RunContext
from kostral.core.contract import (CONTRACT_VERSION, check_descriptor, check_pins,
                                   verify_descriptor)
from kostral.modules.optimizer.engine import OptimizerEngine
from kostral.modules.validator.engine import ValidatorEngine

from .fakes import TEST_TOKEN, _serve, descriptor, pinned_entry
from .helpers import ROOT

logging.disable(logging.CRITICAL)
GOOD = os.path.join(ROOT, "examples/demo/good.yaml")
PINS = {"version": "1.0.0", "input_kinds": ["Deployment"]}


def ctx():
    return RunContext(irs=load_yaml_irs(GOOD, logging.getLogger()), opts={})


def echo(body):
    return 200, {"irs": body["irs"], "findings": []}


class DescriptorShapeTests(unittest.TestCase):
    def test_a_valid_descriptor_is_accepted(self):
        self.assertEqual(check_descriptor(descriptor()), descriptor())

    def test_missing_and_unknown_fields_are_errors(self):
        for broken in ({k: v for k, v in descriptor().items() if k != "version"},
                       {**descriptor(), "mutate": True},          # typo, not silently ignored
                       "not an object", None):
            with self.subTest(broken=broken):
                with self.assertRaises(ValueError):
                    check_descriptor(broken)

    def test_wrong_types_are_errors(self):
        for field, bad in (("name", ""), ("version", 1), ("contract_version", "1"),
                           ("contract_version", True), ("mutates", "yes"),
                           ("input_kinds", []), ("input_kinds", "Deployment"),
                           ("input_kinds", ["Deployment", ""])):
            with self.subTest(field=field, bad=bad):
                with self.assertRaises(ValueError):
                    check_descriptor({**descriptor(), field: bad})

    def test_registry_pins_need_both_fields_and_nothing_else(self):
        self.assertEqual(check_pins(PINS), PINS)
        for broken in (None, {}, {"version": "1.0.0"}, {"input_kinds": ["Deployment"]},
                       {**PINS, "vesion": "x"}, {"version": "", "input_kinds": ["Deployment"]}):
            with self.subTest(broken=broken):
                with self.assertRaises(ValueError):
                    check_pins(broken)


class VerifyDescriptorTests(unittest.TestCase):
    def verify(self, declared=None, pins=PINS, mutates=False, name="r"):
        return verify_descriptor(declared or descriptor(), name=name, pins=pins, mutates=mutates)

    def test_a_matching_engine_passes(self):
        self.verify()

    def test_each_mismatch_is_refused_with_its_own_reason(self):
        cases = [
            ("identifies itself", {"name": "other"}, {}),
            ("contract", {"contract_version": CONTRACT_VERSION + 1}, {}),
            ("pinned 1.0.0", {"version": "1.0.1"}, {}),
            ("input_kinds", {"input_kinds": ["Deployment", "Secret"]}, {}),
            ("declares mutates=True", {"mutates": True}, {"mutates": False}),
            ("declares mutates=False", {"mutates": False}, {"mutates": True}),
        ]
        for reason, change, kw in cases:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(EngineContractViolation, reason):
                    self.verify(declared={**descriptor(), **change}, **kw)

    def test_the_order_of_input_kinds_does_not_matter(self):
        self.verify(declared=descriptor(kinds=("Service", "Deployment")),
                    pins={"version": "1.0.0", "input_kinds": ["Deployment", "Service"]})

    def test_without_pins_identity_contract_and_mutation_are_still_verified(self):
        self.verify(declared=descriptor(version="anything", kinds=("Service",)), pins=None)
        with self.assertRaises(EngineContractViolation):
            self.verify(declared={**descriptor(), "contract_version": 99}, pins=None)


class ServerDescribeTests(unittest.TestCase):
    def test_the_descriptor_is_built_from_the_engine_and_the_operators_declaration(self):
        d = describe(ValidatorEngine(), "2.1.0", ["Deployment", "Service"])
        self.assertEqual(d, {"name": ValidatorEngine.name, "version": "2.1.0",
                             "contract_version": CONTRACT_VERSION, "mutates": False,
                             "input_kinds": ["Deployment", "Service"]})
        self.assertTrue(describe(OptimizerEngine(), "1.0.0", ["Deployment"])["mutates"])

    def test_a_server_with_a_bad_declaration_refuses_to_start(self):
        with self.assertRaises(ValueError):
            describe(ValidatorEngine(), "1.0.0", [])

    def test_there_are_no_defaults_for_version_and_kinds(self):
        with self.assertRaises(TypeError):
            serve(ValidatorEngine(), token_env="KOSTRAL_TEST_TOKEN")

    def test_describe_is_served_over_http_and_process_still_works(self):
        engine = ValidatorEngine()
        server = HTTPServer(("127.0.0.1", 0), _create_handler(engine, describe(engine, "1.0.0", ["Deployment"]), TEST_TOKEN))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        auth = {"Authorization": f"Bearer {TEST_TOKEN}"}
        
        got = requests.get(f"{base}/describe", headers=auth, timeout=5)
        self.assertEqual(got.json(), describe(engine, "1.0.0", ["Deployment"]))
        self.assertEqual(requests.get(f"{base}/other", headers=auth, timeout=5).status_code, 404)

        client = HTTPModuleClient(engine.name, f"{base}/process", token=TEST_TOKEN)
        ServiceBus([], parallel_checks=[client], seq_after=[]).run(ctx())


class HandshakeTests(unittest.TestCase):
    def client(self, declared=None, log=None, mutates=None, responder=echo, pins=PINS):
        server, url = _serve(responder, declared=declared, log=log)
        self.addCleanup(server.shutdown)
        entry = pinned_entry(url, mutates=mutates, version=pins["version"], kinds=pins["input_kinds"])
        return from_registry(entry, metadata={"mutates": mutates} if mutates is not None else None)

    def run_client(self, client):
        ServiceBus([client] if client.metadata["mutates"] else [],
                   parallel_checks=[] if client.metadata["mutates"] else [client],
                   seq_after=[]).run(ctx())

    def test_the_descriptor_is_read_before_any_document_and_only_once(self):
        log = []
        client = self.client(log=log)
        self.run_client(client)
        self.run_client(client)
        self.assertEqual(log, ["GET /describe", "POST /process", "POST /process"])

    def test_a_mismatch_means_no_document_is_ever_sent(self):
        drifted = {
            "version drifted": descriptor(version="1.1.0"),
            "kinds widened": descriptor(kinds=("Deployment", "Secret")),
            "contract changed": {**descriptor(), "contract_version": 2},
            "other engine": descriptor(name="impostor"),
            "claims it mutates": descriptor(mutates=True),
        }
        for label, declared in drifted.items():
            with self.subTest(label):
                log = []
                with self.assertRaises(EngineContractViolation):
                    self.run_client(self.client(declared=declared, log=log))
                self.assertEqual(log, ["GET /describe"])         # nothing was POSTed

    def test_workflow_allowing_mutation_must_match_what_the_engine_declares(self):
        with self.assertRaisesRegex(EngineContractViolation, "declares mutates=False"):
            self.run_client(self.client(declared=descriptor(mutates=False), mutates=True))
        self.run_client(self.client(declared=descriptor(mutates=True), mutates=True))

    def test_an_unreachable_descriptor_is_an_error_not_an_empty_result(self):
        client = from_registry(pinned_entry("http://127.0.0.1:1/process"))
        with self.assertRaisesRegex(RemoteEngineError, "cannot read the descriptor"):
            self.run_client(client)

    def test_a_malformed_descriptor_is_a_remote_engine_error(self):
        for bad in ({"name": "r"}, {**descriptor(), "extra": 1}):
            with self.subTest(bad=bad):
                with self.assertRaises(RemoteEngineError):
                    self.run_client(self.client(declared=bad))


class RegistryEntryTests(unittest.TestCase):
    URL = "http://127.0.0.1:1/process"

    def test_an_entry_must_pin_the_version_and_kinds(self):
        for entry in ({"name": "r", "endpoint": self.URL},
                      {"name": "r", "endpoint": self.URL, "descriptor": {"version": "1.0.0"}}):
            with self.subTest(entry=entry):
                with self.assertRaises(ValueError):
                    from_registry(entry)

    def test_a_typo_in_an_entry_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "unknown keys"):
            from_registry({**pinned_entry(self.URL), "descriptr": {}})
        with self.assertRaises(ValueError):
            from_registry({**pinned_entry(self.URL), "descriptor": {**PINS, "vesion": "1"}})

    def test_the_pins_are_kept_on_the_client(self):
        self.assertEqual(from_registry(pinned_entry(self.URL)).pins, PINS)

    def test_every_entry_in_the_shipped_example_registry_loads(self):
        with open(os.path.join(ROOT, "examples/remote/registry.json")) as f:
            registry = json.load(f)
        tokens = {entry["token_env"]: "x" * 32 for entry in registry.values()}
        with mock.patch.dict(os.environ, tokens):
            for key, entry in registry.items():
                with self.subTest(key):
                    asked = {"mutates": entry.get("metadata", {}).get("mutates", False)}
                    self.assertEqual(from_registry(entry, metadata=asked).name, entry["name"])
 

if __name__ == "__main__":
    unittest.main()
