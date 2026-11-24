from copy import deepcopy
from typing import Any, Dict

from kostral.core.base import IR


class OpaqueIR(IR):
    """
    Holds a Kubernetes manifest whose kind has no dedicated IR.
    The document is preserved verbatim and never interpreted.

    INVARIANT: never define `resources`, `containers`, `image`, or
    kind == "ServiceIR". Built-in rules skip IRs via hasattr()/kind
    checks, and that is what keeps them away from opaque documents.
    """
    kind = "OpaqueIR"
    is_opaque = True

    def __init__(self, *, manifest: Dict[str, Any]):
        if not isinstance(manifest, dict):
            raise TypeError("OpaqueIR manifest must be a dictionary")
        self.manifest = deepcopy(manifest)
        self.original_kind = manifest.get("kind", "Unknown")
        metadata = manifest.get("metadata") or {}
        self.name = metadata.get("name") or "<unnamed>"

    def to_manifest(self) -> Dict[str, Any]:
        return deepcopy(self.manifest)

    def __repr__(self):
        return f"OpaqueIR(kind={self.original_kind}, name={self.name})"