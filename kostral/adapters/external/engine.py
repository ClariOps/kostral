"""A scanner run in this process (a subprocess), mapped the same way a remote one is."""
from kostral.core.base import Module
from kostral.core.contract import DEFAULT_METADATA, check_kinds

from .apply import apply_scan, claim_artifact, documents_for, skip
from .runner import DEFAULT_TIMEOUT, MAX_OUTPUT_BYTES, check_command, run_tool
from .sarif import DEFAULT_PROFILE


class ExternalToolEngine(Module):
    """Read-only by construction: it appends findings and never touches a document."""

    metadata = DEFAULT_METADATA

    def __init__(self, name, command, *, input_kinds=("*",), mapping=DEFAULT_PROFILE,
                 timeout=DEFAULT_TIMEOUT, max_output_bytes=MAX_OUTPUT_BYTES, keep_raw=False):
        if not isinstance(name, str) or not name:
            raise ValueError("external engine: name must be a non-empty string")
        self.name = name
        self.command = check_command(command, name)
        self.input_kinds = list(input_kinds)
        check_kinds(self.input_kinds, name)
        self.mapping, self.timeout = mapping, timeout
        self.max_output_bytes, self.keep_raw = max_output_bytes, keep_raw

    def process(self, ctx):
        claim_artifact(ctx, self.name)
        manifests = documents_for(ctx, self.input_kinds)
        if not manifests:
            return skip(ctx, self.name)
        sarif = run_tool(self.command, manifests, timeout=self.timeout,
                         max_output_bytes=self.max_output_bytes)
        apply_scan(ctx, self.name, sarif, self.mapping, manifests, keep_raw=self.keep_raw)