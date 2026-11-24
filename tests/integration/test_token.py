"""Token authentication between the client and a remote engine server.

  * the token is a shared secret read from an environment variable; the registry
    holds only the variable's NAME
  * every request must carry it, including /describe and unknown paths
  * it is compared in constant time (hmac.compare_digest)
  * a missing or weak token is an error on both sides, never "no authentication"
  * it never travels over plain http beyond localhost, and never appears in an
    error message, a URL or a log line
"""
import logging
import os
import threading
import unittest
from http.server import HTTPServer
from unittest import mock

import requests

from kostral.adapters.remote import HTTPModuleClient
from kostral.adapters.remote.auth import (MIN_TOKEN_LENGTH, bearer, check_env_name,
                                          check_transport, is_authorized, read_token)
from kostral.adapters.remote.client import RemoteEngineError
from kostral.adapters.remote.registry import from_registry
from kostral.adapters.remote.server import _create_handler, describe, serve
from kostral.cli.helper import load_yaml_irs
from kostral.core.base import Module
from kostral.core.bus import ServiceBus
from kostral.core.context import RunContext
from kostral.modules.validator.engine import ValidatorEngine

from .fakes import TEST_TOKEN, TEST_TOKEN_ENV, _serve, descriptor, pinned_entry
from .helpers import ROOT

logging.disable(logging.CRITICAL)
GOOD = os.path.join(ROOT, "examples/demo/good.yaml")
BAD = os.path.join(ROOT, "examples/demo/bad.yaml")
RIGHT = "right-token-0123456789-abcdef"
WRONG = "wrong-token-0123456789-abcdef"


def ctx(path=GOOD):
    return RunContext(irs=load_yaml_irs(path, logging.getLogger()), opts={})


def echo(body):
    return 200, {"irs": body["irs"], "findings": []}


