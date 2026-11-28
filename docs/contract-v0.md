# KOSTRAL engine contract v0

Date: 2026-11-28 · `CONTRACT_VERSION = 1` (`kostral/core/contract.py`)

**Status: v0.** This replaces the "draft v0" in `engine-contract.md`. It was written after the Trivy adapter ran against real Trivy output (0.76.2), as ADR16 asked. It describes what the code does today. Section 8 lists what is deliberately not in v0; those items go into v0.1.

There are three kinds of engine. They share one set of rules (section 2) and differ in where they run and what travels between them.

| | Local | Remote (`native`) | External (`external`) |
| :--- | :--- | :--- | :--- |
| Runs | In the KOSTRAL process | HTTP service | A third-party scanner, as a subprocess or behind a small HTTP server |
| Speaks | `ctx` directly | IRs in, IRs and findings out | Raw manifests in, a SARIF log out |
| May mutate | Yes, if the workflow grants it | Yes, if workflow and registry both agree | Never |
| Findings come from | The engine appends them | The engine returns them, the client appends them | A mapper turns SARIF into findings |
| Failure | Exception, exit 3 | Handshake or reply error, exit 3 | Tool or log error, exit 3 |

## 1. What an engine is

An engine extends `Module`, has a `name`, and implements `process(ctx)`.

- `ctx.irs`: the documents, one object per Kubernetes document.
- `ctx.report`: the findings. Engines only append.
- `ctx.artifacts`: data an engine leaves behind, keyed by engine name. An engine never overwrites another engine's entry.
- Engines talk to each other only through `ctx`.

A workflow is a Python file that defines `workflow`:

```python
workflow = {
    "seq_before": [],        # may mutate, run first
    "parallel_checks": [],  # read-only engines
    "seq_after": [],        # run last
}
```

Order is `seq_before`, `parallel_checks`, `seq_after`. `parallel_checks` runs one engine after another, in list order, today. The name says the engines are eligible to run in parallel, not that they do (ADR8). `KostralRunner` runs the coverage engine before the workflow; the workflow cannot skip it and `--skip-rules` / `--allow-rules` do not hide its findings (ADR2).

## 2. Shared rules (all three kinds)

### 2.1 Findings

| Field | Notes |
| :--- | :--- |
| `rule`, `resource`, `engine`, `category`, `severity`, `level` | Always present |
| `issue`, `fix` | Required for `warning` and `error` levels; `message` must be absent |
| `message` | Required for `optimization`; `issue`, `impact`, `fix` must be absent |
| `impact` | Optional for `warning` and `error` |

Every finding goes through `Report.append_event`, local or not. A reply with no findings key, or a malformed finding, is an error.

### 2.2 Permissions

One permission: `mutates` (default `False`).

- The workflow grants it with `with_metadata(Engine(), mutates=True)`. Unknown keys are an error.
- Metadata is frozen when the bus is built; an engine cannot grant itself mutation.
- A mutating engine in `parallel_checks` raises `ValueError` when the bus is built.

### 2.3 What the bus checks around every engine

The bus snapshots documents and report before an engine and compares after. A broken rule raises `EngineContractViolation` (exit 3).

| Rule | Violation |
| :--- | :--- |
| Read-only means read-only | A document changed after an engine with `mutates=False` |
| Changes are reported | A document changed after a mutating engine that added no `optimization` finding |
| The report only grows | An earlier finding was removed or edited |
| Unanalyzed documents are untouchable | A document of an unmodeled kind was edited, removed or reordered |

The bus observes documents and the report only. Files, network and other side effects are not observed and engines are not sandboxed.

### 2.4 Exit codes

| Code | Meaning |
| :--- | :--- |
| 0 | Run completed, no error-level findings |
| 1 | Run completed with error-level findings |
| 2 | Usage error |
| 3 | An engine or KOSTRAL itself failed |

An engine failure is never turned into a report event. The exit code is derived once, from the final `ctx`, after all engines and renderers ran (ADR9).

### 2.5 Output

Text, JSON and YAML renderers show the same findings.

- **JSON, default:** each finding has `rule`, `severity`, `category`. This shape did not change.
- **JSON with `--verbose`:** adds `engine`, `level`, `message`, `issue`, `impact`, `fix`. The flag is passed to `JSONRenderer` in all three commands in `cli/main.py`.
- Raw tool output is never part of the rendered output or the exit code.

## 3. Local engine

Runs in process. The workflow author owns the code, so the workflow author grants mutation (ADR4).

