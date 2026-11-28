"""Map a SARIF 2.1.0 log into KOSTRAL findings.

This is the ONLY place SARIF is known. It is a pure function: no I/O, no clock,
no environment. The same log and the same profile always give the same findings,
in the same order, whatever order the tool listed its results in.

Nothing is guessed. A level the profile does not map, a result without any
source for `fix`, a log that says the analysis was not performed: each is a
SarifMappingError (the run ends with exit 3), never a silently shorter report.
"""
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Callable, Mapping, Optional

from kostral.core.base import RuleCategory, RuleSeverity

SARIF_VERSION = "2.1.0"

# Where `fix` may come from, in the order a profile lists them.
#   fixes     result.fixes[].description.text   (SARIF's own place for a fix)
#   help      rule.help.text                    (free text; some tools put metadata here)
#   help_uri  rule.helpUri                      ("see <uri>")
FIX_SOURCES = ("fixes", "help", "help_uri")

_PROBLEM_LEVELS = frozenset({"warning", "error"})
_PROFILE_KEYS = frozenset({"levels", "fix_sources", "default_fix", "category"})

UNLOCATED = "<unlocated>"


class SarifMappingError(ValueError):
    """The SARIF log cannot be mapped faithfully."""


# SARIF `level` -> (KOSTRAL level, KOSTRAL severity). Severity names are the
# existing RuleSeverity values; this table does not rename them.
DEFAULT_LEVELS = MappingProxyType({
    "error": ("error", "HIGH"),
    "warning": ("warning", "medium"),
    "note": ("warning", "low"),
})


@dataclass(frozen=True)
class SarifProfile:
    """Per-tool mapping decisions, pinned in the registry so they are reviewed,
    not buried in code. Every field has an explicit default."""

    levels: Mapping = field(default_factory=lambda: DEFAULT_LEVELS)
    fix_sources: tuple = ("fixes", "help_uri")
    default_fix: Optional[str] = None
    category: str = "security"

    @classmethod
    def from_dict(cls, data, who="mapping"):
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ValueError(f"{who}: mapping must be an object")
        unknown = set(data) - _PROFILE_KEYS
        if unknown:
            raise ValueError(f"{who}: unknown mapping keys {sorted(unknown)}; allowed: {sorted(_PROFILE_KEYS)}")

        levels = DEFAULT_LEVELS
        if "levels" in data:
            raw = data["levels"]
            if not isinstance(raw, dict) or not raw:
                raise ValueError(f"{who}: mapping 'levels' must be a non-empty object")
            levels = {}
            for sarif_level, target in raw.items():
                ok = (isinstance(target, (list, tuple)) and len(target) == 2
                      and target[0] in _PROBLEM_LEVELS
                      and target[1] in {s.value for s in RuleSeverity})
                if not ok:
                    raise ValueError(
                        f"{who}: mapping level '{sarif_level}' must map to "
                        f"[warning|error, {'|'.join(s.value for s in RuleSeverity)}]")
                levels[sarif_level] = (target[0], target[1])
            levels = MappingProxyType(levels)

        fix_sources = cls.fix_sources
        if "fix_sources" in data:
            raw = data["fix_sources"]
            if (not isinstance(raw, list) or len(set(raw)) != len(raw)
                    or not all(s in FIX_SOURCES for s in raw)):
                raise ValueError(f"{who}: mapping 'fix_sources' must be a list without repeats from {list(FIX_SOURCES)}")
            fix_sources = tuple(raw)

        default_fix = data.get("default_fix")
        if default_fix is not None and (not isinstance(default_fix, str) or not default_fix.strip()):
            raise ValueError(f"{who}: mapping 'default_fix' must be a non-empty string")

        category = data.get("category", cls.category)
        if category not in {c.value for c in RuleCategory}:
            raise ValueError(f"{who}: mapping 'category' must be one of {sorted(c.value for c in RuleCategory)}")

        return cls(levels=levels, fix_sources=fix_sources, default_fix=default_fix, category=category)


DEFAULT_PROFILE = SarifProfile()


def _text(node):
    """The `text` of a SARIF message-like object, whitespace collapsed."""
    if isinstance(node, dict) and isinstance(node.get("text"), str):
        return re.sub(r"\s", " ", node["text"]).strip()
    return ""

_KEYED_MESSAGE = re.compile(r"^Message:[ \t]*(.+)$", re.MULTILINE)


def _issue_text(node):
    """The finding's sentence. Trivy packs 'Artifact/Type/Vulnerability/Severity/Message/Link'
    into one multi-line message; those extras are already in other fields (rule, severity,
    fix, resource), so when a `Message:` line is present use only that. Otherwise the whole
    message, whitespace collapsed."""
    if isinstance(node, dict) and isinstance(node.get("text"), str):
        m = _KEYED_MESSAGE.search(node["text"])
        if m and m.group(1).strip():
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return _text(node)

