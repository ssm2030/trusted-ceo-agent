from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugin" / "trusted-ceo-agent"
if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from trusted_ceo_agent.canonical import canonical_bytes  # noqa: E402
from trusted_ceo_agent.outputs.render import render_package  # noqa: E402
from trusted_ceo_agent.poc import run_scenario  # noqa: E402


def evaluate(actual: dict, oracle: dict) -> dict:
    checks = {
        "facts": set(oracle["expected_fact_codes"]).issubset(actual["fact_codes"]),
        "signals": set(oracle["expected_signal_codes"]).issubset(actual["signal_codes"]),
        "issues": oracle["expected_issue_keys"] == actual["issue_keys"],
        "grades": oracle["expected_primary_grades"] == actual["primary_grades"],
        "forbidden_claims": set(oracle["forbidden_claim_codes"]).isdisjoint(actual["claim_codes"]),
        "professional_boundary": set(oracle["forbidden_professional_conclusions"]).isdisjoint(
            actual["professional_conclusions"]
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}


def run(results_root: Path, fixtures_root: Path, oracle_root: Path, repeat: int) -> dict:
    results_root.mkdir(parents=True, exist_ok=True)
    records = []
    for fixture in sorted(path for path in fixtures_root.iterdir() if path.is_dir()):
        actual_runs = [run_scenario(fixture) for _ in range(repeat)]
        oracle = json.loads((oracle_root / f"{fixture.name}.json").read_text("utf-8"))
        fingerprints = {canonical_bytes(item["result"]) for item in actual_runs}
        verdict = evaluate(actual_runs[0], oracle)
        verdict["deterministic_repeats"] = len(fingerprints) == 1
        verdict["passed"] = verdict["passed"] and verdict["deterministic_repeats"]
        scenario_root = results_root / fixture.name
        scenario_root.mkdir(parents=True, exist_ok=True)
        for relative, payload in render_package(actual_runs[0]["result"]).items():
            destination = scenario_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        (scenario_root / "evaluation.json").write_bytes(canonical_bytes(verdict))
        records.append({"scenario_id": fixture.name, **verdict})
    report = {"repeat": repeat, "passed": all(item["passed"] for item in records), "scenarios": records}
    (results_root / "report.json").write_bytes(canonical_bytes(report))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, default=ROOT / "tests" / "fixtures" / "evaluation")
    parser.add_argument("--oracles", type=Path, default=ROOT / "tests" / "evaluation" / "oracles")
    parser.add_argument("--repeat", type=int, default=2)
    args = parser.parse_args()
    report = run(args.results_root, args.fixtures, args.oracles, args.repeat)
    print(canonical_bytes(report).decode("utf-8"))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

