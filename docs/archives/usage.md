# Kostral CLI Reference

> Pre-deployment analysis and optimization for Kubernetes manifests.

Kostral provides a small CLI surface for analyzing, optimizing, and running Kubernetes workflows.

## Synopsis

```text
koss <command> [arguments] [options]
```

Run:

```bash

koss <command> --help
```

---

## Commands

| Command | Purpose |
|---|---|
| `explain` | Analyze a manifest without optimization |
| `optimize` | Optimize, validate, assess security, and produce the resulting state |
| `remote` | Execute a user-defined workflow that can invoke remote engines |
| `run` | Run a Kostral workflow from a Python DSL input |
| `generate` | CLI-based Deployment input |

> `run` and `generate` use the Manifest Preparation Engine. Both commands are currently on hold and may be reintroduced later. 

---

# `koss explain`

Analyze a Kubernetes manifest without applying Optimizer mutations.

## Usage

```bash
koss explain <file> [options]
```

## Arguments

```text
file    Path to the input manifest
```

## Options

```text
--output {json,yaml}
--verbose
```

## Examples

```bash
# Human-readable report
koss explain ./examples/demo/bad.yaml

# JSON report
koss explain ./examples/demo/bad.yaml --output=json

# YAML manifest output
koss explain ./examples/demo/bad.yaml --output=yaml

# YAML output with a detailed report on stderr
koss explain ./examples/demo/bad.yaml --output=yaml --verbose
```

---

# `koss optimize`

Run the optimization workflow and then validate and assess the resulting state.

## Usage

```bash
koss optimize <file> [options]
```

## Arguments

```text
file    Path to the input manifest
```

## Options

```text
--target {local,aks}
--context CONTEXT
--verbose
--dry-run
--skip-rules
--allow-rules
--apply-aks-defaults
--output {json,yaml}
```

## Examples

```bash
# Optimize and report
koss optimize ./examples/demo/bad.yaml

# Optimize without applying the execution target
koss optimize ./examples/demo/bad.yaml --dry-run

# JSON report
koss optimize ./examples/demo/bad.yaml --output=json

# YAML manifest output
koss optimize ./examples/demo/bad.yaml --output=yaml

# YAML manifests plus detailed report
koss optimize ./examples/demo/bad.yaml --output=yaml --verbose
```

---

# `koss remote`

Execute a workflow defined in a Python file.

The workflow can combine local engines and remote engines invoked
through HTTP clients.

## Usage

```bash
koss remote <file> --exec <workflow> [options]
```

## Arguments

```text
file    Path to the input manifest
```
## Required Options

```text
--exec WORKFLOW    Path to the Python workflow definition
```
## Options

```text
--target {local,aks}
--context CONTEXT
--verbose
--dry-run
--skip-rules
--allow-rules
--output {json,yaml}
```
## Example

Start the three engine servers in separate terminals from the
repository root:

```bash
python examples/remote/optimizer_server.py

python examples/remote/validator_server.py

python examples/remote/security_server.py

```
Then execute the workflow from another terminal:

```bash
koss remote ./examples/demo/bad.yaml \
  --exec ./examples/remote/workflow.py
```

JSON report:
```bash
koss remote ./examples/demo/bad.yaml \
  --exec ./examples/remote/workflow.py \
  --output=json
```

YAML report:
```bash
koss remote ./examples/demo/bad.yaml \
  --exec ./examples/remote/workflow.py \
  --output=yaml
```



---

# `koss run`

Run a Kostral workflow from a Python DSL input.

## Usage

```bash
koss run <file> [options]
```

## Arguments

```text
file    Path to the Python DSL application
```

## Options

```text
--target {local,aks}
--verbose
--helm HELM
--dry-run
--skip-rules
--allow-rules
```

## Example

The repository includes a Python DSL example at:

```text
examples/
└── dsl/
    └── app.py
```

The application defines Kubernetes resources with the Kostral DSL:

```python
from kostral.dsl import deployment, pvc


api = deployment(
   "nginxdsl-dep",
   cpu="80m",
   memory="9Mi",
   image="nginx:latest",
   replicas=2,
   ports=[5000]
)


pvc(
     name="mongo-dsl-pvc",
     storage="5Gi",
     storage_class="standard"
 )
```

Run it with:

```bash
koss run ./examples/dsl/app.py
```

`app.py` is the Python DSL input; Kostral loads the user-defined IR and runs the selected workflow.

> `koss run` is currently on hold and may be reinitiated later.

---

# `koss generate`

Create a deployment from CLI-provided deployment parameters.

## Usage

```bash
koss generate [options]
```

## Options

```text
--name NAME
--cpu CPU
--memory MEMORY
--image IMAGE
--helm HELM
--target {local,aks}
--verbose
--dry-run
--skip-rules
--allow-rules
```

## Example

```bash
koss generate   --name backend   --cpu 500m   --memory 512Mi   --image nginx:1.27  
```

> `koss generate` is currently on hold and may be reinitiated later.


---

# Output

`explain` and `optimize` support structured output:

```bash
--output=json
--output=yaml
```

Without `--output`, Kostral uses its human-readable CLI reporting path.

### JSON

Use JSON when another tool, script, or CI system needs the report.

```bash
koss optimize ./app.yaml --output=json
```

### YAML

Use YAML when the resulting Kubernetes manifests are the required output.

```bash
koss optimize ./app.yaml --output=yaml
```

### Verbose

```bash
koss optimize ./app.yaml --verbose
```

For YAML output, `--verbose` keeps the manifest on standard output and emits the detailed report separately on standard error.

This preserves YAML as machine-consumable output.

---

# Standard Input and Piping

Kostral accepts a manifest path as command input.

For rendered Kubernetes YAML, a Unix-style pipeline can be used where the current input loader supports standard input:

```bash
helm template ./chart | koss optimize -
```

Check the installed CLI help before relying on `-` in automation.

---

# Common Workflows

## Inspect

```bash
koss explain ./app.yaml
```

## Optimize

```bash
koss optimize ./app.yaml
```

## Optimize without execution

```bash
koss optimize ./app.yaml --dry-run
```

## Machine-readable report

```bash
koss optimize ./app.yaml --output=json > report.json
```

## Machine-readable manifests

```bash
koss optimize ./app.yaml --output=yaml > optimized.yaml
```

## Manifest + verbose diagnostics

```bash
koss optimize ./app.yaml --output=yaml --verbose > optimized.yaml
```

The manifest remains in `optimized.yaml`; the verbose report is emitted separately through stderr.

---

# Command Help

The CLI itself is the authoritative source for available flags:

```bash
koss explain --help
koss optimize --help
koss remote --help
koss run --help
koss generate --help
```

When this reference and the installed CLI differ, use the CLI help for the version you are running.

---

## Related Documentation

- [System Model](system-model.md) — conceptual model and responsibilities
- [Architecture](architecture.md) — engine and IR architecture
- [Guarantees](guarantees.md) — behavioral guarantees
- [Vision](vision.md) — future direction
- [Documentation Index](README.md)
