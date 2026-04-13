import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from tvl.loader import load
from tvl.measurement import load_measurement, prepare_measurement_bundle
from tvl.promotion import epsilon_pareto_gate


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_module_and_inputs(
    inputs: List[Path],
    policy_override: Path | None,
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]], Path, Path]:
    warnings: List[Dict[str, Any]] = []

    if len(inputs) == 3:
        module_path, incumbent_path, candidate_path = inputs
        module = load(module_path)
        return module, module.get("promotion_policy", {}) or {}, warnings, incumbent_path, candidate_path

    if len(inputs) == 2 and policy_override is not None:
        incumbent_path, candidate_path = inputs
        policy_doc = load_yaml(policy_override)
        warnings.append(
            {
                "code": "deprecated_ci_gate_policy_flag",
                "message": (
                    "Passing policy/module YAML via --policy is deprecated. "
                    "Use 'tvl-ci-gate <module> <incumbent> <candidate> --json'."
                ),
            }
        )
        if isinstance(policy_doc, dict) and "promotion_policy" in policy_doc:
            module = policy_doc
            policy = module.get("promotion_policy", {}) or {}
        else:
            policy = policy_doc or {}
            module = {
                "promotion_policy": policy,
                "objectives": policy.get("objectives", []) if isinstance(policy, dict) else [],
            }
        return module, policy, warnings, incumbent_path, candidate_path

    raise ValueError(
        "Usage: tvl-ci-gate <module> <incumbent> <candidate> [--json]. "
        "Legacy fallback: tvl-ci-gate <incumbent> <candidate> --policy <module-or-policy>."
    )


def _qualify_issues(source: str, issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    qualified: List[Dict[str, Any]] = []
    for issue in issues:
        enriched = dict(issue)
        enriched["source"] = source
        qualified.append(enriched)
    return qualified


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline CI gate dry-run using a TVL module as the source of objectives and promotion policy."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Canonical: <module> <incumbent> <candidate>. Legacy fallback: <incumbent> <candidate> with --policy.",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        help="Deprecated fallback for standalone dry-runs. Supply a full module when possible.",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args()

    try:
        module, policy, cli_warnings, incumbent_path, candidate_path = _load_module_and_inputs(
            args.inputs,
            args.policy,
        )
        objectives = module.get("objectives", []) or []

        incumbent_raw = load_measurement(incumbent_path)
        candidate_raw = load_measurement(candidate_path)

        incumbent, incumbent_warnings, incumbent_readiness = prepare_measurement_bundle(module, incumbent_raw)
        candidate, candidate_warnings, candidate_readiness = prepare_measurement_bundle(module, candidate_raw)

        warnings = cli_warnings + _qualify_issues(str(incumbent_path), incumbent_warnings)
        warnings.extend(_qualify_issues(str(candidate_path), candidate_warnings))

        readiness_issues = _qualify_issues(str(incumbent_path), incumbent_readiness)
        readiness_issues.extend(_qualify_issues(str(candidate_path), candidate_readiness))
        if readiness_issues:
            diag = {
                "ok": False,
                "error": "Measurement bundles are not promotion-ready.",
                "warnings": warnings,
                "readiness_issues": readiness_issues,
            }
            print(json.dumps(diag, indent=2))
            raise SystemExit(2)

        decision, evidence = epsilon_pareto_gate(
            incumbent=incumbent,
            candidate=candidate,
            policy=policy,
            objectives=objectives,
        )

        result = {
            "ok": True,
            "decision": decision,
            "warnings": warnings,
            "evidence": evidence,
        }

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Decision: {decision}")
            print(f"Reason: {evidence.get('decision_reason', '')}")
            if warnings:
                print("Warnings:")
                for warning in warnings:
                    print(f"- [{warning.get('code', 'warning')}] {warning.get('message', '')}")
            print("== Evidence Summary ==")
            print(json.dumps(evidence.get("summary", {}), indent=2))

    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        diag = {"ok": False, "error": str(e)}
        print(json.dumps(diag, indent=2))
        sys.exit(2)


if __name__ == "__main__":
    main()
