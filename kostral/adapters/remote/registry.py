
from kostral.core.contract import check_metadata, check_pins

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
    
    """
    entry["descriptor"] pins the engine's version and input kinds. The client checks them against /describe before it sends anything.
     """
    
    unknown = set(entry) - {"name", "endpoint", "metadata", "descriptor"}
    if unknown:
        raise ValueError(f"registry entry '{entry.get('name')}': unknown keys {sorted(unknown)}")

    client = HTTPModuleClient(
        entry["name"],
        entry["endpoint"],
        timeout
    )

    client.pins = check_pins(entry.get("descriptor"), f"registry entry '{client.name}'")
    
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
