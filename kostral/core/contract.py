
"""What an engine may do, and how the bus checks that it did only that."""

import json
from types import MappingProxyType


ALLOWED_METADATA = frozenset({"mutates"})

# Shared immutable default.
DEFAULT_METADATA = MappingProxyType({
    "mutates": False
})


class EngineContractViolation(Exception):
    """An engine did something its metadata does not allow."""


def check_metadata(meta, who="engine"):
    """Validate engine metadata and return it as a read-only mapping."""

    unknown = set(meta) - ALLOWED_METADATA

    if unknown:
        raise ValueError(
            f"{who}: unknown metadata {sorted(unknown)}; "
            f"allowed: {sorted(ALLOWED_METADATA)}"
        )

    merged = {
        **DEFAULT_METADATA,
        **meta
    }

    if not isinstance(merged["mutates"], bool):
        raise ValueError(
            f"{who}: metadata 'mutates' must be True or False"
        )

    return MappingProxyType(merged)


def snapshot(ctx):
    """Capture the observable state that the contract protects."""

    return {
        "docs": json.dumps(
            [ir.to_manifest() for ir in ctx.irs],
            sort_keys=True,
            default=str
        ),
        "findings": [
            event.to_dict()
            for event in ctx.report.events
        ],
    }


def verify(engine_name, mutates, before, after):
    """Raise EngineContractViolation if the engine broke its contract."""

    previous_count = len(before["findings"])

    # Existing findings must remain unchanged.
    if after["findings"][:previous_count] != before["findings"]:
        raise EngineContractViolation(
            f"engine '{engine_name}' removed or modified "
            f"findings reported earlier"
        )

    # Detect manifest changes.
    if after["docs"] != before["docs"]:

        # Read-only engines cannot modify manifests.
        if not mutates:
            raise EngineContractViolation(
                f"engine '{engine_name}' changed the manifests "
                f"but its metadata says mutates=False"
            )

        # Mutations must be accompanied by an optimization finding.
        new_findings = after["findings"][previous_count:]

        if not any(
            event["level"] == "optimization"
            for event in new_findings
        ):
            raise EngineContractViolation(
                f"engine '{engine_name}' changed the manifests "
                f"without reporting the change"
            )
