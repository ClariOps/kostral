Date: 2026-11-18
Updated: 2026-11-23

## ADR1. OpaqueIR-unknownKind-undetected

### Status

Completed

### Context

Unmodeled kinds (for example a StatefulSet) passed silently with PASSED and vanished from the rendered output. A raw document should also be able to reach third-party scanners like Trivy.

### Decision

Introduce an OpaqueIR that holds the raw document verbatim, round-trips unchanged, and gets a warning naming the kinds no engine analyzed (the warning is emitted by the CoverageEngine, see ADR2). A remote engine receives opaque documents only if its input_kinds say so ("*" or the kind by name).

### Consequences/Findings

- Nothing is dropped any more, and the output YAML keeps every document in its original order.
- Coverage is a warning, not an error, so PASSED can still coexist with unanalyzed resources. Making it an error is a one-word change (`.warning` to `.error`).
- Revisit if users want a strict mode where an unanalyzed kind fails the run.


## ADR2. Kostral-system-runner-layer

### Status

Completed

### Context

When adding OpaqueIR, for architectural perspective, we need to decide where the "unanalyzed kind" report comes from:
    1. a new engine
    2. coupled in load_yaml_irs and force feed the error

### Decision

We decided to opt for option 1 due to
    coupling, antipattern, and it would void the guarantee of explicit declaration

but it comes with an issue: if the engine is part of the user workflow, the workflow can leave it out (implicit/optional), and that voids the guarantee again. So we decided to

    Add another layer of system level responsibilities, KostralRunner, and segregate it from user-defined workflows.

KostralRunner runs the CoverageEngine first, then the user workflow (the bus).

### Consequences/Findings

Preserves explicit declaration rules within user workflows while ensuring system-level guarantees (like OpaqueIR fallback handling) always execute reliably.

- The CoverageEngine runs outside the bus checks (trusted system code).
- skip_rules / allow_rules do not hide it.
- Its findings come first, so unanalyzed resources are listed first in the report.
- Revisit if a workflow needs a deliberate opt-out (for example Helm charts full of ServiceAccounts).


## ADR3. remote-mutation-workflow

### Status

Completed

### Context

For mutation of a remote engine, there must be an initial authorization.

### Decision

To allow the engine to mutate, this pattern must be followed:
    1. Registry explicitly declares the engine may mutate (metadata.mutates)
    2. Workflow requests to allow mutation (from_registry(entry, metadata={"mutates": True}))
    3. from_registry checks that both are true when the client is built, and the handshake checks that the engine's declared mutates equals what the workflow allows (ADR5)

Registry approval alone grants nothing.

### Consequences

Engine mutates only with cross-checked authorization. The registry file lives next to the workflow, so this is a process control (code review), not a security boundary.


## ADR4. local-mutation-workflow

### Status

Completed

### Context

For mutation of a local engine, the workflow author owns the code, so the workflow author grants it.

### Decision

To allow the engine to mutate, this pattern must be followed:
    1. Default metadata is a read-only MappingProxyType with mutates false; an engine that mutates sets it to true
    2. To allow mutation, with_metadata() overrides it per instance (unknown keys are an error)
    3. The bus refuses a mutating engine in parallel_checks (read-only phase) when the bus is constructed

### Consequences

Local mutation is granted by the workflow; remote mutation also needs the registry (ADR3). A typo in metadata is an error, not silently ignored.


## ADR5. Engine Descriptor

### Status

Completed (minimal, output_kinds deferred)

### Context

For a remote third party engine to communicate, there must be a contract, authorization (mutation) and input kinds. (Authentication is ADR11.)

### Decision

1. A remote server publishes a descriptor at GET /describe: name, version, contract_version, mutates, input_kinds (Kubernetes manifest kinds). The server builds it from the engine's metadata plus what the operator declares; there are no defaults.
2. The client reads it before the first document (once per client) and verifies it. Any mismatch is an error and nothing is sent.
3. The expectation lives in registry.json: the entry name must equal the engine's name, and the entry pins version and input_kinds (both required). contract_version must equal CONTRACT_VERSION (an integer for now).
4. output_kinds is deferred: the bus already detects added or removed documents.

### Consequences

Basic client/server cross check verified. Revisit when a remote engine needs to add documents (that is what output_kinds would declare).


## ADR6. Secret Hold back

### Status

Completed

### Context

Hold back and send only the allowed, explicit kinds of IR to the remote server.

### Decision

Hold back every IR the engine did not declare. The client sends only the kinds pinned in the registry, and the server also answers 400 to any other kind. Redaction was rejected: a redacted value coming back would overwrite the real Secret.

### Consequences

Secrets are held on the client end and merged back into ctx in their original position.
"*" never includes Secret: a Secret goes out only if "Secret" is named. A client without a registry never sends Secrets.
Not covered yet: ctx.opts still goes to every engine.


## ADR7. Mutation Enforcement

