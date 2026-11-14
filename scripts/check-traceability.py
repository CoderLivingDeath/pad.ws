#!/usr/bin/env python3
"""Verify that every P0 Use Case has an existing automated test.

The source of truth is ``docs/use-cases.md``. It must list UC-01…UC-10 in the
traceability table and each row must name at least one existing test file and a
status that does not say "to implement". User journeys use Playwright specs;
operator journeys use the deployment harness under ``tests/deploy``.

Exit codes: 0 when the matrix is complete, 1 otherwise.
"""

from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USE_CASES_DOC = ROOT / "docs/use-cases.md"
USE_CASES_SPEC = ROOT / "openspec/specs/use-cases/spec.md"

UC_REQUIREMENT = re.compile(r"^### Requirement: (UC-\d+)", re.MULTILINE)
# Table row: | UC-01 | yes | reqs | evidence | status |
TABLE_ROW = re.compile(r"^\|\s*(UC-\d+)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|\s*$")
# A backtick-delimited path or an inline test reference.
BACKTICK = re.compile(r"`([^`]+)`")

ALLOWED_STATUS = {
    "green",
    "passing",
    "implemented",
    "staging gate",
    "manual gate",
    "approved gate",
}
BLOCKED_STATUS = {"to implement", "todo", "missing", "skipped", "not implemented"}

# Domain prefixes used in the document that are relative to a known directory.
RELATIVE_DIRS = ("tests/e2e/specs", "tests/deploy", "tests/integration", "")


def spec_use_cases() -> list[str]:
    text = USE_CASES_SPEC.read_text(encoding="utf-8")
    return UC_REQUIREMENT.findall(text)


def parse_matrix() -> dict[str, dict[str, str]]:
    text = USE_CASES_DOC.read_text(encoding="utf-8")
    rows: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        match = TABLE_ROW.match(line.strip())
        if not match:
            continue
        uc, p0, requirements, evidence, status = (part.strip() for part in match.groups())
        if not uc.startswith("UC-"):
            continue
        rows[uc] = {
            "p0": p0,
            "requirements": requirements,
            "evidence": evidence,
            "status": status,
        }
    return rows


def resolve_paths(evidence: str) -> list[Path]:
    """Turn the evidence cell into concrete paths that must exist."""
    found: list[Path] = []
    for candidate in BACKTICK.findall(evidence):
        if not re.search(r"\.(ts|js|py|sh)$", candidate):
            continue
        if any(char in candidate for char in "*?["):
            for base in RELATIVE_DIRS:
                matches = glob.glob(str(ROOT / base / candidate))
                found.extend(Path(match).resolve() for match in matches)
            continue
        path = (ROOT / candidate).resolve()
        if not path.exists():
            for base in RELATIVE_DIRS:
                alternative = (ROOT / base / candidate).resolve()
                if alternative.exists():
                    path = alternative
                    break
        found.append(path)
    return found


def is_skipped_spec(path: Path) -> bool:
    if path.suffix not in {".ts", ".js"}:
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(re.search(r"\b(test|describe)\.skip\(", text))


def check() -> list[str]:
    errors: list[str] = []
    required = spec_use_cases()
    if not required:
        errors.append(f"no UC requirements found in {USE_CASES_SPEC.relative_to(ROOT)}")

    matrix = parse_matrix()
    if not matrix:
        errors.append(f"no traceability table rows found in {USE_CASES_DOC.relative_to(ROOT)}")
        return errors

    documented = set(matrix)
    for uc in required:
        if uc not in documented:
            errors.append(f"{uc}: missing from the traceability table")

    for uc, row in sorted(matrix.items()):
        if row["p0"].lower() != "yes":
            continue
        status = row["status"].lower()
        if any(blocked in status for blocked in BLOCKED_STATUS):
            errors.append(f"{uc}: status is '{row['status']}' (must be implemented or an approved gate)")
        elif not any(allowed in status for allowed in ALLOWED_STATUS):
            errors.append(f"{uc}: unrecognised status '{row['status']}'")
        if not row["requirements"]:
            errors.append(f"{uc}: no linked requirements")

        paths = resolve_paths(row["evidence"])
        if not paths:
            errors.append(f"{uc}: no automated test path in the evidence column")
            continue
        missing = [path for path in paths if not path.exists()]
        for path in missing:
            errors.append(f"{uc}: evidence path does not exist: {path.relative_to(ROOT)}")
        for path in paths:
            if not path.exists() or not is_skipped_spec(path):
                continue
            # A documented staging gate may skip on hosts without the
            # prerequisite; an undocumented skip still fails the check.
            if "staging gate" in status:
                continue
            errors.append(f"{uc}: {path.relative_to(ROOT)} contains a skipped test")

    return errors


def main() -> int:
    errors = check()
    if errors:
        print("Traceability check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print(
            f"\n{len(errors)} problem(s). Update docs/use-cases.md or add the missing tests.",
            file=sys.stderr,
        )
        return 1
    print("Traceability check passed: every P0 Use Case has an existing automated test.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
