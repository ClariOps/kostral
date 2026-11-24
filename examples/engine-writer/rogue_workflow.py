"""An engine that breaks the contract: it declares nothing (so it is read-only)
but edits a manifest. The bus rejects it.

    koss remote ./examples/demo/bad.yaml --exec ./examples/engine-writer/rogue_workflow.py

Expected: "koss: engine contract violation: engine 'rogue-engine' changed the
manifests but its metadata says mutates=False", exit code 3.
See docs/engine-contract.md.
"""
from kostral.core.base import Module
from kostral.modules.renderer.engine import RendererEngine


class Rogue(Module):
    """Claims to be read-only but edits a manifest."""
    name = "rogue-engine"

    def process(self, ctx):
        ctx.irs[0].manifest["metadata"]["name"] = "renamed-by-rogue"


workflow = {"seq_before": [], "parallel_checks": [], "seq_after": [Rogue(), RendererEngine()]}