### Status

Completed

### Context

A rogue engine could still mutate without any authority, so we need authorization to keep the guarantees intact.

### Decision

For remote, workflow request and registry approval are both needed for mutation. The bus reads and freezes the metadata once before the run starts. The bus snapshots before and after each engine and compares canonical JSON (core/contract.py).

1. A non-mutating engine must leave the documents unchanged, and the report events must only grow (earlier events unchanged).
2. A mutating engine that changes anything must add at least one optimization event. That makes "optimizer changes are always reported" testable.
3. Opaque documents cannot be modified, removed or reordered by any engine, even a mutating one.

### Consequences

A rogue engine violates the contract and gets an error (exit 3).
Known limitation: the opaque check records each document's absolute position, so a mutating engine that inserts a typed document ahead of them is rejected as if it reordered them. Marked as an expected failure in the tests; comparing the opaque documents as an ordered list (without the index) would fix it. Decision pending.


## ADR8. Parallel Engines

### Status

Completed

### Context

parallel_checks hold read-only engines. They run sequentially in a fixed order, and the docs say so.

### Decision

1. Sequential, fixed order, with boundaries.
2. parallel_checks takes read-only engines only (mutates false), enforced when the bus is built.
3. The name parallel_checks stays on purpose: it says the engines are eligible for parallel, not that they run in parallel today. A rename was rejected as churn.
4. Later, run non-mutating engines concurrently, each on its own copy, and merge their findings in declared order, not completion order. Without the fixed merge order, same input gives same output breaks.

### Consequences

Read-only engines fall in parallel_checks, which sets the boundary, and run in sequential order.
A prototype of point 4 (deepcopy per engine, thread pool, merge in declared order) was about 15 lines and gave the same findings in the same order even when the last engine finished first, so it does not depend on the language.


## ADR9. Error model

### Status

Completed

### Context

Engine failure, timeout, malformed response, missing tools. All must be an error with a non-zero exit, never an empty result.

### Decision

Each failure is segregated:

1. Exit codes: 0 clean, 1 the manifest has errors (status FAILED), 2 usage error, 3 an engine or KOSTRAL itself failed. Engine failures raise and exit 3, kept distinct from "the manifest failed" (exit 1).
2. They never become report events or ctx.errors.
3. The exit code is derived once, from the final ctx, after all engines and renderers have run. Engines never call exit.

### Consequences

Each failure has a test (server down, bad token, wrong contract_version, malformed reply, rogue engine).


## ADR10. Remote security critical kinds holdback

### Status

Completed

### Context

Allow only configured kinds which are authorized. Unauthorized or undefined resources are held back at the client end, and the reply must not change what was sent.

### Decision

1. Authorized kinds are defined in registry.json (the pin)
2. Hold back the other kinds at the client end
3. Merge back with ensured non-mutation: the reply must have the same number of documents, with the same kind in the same position, and it is validated before anything is applied

### Consequences

Unauthorized kinds/config or rogue config are held back at the client end. A remote engine cannot add or remove documents (that would need output_kinds).


## ADR11. Token based security and authentication

### Status

Completed

### Context

For communication with a remote engine, there must be token based authentication so both ends know the communication is authentic.

### Decision

1. Token defined in env, never saved. The registry holds only the variable name (token_env).
2. Every request is authenticated first, before routing or reading the body, including /describe and unknown paths. Compared with hmac.compare_digest.
3. Only after that does the server communicate with the client.
4. A missing or weak token (under 16 characters) is an error on both sides; the server refuses to start without one. A token is never sent over plain http beyond localhost.

### Consequences

Every remote call must be authentic. Not covered yet: TLS in the example server (use https or a proxy beyond localhost), token rotation, request size and timeout limits on the server.


## ADR12. Pipeline Shape

### Status

Completed

### Context

For remote third party engines, the output response will be different.

### Decision

Currently sarif based apps are supported, Sarif based output will be JSON kostral, then merge back to findings to get same ouptut. 
original engine response shall remain in ctx.aritifacts["trivy|xyz|kubescore"], in that format   
ctx.artifacts[name] = {"format", "tool", "version" ,"documents_sent", "results"}

### Consequences

Output shall remain same (kostral based JSON), independent of engine Profile (external|native) 


## ADR13. Unit of exchange

### Status

Completed

### Context

IR plus artifacts isn't enough. It works for Kostral's own engines. A third-party scanner needs the raw documents of all kinds, or it scans only what Kostral understands.

### Decision

1. Request: the documents the engine declared, in stable order. Secrets are held back, not redacted (ADR6). Still proposed: send raw manifests (kind: Deployment) instead of IR class names (DeploymentIR).
2. Response: findings only, appended by the client, never a replacement report (ADR15). Still proposed: a non-mutating engine returns no documents. Modified documents are returned only if the descriptor says mutates: true.
3. Engine failures: don't put these in ctx.errors or as report events. They must raise and exit 3 (ADR9).

