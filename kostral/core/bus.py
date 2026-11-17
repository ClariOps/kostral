
import logging

from typing import List, Optional

from .base import Module
from .context import RunContext

from .contract import (
    EngineContractViolation,
    check_metadata,
    snapshot,
    verify,
)


logger = logging.getLogger(__name__)


def _name(m):
    return getattr(
        m,
        "name",
        type(m).__name__
    )


class ServiceBus:
    """
    Runs engines in three explicit phases.

    seq_before:
        Engines that may mutate.

    parallel_checks:
        Read-only engines.

    seq_after:
        Subsequent engines.
    """

    def __init__(
        self,
        seq_before: List[Module],
        parallel_checks: Optional[List[Module]] = None,
        seq_after: Optional[List[Module]] = None,
    ):

        self.seq_before = seq_before

        self.parallel_checks = (
            parallel_checks or []
        )

        self.seq_after = (
            seq_after or []
        )

        # Freeze engine permissions when the bus is built.
        self._meta = {
            id(m): check_metadata(
                getattr(m, "metadata", {}),
                _name(m)
            )
            for m in [
                *self.seq_before,
                *self.parallel_checks,
                *self.seq_after
            ]
        }

        # Read-only checks cannot have mutation permission.
        for m in self.parallel_checks:

            if self._meta[id(m)]["mutates"]:

                raise ValueError(
                    f"engine '{_name(m)}' has mutates=True "
                    f"but is in the read-only "
                    f"'parallel_checks' phase; "
                    f"put it in seq_before or seq_after"
                )

    def run(self, ctx: RunContext) -> RunContext:

        engines = [
            *self.seq_before,
            *self.parallel_checks,
            *self.seq_after
        ]

        for m in engines:

            # Capture state before execution.
            before = snapshot(ctx)

            # Execute engine.
            m.process(ctx)

            # Validate its behavior.
            verify(
                _name(m),
                self._meta[id(m)]["mutates"],
                before,
                snapshot(ctx)
            )

        return ctx
