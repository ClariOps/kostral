# Engine contract (draft v0)

**Status: draft.** This page describes what the code implements today (`CONTRACT_VERSION = 1`, in `kostral/core/contract.py`). It will change when the first third-party adapter needs something it cannot express. Section 8 lists what is not in the contract yet; those items are decisions or ideas, not features.

Reading time is about ten minutes. If you write an engine, comments on this page are the most useful feedback right now.

## 1. What an engine is

An engine is a class that extends `Module`, has a `name`, and implements `process(ctx)`.

- `ctx.irs` holds the documents (one object per Kubernetes document). The engine reads them and, if it is allowed to, changes them.
- `ctx.report` collects findings. An engine appends to it.
- `ctx.artifacts` is a dictionary for data an engine wants to leave behind.
- Engines communicate only through `ctx`.

Local engines run in-process. A remote engine runs as an HTTP service and is wrapped in a client with the same interface, so a workflow holds both kinds the same way.

## 2. Permissions

There is one permission: `mutates` (`True` or `False`, default `False`).

- A workflow grants it with `with_metadata(MyEngine(), mutates=True)`.
- Unknown metadata keys are an error, so a typo cannot silently do nothing.
- Metadata is frozen when the bus is built. An engine cannot edit its metadata or grant itself mutation during a run.
- A mutating engine cannot be placed in `parallel_checks`; building the bus raises `ValueError`.

## 3. What the bus checks around every engine

Before each engine runs, the bus snapshots the documents and the report. After it runs, the bus compares. A broken rule raises `EngineContractViolation` and the run ends with exit code 3.

| Rule | What counts as a violation |
| :--- | :--- |
| Read-only means read-only | A document differs after an engine with `mutates=False` |
| Changes are reported | A document differs after a mutating engine that added no finding with level `optimization` |
| The report only grows | An earlier finding was removed or edited |
| Unanalyzed documents are untouchable | A document of a kind Kostral does not model was edited, removed or reordered, even by a mutating engine |

"Differs" means the manifests, as returned by `to_manifest()`, serialized as sorted JSON, are not equal.

Limits you should know about:

- The bus checks that a changing engine reported at least one `optimization` finding. It does not check that the findings describe every change.
- The bus observes documents and the report only. Files, network calls and other side effects of an engine are not observed, and an engine is not sandboxed.

## 4. Phases and the system layer

A workflow is a Python file that defines a dictionary named `workflow`:

```python
workflow = {
    "seq_before": [],        # engines that may mutate, run first
    "parallel_checks": [],   # read-only engines
    "seq_after": [],         # run last
}
```

Engines run in the order `seq_before`, `parallel_checks`, `seq_after`. Despite its name, `parallel_checks` runs engines one after another, in list order, today. Running them concurrently on read-only snapshots, with findings merged in declared order, is planned (ADR9).

`KostralRunner` is a system layer that runs before your workflow. It runs the coverage engine, which reports each document of an unmodeled kind. Your workflow cannot skip or erase that report, and `--skip-rules` and `--allow-rules` do not hide it.

## 5. Remote engines (experimental)

The remote part of the contract has three parts. Part 1 is shared by every remote engine; parts 2 and 3 are the two **profiles** that say what travels over the wire.

| Part | What it covers | Where |
| :--- | :--- | :--- |
| 1. Shared | Descriptor handshake, pins, token, errors, report only grows, bus checks | this section: Descriptor, Registry entry, Authentication; sections 3 and 6 |
| 2. `native` profile | KOSTRAL engines: IRs in, IRs and findings out, may mutate (workflow request and registry approval) | this section: Server, Handshake then exchange |
| 3. `external` profile | Third-party scanners (Trivy, kube-linter, Checkov): documents in, a SARIF log out, always read-only | "External profile" at the end of this section |

SARIF is used in one place only, the mapper of part 3. Native engines do not speak it, because it has no `optimization` level and cannot carry changed documents.

### Server