### Consequences

Rogue engine got rejected, unknown KINDS hold in the client end and merge back to the ctx, No mutating engine got rejected on request, Error contract violation or others raised  


## ADR14. Lossless round trip

### Status

Completed

### Context

explain and optimize output added labels, renamed a container and added protocol: TCP, because to_manifest() rebuilt the document from the IR.

### Decision

The IR keeps its source document. to_manifest() overlays only the fields that changed (for example an optimizer edit); an untouched IR returns its source verbatim.

### Consequences

Remote and local give identical YAML. Comments and quoting style are still lost (yaml.safe_load); byte-identical output would need ruamel.yaml.


## ADR15. Findings are append-only

### Status

Completed

### Context

A remote reply replaced ctx.report, so an engine returning an empty report turned FAILED into PASSED with exit 0.

### Decision

The client never reads a report from a reply. It appends the returned findings with the same validation as local rules (Report.append_event), and a reply without findings is an error. The bus also rejects any engine that removes or changes earlier findings.

### Consequences

No engine can erase findings. Severity names are still inconsistent (low, medium, HIGH) and have no CRITICAL; to be decided with the Trivy adapter.


## ADR16. Contract v0 on hold

### Status

Decided

### Context

The wire format still has Python-shaped parts: documents are wrapped in IR class names (DeploymentIR), a reply must contain irs even from a read-only engine, a finding needs issue and fix, there is no CRITICAL severity, opts goes out in full, and there is no channel for raw artifacts. Publishing Contract v0 now would freeze them.

### Decision

No Contract v0 page at the end of week 2. Instead, internal wire-protocol notes. Contract v0 is written after the Trivy adapter works against the protocol, as the first engine we did not design, and fixes go into v0.1 before any workaround in the adapter.

### Consequences

Engine-writer reviews of the contract stay in week 5. Revisit when the Trivy adapter works.


## ADR17. Implementation language

### Status

Deferred

### Context

Go is attractive: single binary, native concurrency and race detector, strict JSON decoding, and the Kubernetes tools (Trivy, kube-linter, Polaris) are Go. But Go enforces types, not semantics (the mutation, append-only and hold-back rules would still be runtime checks), and a rewrite would spend the weeks meant for calls and proof.

### Decision

Stay in Python through the week 6 gates. The integration tests run koss as a subprocess, so they stay useful as a conformance suite for any other implementation.

### Consequences

After the protocol notes exist, a small engine in Go, written only from those notes, can test whether the protocol is language-neutral. Revisit if outside users ask for a single binary, or if concurrency becomes necessary.


## ADR18. External profile and the SARIF mapper

### Status

Completed (experimental). Answers the open parts of ADR12 and ADR13 for third-party scanners.

### Context

Third-party scanners (Trivy, kube-linter, Checkov) do not speak the native protocol: they need raw documents, not IR class names, and they return their own format, not KOSTRAL findings. Making each tool's output a new field in the contract fragments it (ADR12). Making native engines speak SARIF as well would remove what they need: SARIF has no `optimization` level, no `impact`, and no way to return changed documents.

### Decision

1. One contract in three parts: shared rules, the `native` profile and the `external` profile. The descriptor gets an optional `profile` field. It is additive, so `CONTRACT_VERSION` stays 1 and every existing engine and test is unchanged. The client refuses a server whose profile is not the expected one before sending anything.
2. SARIF is used in one place only: a pure mapper, `sarif_to_findings(log, profile)`. Its output is the same finding dict that `Report.extend` already validates, so both profiles meet at the same point and the bus checks stay the same.
3. Tool-specific decisions (level to level and severity, where `fix` comes from, category) live in a `mapping` block pinned in the registry. An unmapped level, a result with no fix source, or a log that says the analysis was not performed is an error, never a guess.
4. `run()` and `map()` are separate. `run_tool` owns everything outside our control (missing binary, timeout, exit code, output size, not JSON) and `sarif_to_findings` owns the translation. Remote and local scanners share both.
5. The external request is `{"documents": [...]}` and the reply is exactly `{"sarif": ...}`. A reply cannot carry a report or documents. A scanner is read-only by its descriptor.
6. The resource of a finding comes from the document its file points to (one file per document, named by position), not from the tool's message text. Raw tool output goes in `ctx.artifacts[<engine name>]`; an engine never overwrites another engine's entry.

### Consequences

- A new scanner needs a server around its command and a `mapping` block. It does not need new code in KOSTRAL, unless its SARIF cannot express a fix (then use `default_fix` or write a tool-specific mapper).
- Each document is scanned as its own file, so checks across documents are not seen. Findings carry no line numbers yet. And Get Results=[]
- The 10 MB size limits and the timeout apply to the external profile only. The native profile still has none (ADR11).
- Revisit if a scanner's SARIF cannot carry a fix, or if two scanners need different resource resolution.