"""The two steps every external engine shares, local or remote:
choose the documents to scan, and apply the scan's result to the context.

Nothing is applied until the whole log has been mapped, so a bad log leaves the
report exactly as it was.
"""
import re
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse

from kostral.core.contract import kind_accepted

from .sarif import sarif_to_findings, tool_identity

_DOC_FILE = re.compile(r"(\d{4})\.yaml")


def documents_for(ctx, input_kinds):
    """Manifests of the accepted kinds, in the order of ctx.irs. A Secret is only
    included if input_kinds names it ("*" never means Secret)."""
    manifests = []
    for ir in ctx.irs:
        manifest = ir.to_manifest()
        if kind_accepted(input_kinds, manifest.get("kind")):
            manifests.append(manifest)
    return manifests


def claim_artifact(ctx, name):
    """Raw output lives under the engine's own name, and an engine never
    overwrites another engine's entry."""
    if name in ctx.artifacts:
        raise ValueError(f"ctx.artifacts already has an entry '{name}'; engine names must be unique")


def resolver_for(manifests):
    """file uri -> resource name, from the order the documents were written in."""
    def resolve(uri):
        match = _DOC_FILE.fullmatch(PurePosixPath(unquote(urlparse(uri).path)).name)
        if not match or int(match.group(1)) >= len(manifests):
            return None
        return (manifests[int(match.group(1))].get("metadata") or {}).get("name") or "<unnamed>"
    return resolve


def skip(ctx, name):
    """Nothing of an accepted kind: nothing is scanned, and the artifact says so."""
    claim_artifact(ctx, name)
    ctx.artifacts[name] = {"format": "sarif", "documents_sent": 0, "results": 0}


def apply_scan(ctx, name, sarif, profile, manifests, *, keep_raw=False):
    claim_artifact(ctx, name)
    findings = sarif_to_findings(sarif, profile, engine=name, resolve=resolver_for(manifests))
    tool, version = tool_identity(sarif)
    ctx.report.extend(findings)                  # append only; never a replacement
    ctx.artifacts[name] = {
        "format": "sarif", "tool": tool, "version": version,
        "documents_sent": len(manifests), "results": len(findings),
        **({"raw": sarif} if keep_raw else {}),
    }