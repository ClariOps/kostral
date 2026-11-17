
from kostral.core.contract import check_metadata

from .client import HTTPModuleClient


def from_registry(
    entry: dict,
    metadata: dict = None,
    timeout: int = 30
) -> HTTPModuleClient:
    """
    Build a remote engine client from a registry entry.

    Registry metadata:
        Permissions approved for the engine.

    Workflow metadata:
        Permissions requested by the workflow.

    Both must agree.
    """

    client = HTTPModuleClient(
        entry["name"],
        entry["endpoint"],
        timeout
    )

    approved = check_metadata(
        entry.get("metadata", {}),
        f"registry entry '{client.name}'"
    )

    requested = check_metadata(
        metadata or {},
        client.name
    )

    if (
        requested["mutates"]
        and not approved["mutates"]
    ):

        raise ValueError(
            f"remote engine '{client.name}': "
            f"mutates=True requested by the workflow "
            f"but not approved by the registry"
        )

    client.metadata = requested

    return client
