import json
from pathlib import Path
from kostral.adapters.remote.registry import from_registry
from kostral.modules.renderer.engine import RendererEngine

try:
    WORKFLOW_DIR = Path(__file__).resolve().parent
except NameError:
    # Fallback if kostral executes the file via exec() without setting __file__
    # We resolve it relative to the script path argument itself
    import sys
    WORKFLOW_DIR = Path(sys.argv[0]).resolve().parent

REGISTRY_PATH = WORKFLOW_DIR / "registry.json"

with open(REGISTRY_PATH) as f:
    registry = json.load(f)


optimizer = registry["X092@jjj"]
validator = registry["Y481@abc"]
security = registry["Z481@abc"]

workflow = {
    "seq_before": [
        from_registry(optimizer, metadata={"mutates": True}),
    ],

    "parallel_checks": [
     #  readonly
     #   from_registry(optimizer, metadata={"mutates": True}),
    ],

    "seq_after": [
        
        from_registry(validator),
        from_registry(security),
        RendererEngine()
        
    ],
}