```python
class TeamLabelEngine(Module):
    name = "team-label-engine"

    def process(self, ctx):
        for ir in ctx.irs:
            manifest = ir.to_manifest()
            if manifest.get("kind") != "Deployment":
                continue
            if "team" not in manifest.get("metadata", {}).get("labels", {}):
                ctx.report.warning(
                    rule="missing-team-label", engine=self.name,
                    resource=manifest["metadata"]["name"],
                    issue="Deployment has no 'team' label",
                    fix="add metadata.labels.team")
```

Rules: section 2 applies in full. `to_manifest()` returns the source document verbatim for an untouched IR and overlays only changed fields otherwise (ADR14). Comments and quoting style are lost.

## 4. Remote engine (`native` profile)

An HTTP service wrapped in a client with the same interface as a local engine. Experimental.

### 4.1 Server

```python
serve(MyEngine(), version="1.0.0", input_kinds=["Deployment"],
      token_env="KOSTRAL_TOKEN_MYENGINE", host="127.0.0.1", port=9001)
```

Endpoints: `GET /describe` and `POST /process`. The server refuses to start unless the variable named by `token_env` holds a token of at least 16 characters.

### 4.2 Descriptor (`GET /describe`)

Exactly these fields; a missing or extra field is an error.

| Field | Meaning |
| :--- | :--- |
| `name` | Must equal the name in the workflow and registry |
| `version` | Non-empty string; must equal the registry pin |
| `contract_version` | Integer; must equal `1` |
| `mutates` | Must equal what the workflow allows |
| `input_kinds` | Kinds analyzed. `"*"` means every kind except `Secret`, which must be named |
| `profile` | Optional: `"native"` (default) or `"external"`. A mismatch is refused before anything is sent |

### 4.3 Registry entry

```json
{
  "name": "validator-engine",
  "endpoint": "http://127.0.0.1:9002/process",
  "descriptor": { "version": "1.0.0", "input_kinds": ["Deployment", "Service"] },
  "metadata": { "mutates": false },
  "token_env": "KOSTRAL_TOKEN_VALIDATOR"
}
```

`descriptor` (version and kinds) is required. `token_env` is a variable name, never the token. Mutation needs both the workflow request and the registry approval (ADR3).

### 4.4 Exchange

1. The client reads `/describe` and checks name, contract version, pinned version and kinds, and the mutation permission. Any mismatch: error, nothing sent.
2. Request: `{"irs": [{"kind": ..., "manifest": ...}], "opts": {...}}`. Only pinned kinds are sent. Everything else, and every Secret not named, stays in the client and is merged back in its original position. The server also answers `400` to an undeclared kind.
3. Reply: `{"irs": [...], "findings": [...]}`. Same number of documents, same kind at each position. Findings are appended, never a replacement report (ADR15).
4. A reply that is not JSON, or lacks `irs` or `findings`, is an error, not an empty result.

Timeout: 30 seconds by default.

### 4.5 Authentication

Every request on every endpoint carries `Authorization: Bearer <token>`, checked first with `hmac.compare_digest`; otherwise `401`. A token is sent only over `https`, or over `http` to localhost (ADR11).

## 5. External engine (`external` profile)

An external scanner (Trivy, kube-linter, Checkov) is not asked to speak KOSTRAL. It writes a SARIF 2.1.0 log and KOSTRAL maps that log into findings (ADR18). SARIF is used in one place: the mapper `sarif_to_findings(log, profile)`. There are two forms that share the runner and the mapper.

### 5.1 Local form: `ExternalToolEngine`

```python
ExternalToolEngine(
    "trivy",
    ["trivy", "config", "--format", "sarif", "--quiet", "{dir}"],
    mapping=SarifProfile.from_dict({"fix_sources": ["fixes", "help_uri"]}),
    timeout=120,        # default 60
    keep_raw=False,
)
```

Constructor: `name`, `command`, `input_kinds=("*",)`, `mapping`, `timeout`, `max_output_bytes` (10 MB), `keep_raw`.

**Command contract.** The command must:

1. Be a list of strings. It is run with no shell.
2. Read the manifests from `{dir}`. `{dir}` is replaced by a temporary folder holding document N as `000N.yaml`.
3. Print a SARIF log to stdout.
4. Exit 0 when the scan worked, even if it found problems. For Trivy, do not pass `--exit-code`. A non-zero exit means the tool broke: `ToolError`, exit 3.

**Run.** `subprocess.run` with stdin closed, stdout captured to a file in the temp folder (capped at `max_output_bytes`), stderr kept for the error message, the timeout, and the temp folder as working directory. The environment is inherited, so a token such as `TRIVY_TOKEN` in the shell reaches the tool. The temp folder is deleted when the run ends. The tool must be installed on the machine (`trivy --version`) and may need network access on its first run to fetch its rules.

**Behaviour.** Read-only by construction: it appends findings and never touches a document. If no document matches `input_kinds`, the tool is not run.