class ReadTokenTests(unittest.TestCase):
    def test_the_token_comes_from_the_environment(self):
        with mock.patch.dict(os.environ, {"KOSTRAL_X": RIGHT}):
            self.assertEqual(read_token("KOSTRAL_X", "w"), RIGHT)

    def test_a_missing_token_is_an_error_that_names_the_variable(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KOSTRAL_X", None)
            with self.assertRaisesRegex(ValueError, "KOSTRAL_X is not set"):
                read_token("KOSTRAL_X", "w")
        with mock.patch.dict(os.environ, {"KOSTRAL_X": ""}):
            with self.assertRaisesRegex(ValueError, "is not set"):
                read_token("KOSTRAL_X", "w")

    def test_a_weak_token_is_refused_without_repeating_it(self):
        weak = "x" * (MIN_TOKEN_LENGTH - 1)
        with mock.patch.dict(os.environ, {"KOSTRAL_X": weak}):
            with self.assertRaises(ValueError) as caught:
                read_token("KOSTRAL_X", "w")
        self.assertIn("shorter than", str(caught.exception))
        self.assertNotIn(weak, str(caught.exception))

    def test_token_env_must_be_a_variable_name_and_a_pasted_token_is_not_echoed(self):
        for ok in ("KOSTRAL_TOKEN_OPTIMIZER", "_X1"):
            self.assertEqual(check_env_name(ok, "w"), ok)
        for pasted in (RIGHT, "0123456789abcdef0123456789abcdef", "has space", "", None, 5):
            with self.subTest(pasted=pasted):
                with self.assertRaises(ValueError) as caught:
                    check_env_name(pasted, "w")
                if isinstance(pasted, str) and pasted:
                    self.assertNotIn(pasted, str(caught.exception))


class IsAuthorizedTests(unittest.TestCase):
    def test_only_the_exact_token_is_accepted(self):
        self.assertTrue(is_authorized(f"Bearer {RIGHT}", RIGHT))
        for header in (None, "", "Bearer ", f"Bearer {WRONG}", f"Bearer {RIGHT}x",
                       f"Bearer {RIGHT[:-1]}", f"bearer {RIGHT}", f"Basic {RIGHT}", RIGHT):
            with self.subTest(header=header):
                self.assertFalse(is_authorized(header, RIGHT))

    def test_the_comparison_is_constant_time(self):
        with mock.patch("kostral.adapters.remote.auth.hmac.compare_digest",
                        wraps=__import__("hmac").compare_digest) as spy:
            is_authorized(f"Bearer {WRONG}", RIGHT)
            is_authorized(None, RIGHT)
        self.assertEqual(spy.call_count, 2)        # even a missing header goes through it

    def test_the_header_the_client_builds_is_accepted(self):
        self.assertTrue(is_authorized(bearer(RIGHT)["Authorization"], RIGHT))


class TransportTests(unittest.TestCase):
    def test_a_token_may_go_over_https_or_to_this_machine(self):
        for url in ("https://engines.example.com/process", "http://127.0.0.1:9001/process",
                    "http://localhost:9001/process", "http://[::1]:9001/process"):
            with self.subTest(url=url):
                check_transport(url, "w")

    def test_a_token_is_never_sent_over_plain_http_beyond_localhost(self):
        for url in ("http://engines.example.com/process", "http://10.0.0.5:9001/process",
                    "http://127.0.0.1.evil.com/process", "http://localhost.evil.com/process",
                    "http://127.0.0.1@evil.com/process", "ftp://127.0.0.1/process"):
            with self.subTest(url=url):
                with self.assertRaisesRegex(ValueError, "plain http"):
                    check_transport(url, "w")

    def test_the_client_enforces_it_when_it_has_a_token(self):
        with self.assertRaisesRegex(ValueError, "plain http"):
            HTTPModuleClient("r", "http://engines.example.com/process", token=RIGHT)
        HTTPModuleClient("r", "http://engines.example.com/process")     # no token, nothing to leak

    def test_the_registry_path_enforces_it_too(self):
        with self.assertRaisesRegex(ValueError, "plain http"):
            from_registry(pinned_entry("http://engines.example.com/process"))


class RegistryTokenTests(unittest.TestCase):
    URL = "http://127.0.0.1:1/process"

    def test_an_entry_without_token_env_is_an_error(self):
        entry = pinned_entry(self.URL)
        del entry["token_env"]
        with self.assertRaisesRegex(ValueError, "token_env' is required"):
            from_registry(entry)

    def test_a_pasted_token_in_token_env_is_refused_and_not_repeated(self):
        with self.assertRaises(ValueError) as caught:
            from_registry(pinned_entry(self.URL, token_env=RIGHT))
        self.assertNotIn(RIGHT, str(caught.exception))

    def test_an_unset_variable_is_an_error_not_an_unauthenticated_client(self):
        os.environ.pop("KOSTRAL_NOT_SET", None)
        with self.assertRaisesRegex(ValueError, "KOSTRAL_NOT_SET is not set"):
            from_registry(pinned_entry(self.URL, token_env="KOSTRAL_NOT_SET"))


class ServerAuthTests(unittest.TestCase):
    def start(self):
        seen = []

        class Recorder(Module):
            name = "recorder"

            def process(self, ctx):
                seen.append("ran")

        engine = Recorder()
        server = HTTPServer(("127.0.0.1", 0),
                            _create_handler(engine, describe(engine, "1.0.0", ["Deployment"]), RIGHT))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}", seen

    def test_no_token_and_a_wrong_token_are_both_401_on_every_endpoint(self):
        base, seen = self.start()
        for headers in ({}, {"Authorization": f"Bearer {WRONG}"}, {"Authorization": "Basic abc"}):
            for method, path in (("GET", "/describe"), ("POST", "/process"), ("GET", "/other")):
                with self.subTest(headers=headers, path=path):
                    reply = requests.request(method, base + path, headers=headers, json={"irs": []}, timeout=5)
                    self.assertEqual(reply.status_code, 401)
                    self.assertEqual(reply.headers.get("WWW-Authenticate"), "Bearer")
                    self.assertNotIn("version", reply.text)            # no descriptor leaked
        self.assertEqual(seen, [])                                       # the engine never ran

    def test_unknown_paths_do_not_reveal_anything_without_a_token(self):
        base, _ = self.start()
        auth = {"Authorization": f"Bearer {RIGHT}"}
        self.assertEqual(requests.get(base + "/other", timeout=5).status_code, 401)
        self.assertEqual(requests.get(base + "/other", headers=auth, timeout=5).status_code, 404)

    def test_the_right_token_is_served(self):
        base, seen = self.start()
        auth = {"Authorization": f"Bearer {RIGHT}"}
        self.assertEqual(requests.get(base + "/describe", headers=auth, timeout=5).status_code, 200)
        self.assertEqual(requests.post(base + "/process", headers=auth, json={"irs": []}, timeout=5).status_code, 200)
        self.assertEqual(seen, ["ran"])

    def test_serve_requires_a_token_variable_and_refuses_to_run_open(self):
        # If serve() ever got as far as serving, fail at once instead of blocking forever.
        never = mock.patch("kostral.adapters.remote.server.HTTPServer.serve_forever",
                           side_effect=AssertionError("the server started without a usable token"))
        kwargs = dict(version="1", input_kinds=["Deployment"])
        with never:
            with self.assertRaises(TypeError):
                serve(ValidatorEngine(), **kwargs)
            os.environ.pop("KOSTRAL_NOT_SET", None)
            with self.assertRaisesRegex(ValueError, "KOSTRAL_NOT_SET is not set"):
                serve(ValidatorEngine(), token_env="KOSTRAL_NOT_SET", **kwargs)
            with mock.patch.dict(os.environ, {"KOSTRAL_WEAK": "short"}):
                with self.assertRaisesRegex(ValueError, "shorter than"):
                    serve(ValidatorEngine(), token_env="KOSTRAL_WEAK", **kwargs)