```python
from kostral.adapters.remote.server import serve

serve(MyEngine(), version="1.0.0", input_kinds=["Deployment"],
      token_env="KOSTRAL_TOKEN_MYENGINE", host="127.0.0.1", port=9001)
```

The server answers `GET /describe` and `POST /process`. It refuses to start unless the environment variable named by `token_env` holds a token of at least 16 characters.

### Descriptor

`GET /describe` returns exactly these fields; a missing or extra field is an error.

| Field | Meaning |
| :--- | :--- |
| `name` | Must equal the name the workflow gave the engine |
| `version` | Engine version, a non-empty string |
| `contract_version` | Integer; must equal `1` today |
| `mutates` | Must equal what the workflow allows |
| `input_kinds` | Kubernetes kinds the engine analyzes. `"*"` means every kind except `Secret`, which must always be named |
| `profile` | Optional. `"native"` (the default when absent) or `"external"`. The client refuses a server whose profile is not the one the workflow expects, before any document is sent. Adding it is backward compatible, so `contract_version` stays `1` |
 
### Registry entry

```json
{
  "name": "validator-engine",
  "endpoint": "http://127.0.0.1:9002/process",
  "descriptor": { "version": "1.0.0", "input_kinds": ["Deployment", "Service"] },
  "metadata": { "mutates": false },
  "token_env": "KOSTRAL_TOKEN_VALIDATOR"
}
```

`descriptor` pins the version and kinds and is required. `token_env` is the name of an environment variable, never the token; a pasted token is refused. Mutation needs both sides: the workflow requests it and the registry approves it.

### Handshake, then exchange

1. Before any document is sent, the client reads `/describe` and checks name, contract version, pinned version, pinned kinds and the mutation permission. Any mismatch is an error and nothing is sent.
2. The client sends `{"irs": [{"kind": ..., "manifest": ...}], "opts": {...}}`. Only documents of the pinned kinds are sent. All others, and every Secret not named in the registry, stay in the client process and are put back in their original positions afterwards. The server also answers `400` to a kind it did not declare.
3. The server answers `{"irs": [...], "findings": [...]}`. The same number of documents must come back, with the same kind in each position. Findings are appended to the report; they never replace it.
4. A reply that is not JSON, lacks `irs` or `findings`, or has a malformed finding is an error, not an empty result.

The client times out after 30 seconds by default.

### Authentication

Every request carries `Authorization: Bearer <token>`, on every endpoint. The server compares in constant time and answers `401` otherwise. A token is only sent over `https`, or over `http` to localhost.

### External profile (experimental)

An external scanner is not asked to speak KOSTRAL. It runs behind a small server (or as a subprocess), writes a SARIF 2.1.0 log, and KOSTRAL maps that log into the same findings every other engine appends.

```json
{
  "name": "trivy",
  "profile": "external",
  "endpoint": "http://127.0.0.1:9012/process",
  "descriptor": { "version": "0.76.2", "input_kinds": ["*"] },
  "token_env": "KOSTRAL_TOKEN_TRIVY",
  "mapping": { "fix_sources": ["fixes", "help_uri"] }
}
```

- **Request.** `POST /process` with `{"documents": [<manifest>, ...]}` in the order of the run. There are no IR class names and no `opts`. Only the pinned kinds are sent; a `Secret` only if the registry names it. Unmodeled kinds are sent when the kinds allow it, so a scanner sees what the user wrote.
- **Run.** The server writes document N to `000N.yaml` in a temporary folder, runs the pinned command (`{dir}` is that folder, no shell) and returns the tool's log: `{"sarif": <log>}`. The tool must exit 0 even when it finds problems (for Trivy, do not pass `--exit-code`); a non-zero exit means the tool broke.
- **Reply.** Exactly `{"sarif": <log>}` and nothing else. A reply cannot carry a report or documents, so it cannot erase a finding or change a manifest.
- **Descriptor.** Must declare `"profile": "external"` and `mutates: false`. A registry entry may not request or approve mutation.
- **Mapping.** The `mapping` block is pinned in the registry, so severity decisions are reviewed, not hidden in code:
  - `levels`: SARIF `level` to `[kostral level, severity]`. Default: `error` to `error`/`HIGH`, `warning` to `warning`/`medium`, `note` to `warning`/`low`. A level that is not listed is an error, never a guess. When a result has no `level`, the rule's default is used, then `warning` (SARIF's own default).
  - `fix_sources`: where `fix` may come from, in order: `fixes` (`result.fixes`), `help` (`rule.help.text`), `help_uri` (`"see <uri>"`). Default `["fixes", "help_uri"]`: `rule.help` is off by default because some tools put metadata there. With no source and no `default_fix`, the run is an error. KOSTRAL does not invent a fix.
  - `category`, `default_fix`: optional.
