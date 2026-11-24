
from kostral.core.contract import check_metadata, check_pins
from kostral.adapters.remote.auth import check_env_name, read_token
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
    
            
    entry["token_env"] names the environment variable that holds the shared
    token. The token itself never appears in the registry.

     
       """
    name = entry.get("name")
    who = f"registry entry '{name}'"

    unknown = set(entry) - {"name", "endpoint", "metadata", "descriptor", "token_env"}
    if unknown:
        raise ValueError(f"{who}: unknown keys {sorted(unknown)}")
    if "token_env" not in entry:
        raise ValueError(f"{who}: 'token_env' is required (the NAME of the environment variable holding the token)")


    pins = check_pins(entry.get("descriptor"), who)
    
    approved = check_metadata(
        entry.get("metadata", {}),who)

    requested = check_metadata(
        metadata or {},
        name
    )

    if (
        requested["mutates"]
        and not approved["mutates"]
    ):

        raise ValueError(
            f"remote engine '{name}': "
            f"mutates=True requested by the workflow "
            f"but not approved by the registry"
        )
    token = read_token(check_env_name(entry["token_env"], who), who)

    client = HTTPModuleClient(name, entry["endpoint"], timeout, token=token)
    client.pins = pins
    client.metadata = requested

    return client
