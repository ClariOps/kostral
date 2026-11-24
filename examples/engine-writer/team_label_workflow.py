"""A minimal read-only engine, and the workflow that runs it.

    koss remote ./examples/demo/bad.yaml --exec ./examples/engine-writer/team_label_workflow.py

Expected: one warning, `missing-team-label`, exit code 0.
See docs/engine-contract.md.
"""
from kostral.core.base import Module
from kostral.modules.renderer.engine import RendererEngine


class TeamLabelEngine(Module):
    """Read-only engine: warns about Deployments that have no `team` label."""
    name = "team-label-engine"

    def process(self, ctx):
        for ir in ctx.irs:
            manifest = ir.to_manifest()
            if manifest.get("kind") != "Deployment":
                continue
            labels = manifest.get("metadata", {}).get("labels", {})
            if "team" not in labels:
                ctx.report.warning(
                    rule="missing-team-label",
                    engine=self.name,
                    resource=manifest["metadata"]["name"],
                    issue="Deployment has no 'team' label",
                    fix="add metadata.labels.team",
                )


workflow = {
    "seq_before": [],
    "parallel_checks": [],
    "seq_after": [TeamLabelEngine(), RendererEngine()],
}
