#!/usr/bin/env python3
"""Enforce coverage thresholds and the coverage ratchet.

Reads the reports written by ``scripts/run-coverage.sh``:

* ``coverage/backend/coverage.xml``      (coverage.py XML)
* ``coverage/frontend/coverage-summary.json`` (Vitest ``json-summary``)

Thresholds (design D4):

* backend: 80% lines, 70% branches overall; 85% lines for security-critical modules
* frontend: 70% statements/lines, 60% branches, 70% functions; 80% lines for
  auth/session/collab modules

The ratchet compares the measured values with ``coverage/baseline.json`` and
fails when any metric drops by more than one point.

Usage:
    scripts/check-coverage.py                 # verify
    scripts/check-coverage.py --update-baseline
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND_XML = ROOT / "coverage/backend/coverage.xml"
FRONTEND_JSON = ROOT / "coverage/frontend/coverage-summary.json"
BASELINE = ROOT / "coverage/baseline.json"

BACKEND_TARGETS = {"lines": 80.0, "branches": 70.0}
FRONTEND_TARGETS = {"statements": 70.0, "lines": 70.0, "branches": 60.0, "functions": 70.0}

# Modules whose failure has a security or session impact get a higher bar.
BACKEND_CRITICAL = {
    "routers/auth_router.py": 85.0,
    "routers/ws_router.py": 85.0,
    "routers/pad_router.py": 85.0,
    "dependencies.py": 85.0,
    "coder.py": 85.0,
}
# ``lib/collab/Collab.tsx`` is intentionally not gated here: it depends on
# Excalidraw internals and is exercised end-to-end by UC-03 (Playwright).
FRONTEND_CRITICAL = {
    "authRefreshManager.ts": 80.0,
    "hooks/useLogout.ts": 80.0,
    "hooks/useWorkspace.ts": 80.0,
    "hooks/useCallbackRefState.ts": 80.0,
}

RATCHET_TOLERANCE = 1.0


def _pct(covered: int, total: int) -> float:
    return 100.0 * covered / total if total else 100.0


def read_backend() -> dict:
    if not BACKEND_XML.exists():
        raise SystemExit(f"missing backend report: {BACKEND_XML.relative_to(ROOT)}")
    tree = ElementTree.parse(BACKEND_XML)
    root = tree.getroot()
    total_lines = int(root.get("lines-valid", 0))
    covered_lines = int(root.get("lines-covered", 0))
    total_branches = int(root.get("branches-valid", 0))
    covered_branches = int(root.get("branches-covered", 0))

    critical: dict[str, float] = {}
    for package in root.iter("package"):
        for cls in package.iter("class"):
            filename = cls.get("filename", "")
            for name, target in BACKEND_CRITICAL.items():
                if filename.endswith(name):
                    lines = cls.findall("./lines/line")
                    valid = len(lines)
                    hit = sum(1 for line in lines if int(line.get("hits", 0)) > 0)
                    critical[name] = _pct(hit, valid)

    return {
        "lines": round(_pct(covered_lines, total_lines), 2),
        "branches": round(_pct(covered_branches, total_branches), 2),
        "critical": {name: round(value, 2) for name, value in sorted(critical.items())},
    }


def read_frontend() -> dict:
    if not FRONTEND_JSON.exists():
        raise SystemExit(f"missing frontend report: {FRONTEND_JSON.relative_to(ROOT)}")
    data = json.loads(FRONTEND_JSON.read_text(encoding="utf-8"))
    total = data.get("total", {})
    metrics = {}
    for key in ("statements", "lines", "branches", "functions"):
        metrics[key] = round(float(total.get(key, {}).get("pct", 0.0)), 2)

    critical: dict[str, float] = {}
    for file_path, values in data.items():
        if file_path == "total":
            continue
        for name, _target in FRONTEND_CRITICAL.items():
            if file_path.replace("\\", "/").endswith(name):
                critical[name] = round(float(values.get("lines", {}).get("pct", 0.0)), 2)

    metrics["critical"] = dict(sorted(critical.items()))
    return metrics


def compare(label: str, actual: dict, targets: dict, errors: list[str]) -> None:
    for metric, target in targets.items():
        value = actual.get(metric)
        if value is None:
            errors.append(f"{label}: missing metric '{metric}' in the report")
        elif value < target:
            errors.append(f"{label}: {metric} {value:.2f}% is below {target:.0f}%")


def compare_critical(label: str, actual: dict, targets: dict, errors: list[str]) -> None:
    for module, target in targets.items():
        value = actual.get(module)
        if value is None:
            errors.append(f"{label}: critical module '{module}' missing from the report")
        elif value < target:
            errors.append(f"{label}: critical module '{module}' at {value:.2f}% is below {target:.0f}%")


def ratchet(label: str, actual: dict, baseline: dict, errors: list[str]) -> None:
    for metric, previous in baseline.items():
        current = actual.get(metric)
        if isinstance(previous, dict) or current is None:
            continue
        if previous - current > RATCHET_TOLERANCE:
            errors.append(
                f"{label}: {metric} dropped from {previous:.2f}% to {current:.2f}% "
                f"(more than {RATCHET_TOLERANCE:.0f} point)"
            )


def measured() -> dict:
    return {"backend": read_backend(), "frontend": read_frontend()}


def main(argv: list[str]) -> int:
    actual = measured()

    if "--update-baseline" in argv:
        BACKEND_XML.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Coverage baseline written to {BASELINE.relative_to(ROOT)}")
        return 0

    errors: list[str] = []
    compare("backend", actual["backend"], BACKEND_TARGETS, errors)
    compare_critical("backend", actual["backend"]["critical"], BACKEND_CRITICAL, errors)
    compare("frontend", actual["frontend"], FRONTEND_TARGETS, errors)
    compare_critical("frontend", actual["frontend"]["critical"], FRONTEND_CRITICAL, errors)

    if BASELINE.exists():
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        ratchet("backend", actual["backend"], baseline.get("backend", {}), errors)
        ratchet("frontend", actual["frontend"], baseline.get("frontend", {}), errors)
    else:
        print("warning: coverage/baseline.json is missing; skipping the ratchet", file=sys.stderr)

    summary = {
        "backend": {k: v for k, v in actual["backend"].items() if k != "critical"},
        "frontend": {k: v for k, v in actual["frontend"].items() if k != "critical"},
    }
    print("Measured coverage: " + json.dumps(summary, sort_keys=True))

    if errors:
        print("Coverage check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Coverage thresholds and ratchet passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
