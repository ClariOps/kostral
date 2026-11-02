# 📊 KOSTRAL Output Example

This example demonstrates how KOSTRAL analyzes Kubernetes manifests and provides actionable feedback before deployment.

---

## 🚀 Command

```bash
koss optimize ./examples/cases/mixed/full-risk-app.yaml --dry-run --verbose
```

---

## 🔍 Execution Logs (Verbose Mode)
```text
╗  ██╗ ██████╗ ███████╗████████╗██████╗  █████╗ ██╗     
██║ ██╔╝██╔═══██╗██╔════╝╚══██╔══╝██╔══██╗██╔══██╗██║     
█████╔╝ ██║   ██║███████╗   ██║   ██████╔╝███████║██║     
██╔═██╗ ██║   ██║╚════██║   ██║   ██╔══██╗██╔══██║██║     
██║  ██╗╚██████╔╝███████║   ██║   ██║  ██║██║  ██║███████╗
╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝

Kostral — Pre-Deployment Intelligence System
────────────────────────────────────────────
Analyze • Optimize • Validate • Secure

"Making Kubernetes predictable before it runs"
```
🔍 Analyzing: full-risk-app.yaml 

16:45:48 | INFO     | kostral.cli.main | args, Namespace(cmd='optimize', file='./examples/cases/mixed/full-risk-app.yaml', target=None, context=None, verbose=True, dry_run=True, skip_rules=False, allow_rules=False, apply_aks_defaults=False, output=None)
16:45:48 | INFO     | kostral.modules.optimizer.engine | Initializing optimizer ........
16:45:48 | INFO     | kostral.modules.optimizer.engine | 2 resources loaded
16:45:48 | DEBUG    | kostral.core.base | cpu-default: executing (resource=full-risk-app)
16:45:48 | DEBUG    | kostral.core.base | cpu-default: completed
16:45:48 | DEBUG    | kostral.core.base | memory-default: executing (resource=full-risk-app)
16:45:48 | DEBUG    | kostral.core.base | memory-default: completed
16:45:48 | DEBUG    | kostral.core.base | cpu-limit-default: executing (resource=full-risk-app)
16:45:48 | DEBUG    | kostral.core.base | cpu-limit-default: completed
16:45:48 | DEBUG    | kostral.core.base | memory-limit-default: executing (resource=full-risk-app)
16:45:48 | DEBUG    | kostral.core.base | memory-limit-default: completed
16:45:48 | DEBUG    | kostral.core.base | replica-default: not applicable (resource=full-risk-app)
16:45:48 | INFO     | kostral.modules.optimizer.engine | Optimizer completed

16:45:48 | DEBUG    | asyncio | Using selector: KqueueSelector
16:45:48 | INFO     | kostral.modules.validator.engine | Initializing Validator ...
16:45:48 | DEBUG    | kostral.core.base | replica-scaling: not applicable (resource=full-risk-app)
16:45:48 | DEBUG    | kostral.core.base | over-provisioning: not applicable (resource=full-risk-app)
16:45:48 | DEBUG    | kostral.core.base | under-provisioning: not applicable (resource=full-risk-app)
16:45:48 | DEBUG    | kostral.core.base | no-readiness-probe: executing (resource=full-risk-app)
16:45:48 | DEBUG    | kostral.core.base | no-readiness-probe: completed
16:45:48 | DEBUG    | kostral.core.base | no-liveness-probe: executing (resource=full-risk-app)
16:45:48 | DEBUG    | kostral.core.base | no-liveness-probe: completed
16:45:48 | DEBUG    | kostral.core.base | nodeport-exposure: executing (resource=full-risk-service)
16:45:48 | DEBUG    | kostral.core.base | nodeport-exposure: completed
16:45:48 | INFO     | kostral.modules.validator.engine | Validator completed

16:45:48 | INFO     | kostral.modules.security.engine | Initializing Security check ...
16:45:48 | DEBUG    | kostral.core.base | latest-tag: executing (resource=full-risk-app)
16:45:48 | DEBUG    | kostral.core.base | latest-tag: completed
16:45:48 | DEBUG    | kostral.core.base | privileged-container: executing (resource=full-risk-app)
16:45:48 | DEBUG    | kostral.core.base | privileged-container: completed
16:45:48 | DEBUG    | kostral.core.base | run-as-root: executing (resource=full-risk-app)
16:45:48 | DEBUG    | kostral.core.base | run-as-root: completed
16:45:48 | INFO     | kostral.modules.security.engine | Security check completed

16:45:48 | INFO     | kostral.modules.renderer.engine | Initializing Renderer ...
16:45:48 | INFO     | kostral.modules.renderer.engine | Renderer completed

