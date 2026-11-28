"""Client for a remote external scanner (the `external` profile).

It reuses everything the native client already proves (token, descriptor handshake,
pins, Secret hold-back) and differs in exactly two ways: what it sends (documents
only: no IR class names, no opts) and what it accepts back (a SARIF log and nothing
else). A reply therefore cannot carry a report or documents, so it cannot erase a
finding or change a manifest.
"""
import json

import requests

from kostral.adapters.remote.client import HTTPModuleClient, RemoteEngineError

from .apply import apply_scan, claim_artifact, documents_for, skip
from .sarif import DEFAULT_PROFILE, SarifMappingError

MAX_RESPONSE_BYTES = 10 * 1024 * 1024
_ERROR_TEXT = 300


class RemoteExternalClient(HTTPModuleClient):
    PROFILE = "external"

    def __init__(self, name, endpoint, *, timeout=30, token=None, mapping=DEFAULT_PROFILE,
                 max_response_bytes=MAX_RESPONSE_BYTES, keep_raw=False):
        super().__init__(name, endpoint, timeout, token)
        self.mapping = mapping
        self.max_response_bytes = max_response_bytes
        self.keep_raw = keep_raw

    def _read_capped(self, response):
        declared = response.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > self.max_response_bytes:
            response.close()
            raise RemoteEngineError(f"{self.name}: reply is larger than {self.max_response_bytes} bytes")
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size = len(chunk)
            if size > self.max_response_bytes:
                response.close()
                raise RemoteEngineError(f"{self.name}: reply is larger than {self.max_response_bytes} bytes")
            chunks.append(chunk)
        return b"".join(chunks)

    def process(self, ctx):
        if not self._verified:
            self._handshake()
        claim_artifact(ctx, self.name)

        manifests = documents_for(ctx, self._input_kinds)
        if not manifests:
            return skip(ctx, self.name)

        try:
            response = self._request("POST", self.endpoint, json={"documents": manifests}, stream=True)
            body = self._read_capped(response)
        except requests.RequestException as exc:
            raise RemoteEngineError(f"{self.name}: request failed: {exc}") from exc

        if response.status_code >= 400:
            raise RemoteEngineError(f"{self.name}: server answered {response.status_code}: {self._error_text(body)}")

        try:
            data = json.loads(body)
        except ValueError as exc:
            raise RemoteEngineError(f"{self.name}: reply is not JSON") from exc
        if not isinstance(data, dict) or set(data) != {"sarif"} or not isinstance(data["sarif"], dict):
            raise RemoteEngineError(f"{self.name}: an external reply must be exactly {{\"sarif\": <log>}}")

        try:
            apply_scan(ctx, self.name, data["sarif"], self.mapping, manifests, keep_raw=self.keep_raw)
        except SarifMappingError as exc:
            raise RemoteEngineError(f"{self.name}: malformed SARIF: {exc}") from exc

    @staticmethod
    def _error_text(body):
        try:
            message = json.loads(body).get("error", "")
        except (ValueError, AttributeError):
            message = ""
        return str(message)[:_ERROR_TEXT] or "(no detail)"
