import logging

from kostral.core.base import Module
from kostral.core.context import RunContext

logger = logging.getLogger(__name__)


class CoverageEngine(Module):
    """Reports resources that were preserved but not analyzed. Read-only."""
    name = "coverage-engine"
    # metadata defaults to mutates=False; do not grant mutation.

    def process(self, ctx: RunContext) -> None:
        for ir in ctx.irs:
            if not getattr(ir, "is_opaque", False):
                continue
            ctx.report.warning(
                rule="unanalyzed-resource-kind",
                engine=self.name,
                resource=f"{ir.original_kind}/{ir.name}",
                category="coverage",
                severity="low",
                issue=f"Kind '{ir.original_kind}' is not analyzed by KOSTRAL.",
                impact="Preserved in the output, but its configuration is not checked.",
                fix="Review independently or add a dedicated IR implementation.",
            )