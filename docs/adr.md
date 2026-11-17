
# A. OpaqueIR

Date: 2026-11-12

## Status

Proposed 

## Context

Unmodeled kinds pass silently and vanish from the output. it also carries the raw documents to third-party scanners like Trivy 

## Decision

add an OpaqueIR that holds the raw document verbatim, round-trips unchanged, and emits a warning naming the kinds no engine analyzed.

## Consequences

to be added later


# B: 1. Pipeline Shape

## Status

Proposed 

## Context

For Remote Third Party Engines, The Output response will be different. 

## Decision

One field per tool is how the contract fragments. Adapters should map each tool’s findings into ReportEvents, and keep the raw tool output under ctx.artifacts["trivy"], namespaced per engine.

## Consequences

to be added later


# 2. Unit of exchange

## Status

Proposed 

## Context

IR plus artifacts isn’t enough. It works for Kostral’s own engines. A third-party scanner needs the raw documents of all kinds, or it scans only what Kostral understands

## Decision

1. Request: raw documents in stable order, plus IRs only for engines that declare those kinds. Filter by declared input kinds and redact Secrets by default.
2. Response: findings only, appended by the client, never a replacement report. Modified documents are returned only if the descriptor says mutates: true.
3. Engine failures: don’t put these in ctx.errors or as report events. They must raise and exit 3, or CI can’t tell “the manifest failed” from “the engine broke”.

## Consequences

to be added later

# 3. Engine Descriptor

## Status

Proposed 

## Context

For Remote third party Engine to communicate. There must be Contract/Authentication, Authorization(mutation) and Input/Output kinds 

## Decision

1. Put a frozen EngineDescriptor (name, version, contract_version, mutates, input kinds, output kinds) on the engine class.
2. For remote engines, serve it at GET /describe and have the client fetch it at startup.
3. The pinned expectation lives in your registry, and the bus fails closed on any mismatch.
4. ctx can carry a read-only ctx.trace of what ran, with versions and before/after hashes. That is useful provenance, not authority.


## Consequences

to be added later

# 4. Mutation Enforcement

## Status

Proposed 

## Context

rogue engine still mutating engines wihtout any authority so need authorization to get guarantees intact.

## Decision

The bus snapshots before and after each engine and compares canonical JSON.

1. A non-mutating engine must leave the documents unchanged, and the report events must only grow (earlier events unchanged).
2. A mutating engine that changes anything must add at least one optimization event. That makes “optimizer changes are always reported” testable.
3. For in-process Python this is detection, not prevention, so the guarantee should say “detected and rejected”.



## Consequences

to be added later

# 4. Parallel Engines

## Status

Proposed 

## Context

Parallel_checks sequentially in a fixed order and say so. Today it is not parallel anyway (two 0.2s engines took 0.40s).

## Decision

1. sequential, fixed order
2. later on run non-mutating engines concurrently, each on a read-only snapshot, and merge their findings in declared order, not completion order. Without the fixed merge order, same input → same output breaks.


## Consequences

to be added later

# 5. Error model

## Status

Proposed 

## Context

Engine failure, timeout, malformed response, missing tools. All must be an error with the non zero exit, never an empty results

## Decision

Rules to adopt

1. Engine failures raise and exit with code 3, kept distinct from “the manifest failed” (exit 1). 
2. They never become report events or ctx.errors. 
3. The plan’s “never an empty result” is right, but CI can’t tell the two cases apart without a separate exit code.

## Consequences

to be added later

# 6. Remote security basics

## Status

Proposed 

## Context

token, timeout, response size limit, no print of the context in the server

## Decision

1. Secret redaction in requests
2. hmac.compare_digest for token comparison
3. Tokens read from env vars (token_env), never committed
4. Plain HTTP only on localhost

## Consequences

to be added later







