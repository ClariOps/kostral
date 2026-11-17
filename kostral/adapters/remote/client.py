import requests

from kostral.core.base import RemoteModuleClient, Report
from kostral.core.context import RunContext
from kostral.core.ir import (
    DeploymentIR,
    ServiceIR,
    IngressIR,
    ConfigMapIR,
    SecretIR,
    PVCIR,
)
from kostral.core.contract import DEFAULT_METADATA

IR_MAPPING = {
    "DeploymentIR": DeploymentIR,
    "ServiceIR": ServiceIR,
    "IngressIR": IngressIR,
    "ConfigMapIR": ConfigMapIR,
    "SecretIR": SecretIR,
    "PVCIR": PVCIR,
}


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

    def __init__(
        self,
        name: str,
        endpoint: str,
        timeout: int = 30
    ):

        self.name = name
        self.endpoint = endpoint
        self.timeout = timeout

        # A plain remote engine is read-only.
        self.metadata = DEFAULT_METADATA

    def process(self, ctx: RunContext) -> None:

        # Do not send the existing report to the remote engine.
        payload = {
            "irs": _serialize_irs(ctx.irs),
            "opts": ctx.opts,
        }

        response = requests.post(
            self.endpoint,
            json=payload,
            timeout=self.timeout,
        )

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
        ctx.irs = new_irs
