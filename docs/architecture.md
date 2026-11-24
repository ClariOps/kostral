# Architecture

How the pieces fit, in about five minutes. For the rules an engine must follow see the [engine contract](engine-contract.md); for what is promised and tested see [guarantees](guarantees.md). Choices and their reasons are in the [decision records](adr.md).

## The shape

```text
manifest(s) -> load -> documents (IR) -> engine -> engine -> ... -> report + manifests
                                           ^
                       snapshot before, compare after, for every engine
```

1. **Load.** `koss` reads files, a directory (in sorted filename order) or stdin. Each Kubernetes document becomes an IR object: a typed IR for Deployment, Service, Ingress, ConfigMap, Secret and PersistentVolumeClaim, or an `OpaqueIR` that holds any other kind verbatim.
2. **Run engines.** The `ServiceBus` runs the workflow's engines in order. Around each engine it snapshots the documents and the report, runs the engine, and compares (see the contract, section 3).
3. **Render.** The renderer turns the final documents and the report into text, JSON or YAML.
4. **Deploy (optional).** `--target` applies the result to a cluster. This is experimental and outside the engine contract.

## The pieces

| Piece | What it does | Code |
| :--- | :--- | :--- |
| `Module` | Base class for every engine: a `name` and `process(ctx)` | `kostral/core/base.py` |
| `RunContext` | Shared state: `irs`, `report`, `opts`, `artifacts`. Engines talk only through it | `kostral/core/context.py` |
| IR | One object per document; `to_manifest()` returns its manifest | `kostral/core/ir/` |
| `ServiceBus` | Runs the three phases and enforces the contract around every engine | `kostral/core/bus.py` |
| Contract | Permissions, snapshots, descriptor checks | `kostral/core/contract.py` |
| `KostralRunner` | System layer: runs the coverage engine before any workflow | `kostral/cli/helper.py` |
| Built-in engines | Optimizer (5 rules), Validator (6), Security (3), Coverage, Renderer | `kostral/modules/` |
| Remote adapter | HTTP client, server, registry, token handling | `kostral/adapters/remote/` |
| CLI | `explain`, `optimize`, `remote`, plus `run` and `generate` (on hold) | `kostral/cli/` |

## Workflows

A workflow is a dictionary with three phases. The bus runs `seq_before`, then `parallel_checks`, then `seq_after`.

| Command | Workflow |
| :--- | :--- |
| `koss explain` | Validator, Security |
| `koss optimize` | Optimizer, Validator, Security, Renderer |
| `koss remote --exec FILE` | Whatever `FILE` defines in `workflow`; see `examples/remote/workflow.py` and `examples/engine-writer/` |

The order is explicit in the workflow, not in the engines. The Validator does not depend on the Optimizer; `explain` simply leaves it out.

## Local and remote engines

A remote engine is the same `Module` interface behind an HTTP client. The workflow does not care which it holds, and the bus applies the same checks to both. Before the first document is sent, the client reads the server's descriptor and checks it against what the registry pinned; documents of kinds the engine did not declare, and every Secret not named in the registry, never leave the process. Details are in the [engine contract](engine-contract.md), section 5.

## Kept deliberately simple

- One process, one pass, no hidden state between engines other than `ctx`.
- Engines in a fixed, visible order. No dependency graph.
- Each resource is analyzed on its own; relationships between resources are not inferred.
- `parallel_checks` runs read-only engines one after another today.

## Not built

Third-party tool adapters (ADR6, ADR7 are Proposed), concurrent execution (ADR9), request size limits and TLS help for remote engines (ADR11 is Proposed), service discovery, a registry service. The README status table tracks these.
