"""Run the integration tests and write a report.

    python tests/report.py                         # writes docs/transparency/test-report.md
    python tests/report.py --out my.md --yaml my.yaml

Uses only the standard library (plus PyYAML, already a KOSTRAL dependency, for --yaml).
Exit code is 1 if any test fails or a known failure unexpectedly passes.

Reasons for known failures come from the first paragraph of each test's docstring.
Add a line "Guarantee: <text>" to a docstring to show which guarantee it checks.
"""
import argparse
import datetime
import io
import re
import sys
import unittest
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Recorder(unittest.TextTestResult):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.rows = []

    def _add(self, test, outcome, detail=""):
        method = getattr(test, test._testMethodName, None)
        doc = (method.__doc__ or "").strip() if method else ""
        self.rows.append({
            "id": test.id(), "module": test.__class__.__module__.split(".")[-1],
            "name": test._testMethodName, "outcome": outcome, "doc": doc,
            "detail": detail.strip().splitlines()[-1] if detail.strip() else "",
        })

    def addSuccess(self, test):
        super().addSuccess(test); self._add(test, "passed")

    def addFailure(self, test, err):
        super().addFailure(test, err); self._add(test, "failed", self.failures[-1][1])

    def addError(self, test, err):
        super().addError(test, err); self._add(test, "error", self.errors[-1][1])

    def addSkip(self, test, reason):
        super().addSkip(test, reason); self._add(test, "skipped", reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err); self._add(test, "known failure")

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test); self._add(test, "unexpected success")


def paragraph(doc):
    first = re.split(r"\n\s*\n", doc.strip())[0] if doc else ""
    return " ".join(first.split())


def cell(text):
    return text.replace("|", "\\|")


def guarantee(doc):
    m = re.search(r"^\s*Guarantee:\s*(.+)$", doc, re.M)
    return m.group(1).strip() if m else ""


def build_markdown(rows, counts, started):
    out = [f"# KOSTRAL test report", "",
           f"Generated {started:%Y-%m-%d %H:%M} by `tests/report.py`. Do not edit by hand.", "",
           "## Summary", "", "| Outcome | Count |", "| --- | --- |"]
    for k in ("passed", "known failure", "failed", "error", "unexpected success", "skipped"):
        if counts.get(k):
            out.append(f"| {k} | {counts[k]} |")
    out.append(f"| total | {sum(counts.values())} |")

    def table(title, selected, with_reason):
        if not selected:
            return
        out.extend(["", f"## {title}", "",
                    "| Test | Guarantee | Reason |" if with_reason else "| Test | Detail |",
                    "| --- | --- | --- |" if with_reason else "| --- | --- |"])
        for r in selected:
            if with_reason:
                out.append(f"| `{r['module']}.{r['name']}` | {cell(guarantee(r['doc']) or 'not tagged')} | {cell(paragraph(r['doc']) or 'no reason written')} |")
            else:
                out.append(f"| `{r['module']}.{r['name']}` | {r['detail'] or r['outcome']} |")

    table("Known failures (code breaks a guarantee today)", [r for r in rows if r["outcome"] == "known failure"], True)
    table("Failures and errors", [r for r in rows if r["outcome"] in ("failed", "error")], False)
    table("Unexpected successes (remove the expectedFailure marker)", [r for r in rows if r["outcome"] == "unexpected success"], False)
    table("Skipped", [r for r in rows if r["outcome"] == "skipped"], False)

    matrix = [r for r in rows if r["module"] == "test_matrix" and r["name"].startswith("test_") and "__" in r["name"]]
    if matrix:
        per = OrderedDict()
        for r in matrix:
            variant = r["name"].rsplit("__", 1)[1]
            per.setdefault(variant, Counter())[r["outcome"]] += 1
        out.extend(["", "## Example files by use case", "", "| Use case | Files | Passed | Not passed |", "| --- | --- | --- | --- |"])
        for variant, c in per.items():
            total = sum(c.values())
            out.append(f"| {variant.replace('_', '-')} | {total} | {c['passed']} | {total - c['passed']} |")

    others = [r for r in rows if r not in matrix and r["outcome"] == "passed"]
    if others:
        out.extend(["", "## Other passing tests", "", "| Test | Guarantee or purpose |", "| --- | --- |"])
        for r in others:
            out.append(f"| `{r['module']}.{r['name']}` | {cell(guarantee(r['doc']) or paragraph(r['doc']) or r['name'].replace('_', ' '))} |")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "transparency" / "test-report.md"))
    ap.add_argument("--yaml")
    args = ap.parse_args()

    started = datetime.datetime.now()
    suite = unittest.TestLoader().discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    runner = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0, resultclass=Recorder)
    result = runner.run(suite)
    rows = sorted(result.rows, key=lambda r: r["id"])
    counts = Counter(r["outcome"] for r in rows)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_markdown(rows, counts, started), encoding="utf-8")
    if args.yaml:
        import yaml
        Path(args.yaml).write_text(yaml.safe_dump(
            {"generated": started.isoformat(timespec="seconds"), "summary": dict(counts),
             "tests": [{"id": r["id"], "outcome": r["outcome"], "guarantee": guarantee(r["doc"]),
                        "reason": paragraph(r["doc"]) if r["outcome"] == "known failure" else ""} for r in rows]},
            sort_keys=False), encoding="utf-8")
    print(f"{sum(counts.values())} tests: " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    print(f"report written to {out}")
    return 0 if not (counts["failed"] or counts["error"] or counts["unexpected success"]) else 1


if __name__ == "__main__":
    sys.exit(main())