- **Resource.** Taken from the document the finding's file points to (`metadata.name`), never parsed from message text. A file KOSTRAL cannot resolve keeps the uri as the resource.
- **Order.** Findings are sorted by file, line, rule and message, so the report does not depend on the order the tool used.
- **A log that cannot be trusted is an error.** Wrong SARIF version, no runs, a run without a `results` list (SARIF: absent means "analysis not performed", `[]` means "found nothing"), a result without rule or message.
- **Limits.** The reply and the tool output are capped at 10 MB, the server refuses a larger request with `413`, and the tool has a timeout.
- **Provenance.** `ctx.artifacts[<engine name>]` holds the tool name and version, the number of documents sent and the number of results. The raw log is stored only with `keep_raw=True`. An engine never overwrites another engine's entry. Artifacts do not enter the rendered output or the exit code.
- **Local form.** `ExternalToolEngine` runs the same command as a subprocess and maps it the same way, with no server and no token.

Known limits: each document is scanned as its own file, so checks that need several documents together are not seen; findings carry no line numbers (the log keeps them); `ctx.opts` is not sent to external scanners and the native profile still sends it (ADR6).


## 6. Errors and exit codes

| Code | Meaning |
| :--- | :--- |
| 0 | Run completed, no error-level findings |
| 1 | Run completed, error-level findings (or a failed deploy) |
| 2 | Usage error, for example a file not found |
| 3 | `koss` itself failed |

An engine failure is exit 3: a contract violation, an unreachable or malformed remote engine, a rejected token, a missing token. Engine failures are never turned into report events, so CI can tell "the manifest failed" (1) from "the engine broke" (3).

## 7. Write and run a local engine

`examples/engine-writer/team_label_workflow.py` is a complete read-only engine:

```python
from kostral.core.base import Module
from kostral.modules.renderer.engine import RendererEngine


class TeamLabelEngine(Module):
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
```

```bash
koss remote ./examples/demo/bad.yaml --exec ./examples/engine-writer/team_label_workflow.py
```

Report events have rules: a `warning` or `error` needs `issue` and `fix` and no `message`; an `optimization` needs `message` and none of `issue`, `impact`, `fix`.

`rogue_workflow.py` in the same folder edits a manifest while declaring nothing. Running it exits with code 3 and the message `engine contract violation: engine 'rogue-engine' changed the manifests but its metadata says mutates=False`.

## 8. Not in the contract yet

- **Raw documents for third-party scanners.** Documents travel as the output of `to_manifest()`, typed or opaque; an untouched document is returned verbatim (ADR14), but comments and quoting style are lost. The `external` profile sends them as raw manifests, with no IR class names. The native profile still wraps them in IR class names.
- **Real Trivy output.** The mapper is tested against a synthetic SARIF fixture built from a real Trivy JSON run, and against an example scanner. It has not been tested against the SARIF Trivy itself writes; do that before pinning a Trivy mapping.
 
- **Transport limits.** No request or response size limit, no TLS setup help, and the example server handles one request at a time (ADR11 is Proposed).
- **Concurrent execution** (ADR9).
- **Finer permissions** than the single `mutates` flag.
- **Version negotiation.** `contract_version` must equal `1` exactly.