def tool_identity(sarif):
    """(name, version) of the first run's tool driver, or (None, None)."""
    try:
        driver = sarif["runs"][0]["tool"]["driver"]
        name, version = driver.get("name"), driver.get("version")
    except (KeyError, IndexError, TypeError, AttributeError):
        return None, None
    return (name if isinstance(name, str) else None,
            version if isinstance(version, str) else None)


def _rule_of(result, rules_by_id, rules_list):
    rule_id = result.get("ruleId")
    index = result.get("ruleIndex")
    rule = {}
    if isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(rules_list):
        rule = rules_list[index] if isinstance(rules_list[index], dict) else {}
        rule_id = rule_id or rule.get("id")
    elif isinstance(rule_id, str):
        rule = rules_by_id.get(rule_id, {})
    if not isinstance(rule_id, str) or not rule_id:
        raise SarifMappingError("a result has no ruleId (and no ruleIndex that names one)")
    return rule_id, rule


def _location(result):
    """(uri or None, start line or 0) of the first location."""
    try:
        physical = result["locations"][0]["physicalLocation"]
        uri = physical["artifactLocation"]["uri"]
    except (KeyError, IndexError, TypeError):
        return None, 0
    if not isinstance(uri, str) or not uri:
        return None, 0
    line = (physical.get("region") or {}).get("startLine")
    return uri, line if isinstance(line, int) and not isinstance(line, bool) else 0


def _fix(result, rule, profile, rule_id):
    for source in profile.fix_sources:
        if source == "fixes":
            for fix in result.get("fixes") or []:
                text = _text((fix or {}).get("description")) if isinstance(fix, dict) else ""
                if text:
                    return text
        elif source == "help":
            text = _text(rule.get("help"))
            if text:
                return text
        elif source == "help_uri":
            uri = rule.get("helpUri")
            if isinstance(uri, str) and uri.strip():
                return f"see {uri.strip()}"
    if profile.default_fix:
        return profile.default_fix
    raise SarifMappingError(
        f"rule '{rule_id}': the result has no fix in {list(profile.fix_sources)} and the "
        f"mapping sets no default_fix; KOSTRAL does not invent one")


def sarif_to_findings(sarif, profile: SarifProfile, *, engine: str,
                      resolve: Optional[Callable[[str], Optional[str]]] = None):
    """Return findings (dicts that `Report.extend` accepts), sorted by location,
    line, rule and message so the order never depends on the tool.

    resolve(uri) may turn a file uri into the resource name KOSTRAL knows; when it
    returns nothing the uri itself is the resource (not guessed from message text)."""
    if not isinstance(sarif, dict):
        raise SarifMappingError("a SARIF log must be an object")
    if sarif.get("version") != SARIF_VERSION:
        raise SarifMappingError(f"SARIF version must be {SARIF_VERSION}, got {sarif.get('version')!r}")
    runs = sarif.get("runs")
    if not isinstance(runs, list) or not runs:
        raise SarifMappingError("the SARIF log has no runs: nothing was analyzed")

    rows = []
    for run in runs:
        if not isinstance(run, dict):
            raise SarifMappingError("a SARIF run must be an object")
        results = run.get("results")
        if not isinstance(results, list):
            # SARIF: [] means "analyzed, found nothing"; null or absent means "not performed".
            raise SarifMappingError("a run has no 'results' list: the tool reports the analysis was not performed")
        rules_list = ((run.get("tool") or {}).get("driver") or {}).get("rules") or []
        if not isinstance(rules_list, list):
            raise SarifMappingError("tool.driver.rules must be a list")
        rules_by_id = {r["id"]: r for r in rules_list if isinstance(r, dict) and isinstance(r.get("id"), str)}

        for result in results:
            if not isinstance(result, dict):
                raise SarifMappingError("a SARIF result must be an object")
            rule_id, rule = _rule_of(result, rules_by_id, rules_list)

            level = (result.get("level")
                     or (rule.get("defaultConfiguration") or {}).get("level")
                     or "warning")                      # SARIF's own default
            if level not in profile.levels:
                raise SarifMappingError(
                    f"rule '{rule_id}': SARIF level {level!r} is not in the mapping "
                    f"{sorted(profile.levels)}")
            kostral_level, severity = profile.levels[level]

            issue = _issue_text(result.get("message"))
            if not issue:
                raise SarifMappingError(f"rule '{rule_id}': the result has no message text")
            fix = _fix(result, rule, profile, rule_id)

            uri, line = _location(result)
            resource = (resolve(uri) if (resolve and uri) else None) or uri or UNLOCATED

            rows.append(((uri or "", line, rule_id, issue, kostral_level), {
                "engine": engine,
                "category": profile.category,
                "severity": severity,
                "level": kostral_level,
                "rule": rule_id,
                "resource": resource,
                "issue": issue,
                "fix": fix,
            }))

    rows.sort(key=lambda row: row[0])
    return [finding for _, finding in rows]