16:45:48 | INFO     | kostral.modules.cloud.engine | Dry-run enabled, skipping deployment


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📦 Resource: full-risk-app

❌ HIGH: privileged-container

Issue : Container runs in privileged mode
Impact: Full host access (critical risk)
Fix   : Remove privileged: true
Engine: security
Category: security

❌ HIGH: run-as-root

Issue : Container 'full-risk-app/app' runs as root (UID 0)
Impact: Increases risk of container escape and privilege escalation
Fix   : Set securityContext.runAsUser to a non-root UID (e.g., 1000)
Engine: security
Category: security

⚠ MEDIUM: no-readiness-probe

Issue : Readiness probe not defined
Impact: Traffic may be routed to unready pods → potential request failures
Fix   : Define readinessProbe to ensure traffic is only sent to healthy pods
Engine: validator
Category: reliability

⚠ MEDIUM: no-liveness-probe

Issue : Liveness probe not defined
Impact: Container failures may not be detected → pods may remain unhealthy
Fix   : Define livenessProbe to enable automatic detection and recovery of failed containers
Engine: validator
Category: reliability

⚠ LOW: latest-tag

Issue : Image uses mutable tag 'latest'
Impact: May lead to unpredictable deployments → increases risk of unverified changes
Fix   : Use a fixed version tag (e.g., v1.2.3) to ensure consistent and reproducible deployments
Engine: security
Category: generic

💡 LOW: cpu-default

Change: CPU request not defined → defaulting to 100m → ensure baseline scheduling
Engine: optimizer

💡 LOW: memory-default

Change: Memory request not defined → defaulting to 128Mi to ensure stable scheduling
Engine: optimizer

💡 LOW: cpu-limit-default

Change: CPU limit not defined → defaulting to 100m to prevent resource overuse
Engine: optimizer

💡 LOW: memory-limit-default

Change: Memory limit not defined → defaulting to 128Mi to prevent excessive memory usage
Engine: optimizer

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📦 Resource: full-risk-service

⚠ MEDIUM: nodeport-exposure

Issue : Service exposed via NodePort → opens access on every node IP
Impact: Increases attack surface → may lead to unauthorized access
Fix   : Use ClusterIP for internal services or Ingress for controlled external access
Engine: validator
Category: network

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Summary
Errors: 2	Warnings: 4	Optimizations: 4

❌ Status: FAILED
💡 Fix issues before they reach your cluster
```

---

## 🔄 JSON Output (Pipeline Mode)

```bash
  koss optimize ./examples/cases/mixed/full-risk-app.yaml --dry-run --verbose --output=json
```

```
{
  "status": "FAILED",
  "summary": {
    "errors": 2,
    "warnings": 4,
    "optimizations": 4
  },
  "resources": {
    "full-risk-app": {
      "errors": [
        {
          "rule": "privileged-container",
          "severity": "HIGH",
          "category": "security"
        },
        {
          "rule": "run-as-root",
          "severity": "HIGH",
          "category": "security"
        }
      ],
      "warnings": [
        {
          "rule": "no-readiness-probe",
          "severity": "medium",
          "category": "reliability"
        },
        {
          "rule": "no-liveness-probe",
          "severity": "medium",
          "category": "reliability"
        },
        {
          "rule": "latest-tag",
          "severity": "low",
          "category": "generic"
        }
      ],
      "optimizations": [
        {
          "rule": "cpu-default",
          "severity": "low",
          "category": "generic"
        },
        {
          "rule": "memory-default",
          "severity": "low",
          "category": "generic"
        },
        {
          "rule": "cpu-limit-default",
          "severity": "low",
          "category": "generic"
        },
        {
          "rule": "memory-limit-default",
          "severity": "low",
          "category": "generic"
        }
      ]
    },
    "full-risk-service": {
      "errors": [],
      "warnings": [
        {
          "rule": "nodeport-exposure",
          "severity": "medium",
          "category": "network"
        }
      ],
      "optimizations": []
    }
  }
}

```
---
## 🧠 What This Shows

KOSTRAL automatically:

* Detects **critical security risks** (privileged containers, root access)
* Identifies **reliability issues** (missing probes)
* Flags **network exposure risks**
* Optimizes **resource allocation**
* Provides **clear fixes with impact**

👉 All before deployment.

---

## 🎯 Why This Matters

Without TRL:

* Issues reach production
* Costs increase due to over/under provisioning
* Security risks remain unnoticed

With TRL:

* Problems are caught early
* Infrastructure is optimized
* Deployments become predictable and safe
