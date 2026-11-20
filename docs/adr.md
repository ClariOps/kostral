
Date: 2026-11-18

## ADR1. OpaqueIR-unknownKind-undetected


### Status

Completed

### Context

Unmodeled kinds pass silently and vanish from the output. it also carries the raw documents to third-party scanners like Trivy 

### Decision

introduce an OpaqueIR that holds the raw document verbatim, round-trips unchanged, and emits a warning naming the kinds no engine analyzed.

### Consequences/Findings


## ADR2. Kostral-system-runner-layer

### Status

Completed

### Context

when add OpaqueIR, for architectural prospect, we need to decide whether initialize 
    1. the new engine
    2. Coupled it in LoadYamlIRS and force feed the error

### Decision

we have decided to Opt option 1 due to
    Coupling, antipattern and void Guarantees of explicit declaration

but it comes with the issue, whether we opt for implicit declaration but it again void the guarantees so have decided to 

    Add another layer of system level responsibilities KostralRunner, and segregate it from user-defined workflows  

### Consequences/Findings

Preserves explicit declaration rules within user workflows while ensuring system-level guarantees (like OpaqueIR fallback handling) always execute reliably.


## ADR3. remote-mutation-workflow

### Status
Completed

### Context
for mutation of remote engine, there must be initial authorization

### Decision

For allow the engine mutation, these pattern must follow
    1. Registry  will explicitly declared the engine to mutate
    2. workflow will request to allow mutation
    3. http request check for both to be true, to approved mutations

### Consequences

Engine mutates with cross check authorization, /describe will be initiated later

## ADR4. local-mutation-workflow

### Status
Completed

### Context
for mutation of local engine, 

### Decision

For allow the engine mutation, these pattern must follow
    1. Default MappingProxyType for mutates defined to false, with mutating engine to true
    2. for allow mutation, with_metadata() to overrides the mutation
    3. In bus avoid parallel check as it is readonly to get errors
### Consequences

Engine mutates with cross check authorization, 


# ADR5. Engine Descriptor

## Status

Completed
## Context

For Remote third party Engine to communicate. There must be Contract/Authentication, Authorization(mutation) and Input/Output kinds 

## Decision

1. Put a frozen EngineDescriptor (name, version, contract_version, mutates, input kinds, output kinds) on the engine class.
2. For remote engines, serve it at GET /describe and have the client fetch it at startup.
3. The pinned expectation lives in your registry, and the bus fails closed on any mismatch.


## Consequences
    
Basic client/server authentication cross check verified

## ADR6. Pipeline Shape

### Status

Proposed 

### Context

For Remote Third Party Engines, The Output response will be different. 

### Decision

One field per tool is how the contract fragments. Adapters should map each tool’s findings into ReportEvents, and keep the raw tool output under ctx.artifacts["trivy"], namespaced per engine.

### Consequences

to be added later


## ADR7. Unit of exchange

### Status

Proposed 

## Context

IR plus artifacts isn’t enough. It works for Kostral’s own engines. A third-party scanner needs the raw documents of all kinds, or it scans only what Kostral understands

## Decision

1. Request: raw documents in stable order, plus IRs only for engines that declare those kinds. Filter by declared input kinds and redact Secrets by default.
2. Response: findings only, appended by the client, never a replacement report. Modified documents are returned only if the descriptor says mutates: true.
3. Engine failures: don’t put these in ctx.errors or as report events. They must raise and exit 3, or CI can’t tell “the manifest failed” from “the engine broke”.

## Consequences

to be added later


# ADR8. Mutation Enforcement

## Status

Completed

## Context

rogue engine still mutating engines without any authority so need authorization to get guarantees intact.

## Decision

For Remote , workflow request and registry must approved for mutation, The bus should read and freeze the metadata once before the run starts . The bus snapshots before and after each engine and compares canonical JSON from contract

1. A non-mutating engine must leave the documents unchanged, and the report events must only grow (earlier events unchanged).
2. A mutating engine that changes anything must add at least one optimization event. That makes “optimizer changes are always reported” testable.

## Consequences

Rogue engine voilates contract, get errors 

# ADR9. Parallel Engines

## Status

Completed 

## Context

Parallel_checks sequentially in a fixed order and say so.

## Decision

1. sequential, fixed order with Boundaries
2. Parallel-checks got ReadOnly engines
2. later on run non-mutating engines concurrently, each on a read-only snapshot, and merge their findings in declared order, not completion order. Without the fixed merge order, same input → same output breaks.


## Consequences

Read Only engine Falls in Parallel-check, to set boundries, and do sequential order

# ADR10. Error model

## Status

Completed 

## Context

Engine failure, timeout, malformed response, missing tools. All must be an error with the non zero exit, never an empty results

## Decision

Each Error failure got segregated with

1. Engine failures raise and exit with code 3, kept distinct from “the manifest failed” (exit 1). 
2. They never become report events or ctx.errors. 


## Consequences

Each tests come with the predictable errors

# ADR11. Remote security basics

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







