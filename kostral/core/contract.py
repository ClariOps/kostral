
"""What an engine may do, and how the bus checks that it did only that."""

import json
from types import MappingProxyType

# The version of THIS contract. An engine must declare the same number.
CONTRACT_VERSION = 1

# What a remote engine publishes at /describe (see check_descriptor).
DESCRIPTOR_FIELDS = frozenset({"name", "version", "contract_version", "mutates", "input_kinds"})

# What a registry entry pins and the client verifies before sending anything.
PIN_FIELDS = frozenset({"version", "input_kinds"})


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
        "opaque_docs": json.dumps(
            [
                {"index": i, "manifest": ir.to_manifest()}
                for i, ir in enumerate(ctx.irs)
                if getattr(ir, "is_opaque", False)
            ],
            sort_keys=True, default=str
        ),
        "findings": [
            event.to_dict()
            for event in ctx.report.events
        ],
    }


def verify(engine_name, mutates, before, after):
    """Raise EngineContractViolation if the engine broke its contract."""
    
    if after["opaque_docs"] != before["opaque_docs"]:
        raise EngineContractViolation(
            f"engine '{engine_name}' modified, removed, or reordered "
            f"an opaque resource"
        )
    
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

# Descriptor (describe/) authentication contract check

def _check_kinds(kinds, who):
    if (not isinstance(kinds, list) or not kinds
            or not all(isinstance(k, str) and k for k in kinds)):
        raise ValueError(f"{who}: input_kinds must be a non-empty list of kind names")


def check_descriptor(declared, who="engine"):
    """Validate what an engine says about itself. input_kinds are Kubernetes
    manifest kinds ("Deployment", "Service", ...)."""
    if not isinstance(declared, dict):
        raise ValueError(f"{who}: descriptor must be an object")
    missing = DESCRIPTOR_FIELDS - set(declared)
    unknown = set(declared) - DESCRIPTOR_FIELDS
    if missing or unknown:
        raise ValueError(f"{who}: descriptor missing {sorted(missing)}, unknown {sorted(unknown)}")
    for field in ("name", "version"):
        if not isinstance(declared[field], str) or not declared[field]:
            raise ValueError(f"{who}: descriptor '{field}' must be a non-empty string")
    if type(declared["contract_version"]) is not int:
        raise ValueError(f"{who}: descriptor 'contract_version' must be an integer")
    if not isinstance(declared["mutates"], bool):
        raise ValueError(f"{who}: descriptor 'mutates' must be True or False")
    _check_kinds(declared["input_kinds"], who)
    return declared


def check_pins(pins, who="engine"):
    """Validate what a registry entry pins. Both fields are required: a pin that
    can be left out checks nothing."""
    if not isinstance(pins, dict):
        raise ValueError(f"{who}: registry entry needs a 'descriptor' with {sorted(PIN_FIELDS)}")
    missing = PIN_FIELDS - set(pins)
    unknown = set(pins) - PIN_FIELDS
    if missing or unknown:
        raise ValueError(f"{who}: registry descriptor missing {sorted(missing)}, unknown {sorted(unknown)}")
    if not isinstance(pins["version"], str) or not pins["version"]:
        raise ValueError(f"{who}: pinned 'version' must be a non-empty string")
    _check_kinds(pins["input_kinds"], who)
    return pins


def verify_descriptor(declared, *, name, pins, mutates):
    """The handshake rules. Raise EngineContractViolation unless the engine that
    answered is the one the workflow means: same name, same contract, the pinned
    version and kinds (when pinned), and the mutation permission the workflow
    granted. pins=None means "not pinned" (a client built without a registry):
    identity, contract and mutation are still verified."""
    declared = check_descriptor(declared, name)

    if declared["name"] != name:
        raise EngineContractViolation(
            f"engine '{name}': the server identifies itself as '{declared['name']}'")
    if declared["contract_version"] != CONTRACT_VERSION:
        raise EngineContractViolation(
            f"engine '{name}': speaks contract {declared['contract_version']}, "
            f"this KOSTRAL speaks {CONTRACT_VERSION}")
    if pins is not None:
        if declared["version"] != pins["version"]:
            raise EngineContractViolation(
                f"engine '{name}': version {declared['version']} does not match the pinned {pins['version']}")
        if sorted(set(declared["input_kinds"])) != sorted(set(pins["input_kinds"])):
            raise EngineContractViolation(
                f"engine '{name}': input_kinds {sorted(declared['input_kinds'])} "
                f"do not match the pinned {sorted(pins['input_kinds'])}")
    if declared["mutates"] != mutates:
        raise EngineContractViolation(
            f"engine '{name}': declares mutates={declared['mutates']} but the workflow "
            f"allows mutates={mutates}")