class ClientTokenTests(unittest.TestCase):
    def run_client(self, *, server_token, client_env_value):
        log, headers = [], []
        server, url = _serve(echo, declared=descriptor(), log=log, token=server_token, headers=headers)
        self.addCleanup(server.shutdown)
        with mock.patch.dict(os.environ, {TEST_TOKEN_ENV: client_env_value}):
            client = from_registry(pinned_entry(url))
        ServiceBus([], parallel_checks=[client], seq_after=[]).run(ctx())
        return log, headers, url

    def test_the_token_is_sent_on_the_handshake_and_on_the_document_request(self):
        log, headers, url = self.run_client(server_token=RIGHT, client_env_value=RIGHT)
        self.assertEqual(log, ["GET /describe", "POST /process"])
        self.assertEqual(headers, [f"Bearer {RIGHT}"] * 2)
        self.assertNotIn(RIGHT, url)                                    # never in the URL

    def test_a_wrong_token_is_an_authentication_error_and_no_document_is_sent(self):
        log = []
        server, url = _serve(echo, declared=descriptor(), log=log, token=RIGHT)
        self.addCleanup(server.shutdown)
        with mock.patch.dict(os.environ, {TEST_TOKEN_ENV: WRONG}):
            client = from_registry(pinned_entry(url))
        with self.assertRaises(RemoteEngineError) as caught:
            ServiceBus([], parallel_checks=[client], seq_after=[]).run(ctx())
        self.assertIn("authentication failed", str(caught.exception))
        self.assertNotIn(WRONG, str(caught.exception))
        self.assertNotIn(RIGHT, str(caught.exception))
        self.assertEqual(log, ["GET /describe 401"])                   # stopped at the handshake

    def test_a_client_with_no_token_against_a_protected_server_fails_clearly(self):
        server, url = _serve(echo, declared=descriptor(), token=RIGHT)
        self.addCleanup(server.shutdown)
        with self.assertRaisesRegex(RemoteEngineError, "no token configured"):
            ServiceBus([], parallel_checks=[HTTPModuleClient("r", url)], seq_after=[]).run(ctx())

    def test_the_whole_path_works_against_the_real_handler(self):
        engine = ValidatorEngine()
        server = HTTPServer(("127.0.0.1", 0),
                            _create_handler(engine, describe(engine, "1.0.0", ["Deployment", "Service"]), RIGHT))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}/process"
        with mock.patch.dict(os.environ, {TEST_TOKEN_ENV: RIGHT}):
            client = from_registry(pinned_entry(url, name=engine.name, kinds=("Deployment", "Service")))
        run = ctx(BAD)
        ServiceBus([], parallel_checks=[client], seq_after=[]).run(run)
        self.assertGreater(len(run.report.events), 0)       # the validator really ran, remotely


if __name__ == "__main__":
    unittest.main()
