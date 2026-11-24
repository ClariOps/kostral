<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/kostral-logo-dark.svg">
    <img src="docs/assets/kostral-logo.svg" alt="Kostral: Engine Governance for Kubernetes" width="800">
  </picture>
</p>

# Kostral: Engine Governance for Kubernetes
**Same manifest, same decision, every time, with every change explained. Engines plug in under one contract.**

Kostral runs analysis and optimization engines over Kubernetes manifests before they reach a cluster. Every engine, local or remote, runs under one contract that Kostral itself enforces: what the engine may change, what it must report, and what it declares about itself.

> **Status: early (`0.1.1b1`).** The pipeline, the 14 built-in rules and the contract checks are implemented and tested. Remote engines are experimental. Each claim below is backed by a test or an example you can run; the [Status](#status) table says which.

Built by [ClariOps](https://clariops.io).

## Try it

```bash
git clone https://github.com/ClariOps/kostral.git
cd kostral
pip install -e .

koss explain ./examples/demo/bad.yaml                 # analyze only
koss optimize ./examples/demo/bad.yaml --dry-run      # optimize, then analyze the result
koss explain ./examples/demo/bad.yaml --output=json   # machine-readable
```

`bad.yaml` is misconfigured on purpose and has one error-level finding, so these commands exit with code 1.

Rendered manifests can be piped in from stdin, for example `helm template ./chart | koss optimize - --dry-run`.

## What it does today

- **A fixed, readable workflow.** `koss optimize` runs Optimizer, Validator, Security, Renderer. `koss explain` runs Validator, Security.
- **14 built-in rules.** 5 optimizer rules (defaults for CPU, memory, their limits, and replicas), 6 validator rules (probes, NodePort exposure, over- and under-provisioning, replica scaling), 3 security rules (latest tag, privileged container, run as root). Each resource is analyzed on its own; there is no cross-resource logic yet.
- **Nothing is silently dropped.** Kinds Kostral does not model (CRDs, for example) pass through unchanged and are reported as unanalyzed.
- **A contract the bus enforces.** Around every engine the bus compares the manifests and the report before and after. A read-only engine that changes a manifest is rejected. An engine that changes a manifest without reporting it is rejected. No engine can erase earlier findings.
- **Same input, same output.** Tested from different working directories and with shuffled file order.
- **Failures are errors, not empty reports.** Exit codes: `0` clean, `1` error-level findings, `2` usage error, `3` engine or internal failure.

## Engines and the contract

An engine is a Python class with a `name` and a `process(ctx)` method. It can run in-process or as a separate HTTP service. Either way Kostral checks it the same way. Read the [engine contract (draft v0)](docs/engine-contract.md), then try a read-only engine and a rogue one in [`examples/engine-writer/`](examples/engine-writer/):

```bash
koss remote ./examples/demo/bad.yaml --exec ./examples/engine-writer/rogue_workflow.py
# koss: engine contract violation: engine 'rogue-engine' changed the manifests
# but its metadata says mutates=False          (exit code 3)
```

Remote engines (experimental) add a handshake before any document is sent: the server's name, contract version, pinned version and input kinds must match; a bearer token is required; Secrets stay on the client unless the registry names them. The shipped example runs three engines on localhost. It is a demonstration, not a production service: static JSON registry, no request size limits, one request at a time.

## Status

| Area | Status | Evidence |
| :--- | :--- | :--- |
| CLI: `explain`, `optimize`, stdin, JSON/YAML output, exit codes | Implemented | `test_guarantees.py`, `test_matrix.py` |
| 14 built-in rules | Implemented | `test_matrix.py` runs every example manifest |
| Contract checks: mutation, descriptor, errors | Implemented | `test_contract.py`, `test_descriptor.py`, `test_runner.py` |
| Remote engines over HTTP | Experimental | `test_remote.py`, `test_token.py`, `test_hold_back.py` |
| Third-party tool adapters (for example Trivy) | Planned | decision records ADR6, ADR7 (Proposed) |
| Concurrent engines | Planned; `parallel_checks` runs read-only engines one after another, in list order | ADR9 |
| `--target` deployment | Experimental, outside the engine contract | |
| DSL (`koss run`), `koss generate` | On hold | |
| Auto-fix, hosted service, other orchestrators | Ideas, not planned work | |

## Known limitations

- One test is marked as a known failure: a mutating engine that inserts a typed document ahead of unanalyzed ones is rejected as if it had reordered them ([test report](docs/transparency/test-report.md)).
- A mutating engine must report its changes, but the bus checks that at least one optimization finding exists, not that the report describes every change.
- The bus observes manifests and the report only. It does not see files, network calls or other side effects of an engine.
- Kostral does not judge whether an engine's findings are correct.

## Documentation

- [CLI reference](docs/usage.md)
- [Guarantees, and the test behind each one](docs/guarantees.md)
- [Engine contract, draft v0](docs/engine-contract.md)
- [Architecture](docs/architecture.md)
- [Decision records](docs/adr.md) and [test report](docs/transparency/test-report.md)
- [Documentation index](docs/README.md)

## Contributing

While the engine contract is a draft, the most useful contributions are feedback on the contract and bug reports. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache License 2.0. Copyright 2026 ClariOps. See [LICENSE](LICENSE).
