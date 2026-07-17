from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text("utf-8"))
    lines = ["# Trusted CEO Agent POC Review", "", f"Automated verdict: {'PASS' if report['passed'] else 'FAIL'}", ""]
    for scenario in report["scenarios"]:
        lines.extend([f"## {scenario['scenario_id']}", "", f"Automated checks: {'PASS' if scenario['passed'] else 'FAIL'}", "", "Human review:", "- [ ] Claims follow Evidence Links", "- [ ] Counter-hypotheses are fair", "- [ ] CEO wording is useful and bounded", "- [ ] Expert boundaries are explicit", ""])
    args.output.write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
