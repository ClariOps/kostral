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

- **Output kinds.** The decision record ADR5 lists them; the descriptor has no such field.
- **Raw documents for third-party scanners.** Documents travel as the serialized output of `to_manifest()`, typed or opaque. Whether that preserves everything the user wrote (unknown fields, ordering, multi-document layout) has not been verified, so a scanner might see a normalized copy. ADR7 proposes that the response carries findings only unless the engine declares `mutates`, and ADR6 proposes a per-engine place for raw tool output; both are Proposed, not implemented.
- **Transport limits.** No request or response size limit, no TLS setup help, and the example server handles one request at a time (ADR11 is Proposed).
- **Concurrent execution** (ADR9).
- **Finer permissions** than the single `mutates` flag.
- **Version negotiation.** `contract_version` must equal `1` exactly.
