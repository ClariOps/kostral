"""A stand-in for a real scanner, so the external profile runs anywhere (CI, a laptop
without Trivy). It does what Trivy, kube-linter and Checkov do from KOSTRAL's side:
reads the YAML files in a folder and writes a SARIF 2.1.0 log to stdout.

    python example_scanner.py <folder>

It lists its results in reverse on purpose: KOSTRAL must not depend on the order a
tool happens to use.
"""
import json
import pathlib
import sys

import yaml

RULES = [
    {"id": "EX001", "name": "LatestTag", "shortDescription": {"text": "Image uses the latest tag"},
     "helpUri": "https://example.invalid/rules/EX001", "defaultConfiguration": {"level": "error"}},
    {"id": "EX002", "name": "NoReadiness", "shortDescription": {"text": "No readiness probe"},
     "help": {"text": "Add a readinessProbe to the container."}, "defaultConfiguration": {"level": "note"}},
]


def scan(folder):
    results = []
    for path in sorted(pathlib.Path(folder).glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or doc.get("kind") != "Deployment":
            continue
        for container in doc["spec"]["template"]["spec"]["containers"]:
            image = container.get("image", "")
            if image.endswith(":latest") or ":" not in image:
                results.append(_result(0, "error", path.name, f"Container '{container['name']}' uses the latest image tag"))
            if "readinessProbe" not in container:
                results.append(_result(1, "note", path.name, f"Container '{container['name']}' has no readiness probe"))
    return {
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "example-scanner", "version": "1.0.0", "rules": RULES}},
                  "results": list(reversed(results))}],
    }


def _result(rule_index, level, uri, text):
    return {"ruleId": RULES[rule_index]["id"], "ruleIndex": rule_index, "level": level,
            "message": {"text": text},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": uri}, "region": {"startLine": 1}}}]}


if __name__ == "__main__":
    json.dump(scan(sys.argv[1]), sys.stdout)