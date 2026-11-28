from urllib.parse import urljoin
import requests
from kostral.adapters.remote.auth import bearer, check_transport
from kostral.core.base import RemoteModuleClient, Report
from kostral.core.context import RunContext
from kostral.core.ir import (
    DeploymentIR,
    ServiceIR,
    IngressIR,
    ConfigMapIR,
    SecretIR,
    PVCIR,
    OpaqueIR
)
from kostral.core.contract import DEFAULT_METADATA, check_descriptor, verify_descriptor, SECRET_KIND, kind_accepted

IR_MAPPING = {
    "DeploymentIR": DeploymentIR,
    "ServiceIR": ServiceIR,
    "IngressIR": IngressIR,
    "ConfigMapIR": ConfigMapIR,
    "SecretIR": SecretIR,
    "PVCIR": PVCIR,
    "OpaqueIR": OpaqueIR
}


def _manifest_kind(ir):
    return ir.to_manifest().get("kind")


def split_for_engine(irs, input_kinds):
    """Client side only. Returns (to_send, held): `held` maps each document's
    original position to a document that stays in this process and is never
    serialized (a Secret, or any kind the engine did not declare)."""
    to_send, held = [], {}
    for position, ir in enumerate(irs):
        if kind_accepted(input_kinds, _manifest_kind(ir)):
            to_send.append(ir)
        else:
            held[position] = ir
    return to_send, held


def merge_back(returned, held, total):
    """Put the returned documents into the free positions and the held ones back
    where they were, so the list has the original order."""
    returned = iter(returned)
    return [held[i] if i in held else next(returned) for i in range(total)]



class RemoteEngineError(Exception):
    """The remote engine failed or answered with something malformed."""


def _serialize_irs(irs):
    return [
        {
            "kind": ir.kind,
            "manifest": ir.to_manifest(),
        }
        for ir in irs
    ]


def _deserialize_irs(items):
    irs = []

    for item in items:
        kind = item["kind"]
        manifest = item["manifest"]

        ir_class = IR_MAPPING.get(kind)

        if ir_class is None:
            raise ValueError(
                f"Unsupported remote IR type: {kind}"
            )

        irs.append(
            ir_class(manifest=manifest)
        )

    return irs



class HTTPModuleClient(RemoteModuleClient):
    # Which profile the server must declare at /describe (see core/contract.py).
    PROFILE = "native"
    def __init__(
        self,
        name: str,
        endpoint: str,
        timeout: int = 30,
        token: str = None
    ):

        self.name = name
        self.endpoint = endpoint
        self.timeout = timeout
        self._token = token                     # never logged, never in an error message
        if token:
            check_transport(endpoint, name)    
        # A plain remote engine is read-only.
    
        self.metadata = DEFAULT_METADATA
        self.pins = None
        self._verified = False
        self._input_kinds = [] 

    def _request(self, method, url, **kwargs):
        """Every request carries the token. A 401 is an authentication error."""
        headers = bearer(self._token) if self._token else {}
        response = requests.request(method, url, headers=headers, timeout=self.timeout, **kwargs)
        if response.status_code == 401:
            raise RemoteEngineError(
                f"{self.name}: authentication failed, the server rejected "
                f"{'the token' if self._token else 'the request (no token configured)'}")
        return response

    def _handshake(self):
        """Ask the engine who it is BEFORE any document is sent."""
        url = urljoin(self.endpoint, "describe")
        try:
            response = self._request("GET", url)
            response.raise_for_status()
            declared = check_descriptor(response.json(), self.name)
        except (requests.RequestException, ValueError) as exc:
            raise RemoteEngineError(f"{self.name}: cannot read the descriptor at {url}: {exc}") from exc

        verify_descriptor(declared, name=self.name, pins=self.pins,
                          mutates=self.metadata["mutates"], profile=self.PROFILE)
 
        # What may be sent is what the REGISTRY pinned (the handshake proved the
        # engine declares the same). Without a registry the engine's own claim is
        # all there is, and a server must not be able to ask for Secrets by itself.
        if self.pins is not None:
            self._input_kinds = list(self.pins["input_kinds"])
        else:
            self._input_kinds = [k for k in declared["input_kinds"] if k != SECRET_KIND]

        self._verified = True
 

    def process(self, ctx: RunContext) -> None:
        if not self._verified:
            self._handshake()

        # Only what the engine declared leaves this process; the rest is held back.
        to_send, held = split_for_engine(ctx.irs, self._input_kinds)            
        # Do not send the existing report to the remote engine.

        payload = {
            "irs": _serialize_irs(to_send),
            "opts": ctx.opts,
        }

        response = self._request("POST", self.endpoint, json=payload)
        

        response.raise_for_status()

        try:
            data = response.json()

        except ValueError as exc:

            raise RemoteEngineError(
                f"{self.name}: response is not JSON"
            ) from exc

        # Response must have the expected structure.
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("irs"), list)
            or not isinstance(data.get("findings"), list)
        ):

            raise RemoteEngineError(
                f"{self.name}: response must contain "
                f"'irs' and 'findings' lists"
            )

        try:

            new_irs = _deserialize_irs(
                data["irs"]
            )
            self._check_same_documents(to_send, new_irs)

            # Append findings; never replace the report.
            ctx.report.extend(
                data["findings"]
            )

        except (
            KeyError,
            ValueError,
            TypeError
        ) as exc:

            raise RemoteEngineError(
                f"{self.name}: malformed response: {exc}"
            ) from exc

        # Update IR only after deserialization and finding validation.
        ctx.irs = merge_back(new_irs, held, len(ctx.irs))


    @staticmethod
    def _check_same_documents(sent, returned):
        """An engine may change what it was given, not which documents exist:
        same count, and the same kind in every position."""
        if len(returned) != len(sent):
            raise ValueError(f"{len(returned)} documents returned for {len(sent)} sent")
        for position, (before, after) in enumerate(zip(sent, returned)):
            if _manifest_kind(before) != _manifest_kind(after):
                raise ValueError(
                    f"document {position} came back as {_manifest_kind(after)}, "
                    f"was {_manifest_kind(before)}")