### 5.2 Remote form: external scanner behind a server

This is KOSTRAL's own small server around a scanner command. It is not Trivy's `trivy server`, which serves vulnerability data and does not run misconfiguration checks (those run on the client even in Trivy's client/server mode), so it is not needed for `trivy config`.

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

- **Request:** `{"documents": [<manifest>, ...]}`. No IR class names, no `opts`. Only pinned kinds are sent; a Secret only if named.
- **Server:** writes the documents to a temp folder, runs the pinned command as in 5.1, returns `{"sarif": <log>}`.
- **Reply:** exactly `{"sarif": <log>}`. It cannot carry a report or documents.
- **Descriptor:** `"profile": "external"` and `mutates: false`. A registry entry may not request or approve mutation.
- **Limits:** request and reply capped at 10 MB (`413` for a larger request), plus a tool timeout.
- Authentication and handshake are as in 4.2 and 4.5.

### 5.3 Mapping (both forms)

The mapping is pinned, so severity and fix decisions are reviewed, not hidden in code.

| Key | Meaning |
| :--- | :--- |
| `levels` | SARIF `level` to `[kostral level, severity]`. Default: `error` to `error`/`HIGH`, `warning` to `warning`/`medium`, `note` to `warning`/`low`. An unlisted level is an error. No `level` on a result: the rule's default, then `warning` |
| `fix_sources` | Where `fix` may come from, in order: `fixes`, `help` (`rule.help.text`), `help_uri` (`"see <uri>"`). Default `["fixes", "help_uri"]`. `help` is off by default because some tools put metadata there |
| `category`, `default_fix` | Optional |

- No fix source and no `default_fix`: error. KOSTRAL does not invent a fix.
- **Issue text.** The finding's `issue` is the message text with whitespace collapsed. When the message has a `Message:` line, as Trivy's does (it also packs Artifact, Type, Vulnerability, Severity and Link into one message), only that line is used. Otherwise the whole message is used.
- **Resource** comes from the document the finding's file points to (`metadata.name`), never from message text. An unresolvable file keeps its uri as the resource.
- **Order:** findings are sorted by file, line, rule and message.
- **A log that cannot be trusted is an error:** wrong SARIF version, no runs, a run without a `results` list (absent means "not performed", `[]` means "found nothing"), a result without rule or message.

### 5.4 Provenance

`ctx.artifacts[<engine name>]` holds the tool name and version, the number of documents sent and the number of results. The raw SARIF is stored under `raw` only with `keep_raw=True`. Whether a renderer shows it is not part of v0.

## 6. What changed since the draft

- The mapper passes against real Trivy 0.76.2 SARIF (10 results). The "not verified against real output" note is closed, except the clean-run case (section 8).
- `issue` for Trivy is the `Message:` line, not the whole packed message.
- JSON output has a compact default and a verbose form; the flag reaches the JSON renderer.
- The local form of the external profile (`ExternalToolEngine`) has a written command contract.

## 7. Verification

Tested: `tests/integration/test_external.py` (48 tests) with the real Trivy fixture `fixtures/trivy-good.sarif.json`. Not run in the sandbox: the full suite with snapshots, and Trivy itself (the fixture is a real run done by the author).

## 8. Not in v0 (candidates for v0.1)

1. **Exit-code policy.** A scanner that exits non-zero when it finds problems (Checkov, Kubescape, likely) is treated as broken. Needs an `ok_exit_codes` option or a wrapper.
2. **Output channel.** Tools that only write SARIF to a file are not supported without a wrapper.
3. **Tool-specific text handling in the mapper.** The `Message:` rule is Trivy-shaped logic in generic code. Move it into the mapping (for example `message_pattern`).
4. **Severity names.** The defaults give `HIGH` next to `medium` and `low`, and there is no `CRITICAL` (ADR15). Decide the casing and add the level.
5. **Clean run.** Not verified whether Trivy writes `"results": []` for a clean run. This decides whether the "absent means not performed" rule needs a profile option.
6. **Non-SARIF tools** (for example kube-score) need a second mapper behind a small mapper interface.
7. **Empty fields.** `message` and `impact` are `null` for external findings.
8. **Documents:** each is scanned as its own file, so cross-document checks are not seen. Findings carry no line numbers (the log keeps them). `ctx.opts` is still sent to native engines.
9. **Opaque documents:** a mutating engine that inserts a typed document ahead of them is rejected as if it had reordered them (ADR7, decision pending).
10. **Transport:** no TLS setup help, no token rotation, no request size limit on the native server, and the example server handles one request at a time.
11. **Output kinds** in the descriptor, concurrent execution of `parallel_checks`, finer permissions than `mutates`, and version negotiation beyond `contract_version == 1`.