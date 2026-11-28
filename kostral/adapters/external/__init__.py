"""External scanners (Trivy, kube-linter, Checkov, ...): the `external` profile.

A scanner is not asked to speak KOSTRAL. It is run (`runner`), its SARIF output is
mapped (`sarif`) into the same findings every other engine appends, and nothing
else is allowed to change.
"""