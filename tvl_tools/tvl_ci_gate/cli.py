import argparse
import json
import sys
from pathlib import Path
from typing import Any

from tvl.lints import _uses_13_constructs, lint_module
from tvl.loader import is_pack_document, load
from tvl.measurement import load_measurement, prepare_measurement_bundle
from tvl.promotion import epsilon_pareto_gate
from tvl.yaml_safe import safe_load


def _refuse_unsupported(construct: str, use_json: bool) -> None:
    if use_json:
        diag = {
            "ok": False,
            "error": f"unsupported_construct: {construct}",
            "code": "unsupported_construct",
            "construct": construct,
        }
        print(json.dumps(diag, indent=2))
    else:
        print(f"unsupported_construct: {construct}", file=sys.stderr)
    raise SystemExit(2)


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return safe_load(f)


def _load_module_and_inputs(
    inputs: list[Path],
    policy_override: Path | None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], Path, Path]:
    warnings: list[dict[str, Any]] = []

    if len(inputs) == 3:
        module_path, incumbent_path, candidate_path = inputs
        module = load(module_path)
        return module, module.get("promotion_policy", {}) or {}, warnings, incumbent_path, candidate_path

    if len(inputs) == 2 and policy_override is not None:
        incumbent_path, candidate_path = inputs
        policy_doc = load_yaml(policy_override)
        if isinstance(policy_doc, dict):
            if is_pack_document(policy_doc):
                err = ValueError("unsupported_construct: tvl_pack")
                err.code = "unsupported_construct"  # type: ignore[attr-defined]
                err.construct = "tvl_pack"  # type: ignore[attr-defined]
                raise err
            for blk in ("requirements", "monitors", "responses"):
                if blk in policy_doc:
                    err = ValueError(f"unsupported_construct: {blk}")
                    err.code = "unsupported_construct"  # type: ignore[attr-defined]
                    err.construct = blk  # type: ignore[attr-defined]
                    raise err
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


def _qualify_issues(source: str, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    qualified: list[dict[str, Any]] = []
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
        if args.policy is None and _uses_13_constructs(module):
            lint_issues = lint_module(module)
            lint_errors = [i for i in lint_issues if i.get("severity") == "error"]
            if lint_errors:
                diag = {
                    "ok": False,
                    "error": "Module failed runtime lint checks.",
                    "issues": lint_issues,
                }
                print(json.dumps(diag, indent=2))
                raise SystemExit(2)

        objectives = module.get("objectives", []) or []

        incumbent_raw = load_measurement(incumbent_path)
        candidate_raw = load_measurement(candidate_path)

        if args.policy is not None:
            if "monitor_outcomes" in incumbent_raw or "monitor_outcomes" in candidate_raw:
                _refuse_unsupported("monitor_outcomes", args.json)

        incumbent, incumbent_warnings, incumbent_readiness = prepare_measurement_bundle(
            module, incumbent_raw, role="incumbent"
        )
        candidate, candidate_warnings, candidate_readiness = prepare_measurement_bundle(
            module, candidate_raw, role="candidate"
        )

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
            requirements=module.get("requirements"),
            monitors=module.get("monitors"),
        )

        if decision == "Error":
            # Undefined check (e.g. zero_trials): an error, not Reject/NoDecision.
            diag = {
                "ok": False,
                "decision": "Error",
                "error": evidence.get("summary", {}).get("decision_reason", "Error"),
                "codes": evidence.get("summary", {}).get("chance_error_codes", []),
                "warnings": warnings,
                "evidence": evidence,
            }
            if args.json:
                print(json.dumps(diag, indent=2))
            else:
                print("Decision: Error")
                print(f"Reason: {diag['error']}")
            raise SystemExit(2)

        result = {
            "ok": decision == "Promote",
            "decision": decision,
            "warnings": warnings,
            "evidence": evidence,
        }

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Decision: {decision}")
            if _uses_13_constructs(module):
                # Names remain in evidence; render a complete closed explanation.
                reason = evidence.get("summary", {}).get("decision_reason", "").partition(":")[0]
                if reason.endswith("; superior on"):
                    reason = reason.removesuffix("; superior on") + "; at least one objective is superior"
                else:
                    reason = reason.removesuffix(" on")
                print(f"Reason: {reason}")
            else:
                print(f"Reason: {evidence.get('decision_reason', '')}")
            if warnings:
                print("Warnings:")
                for warning in warnings:
                    print(f"- [{warning.get('code', 'warning')}] {warning.get('message', '')}")
            print("== Evidence Summary ==")
            print(json.dumps(evidence.get("summary", {}), indent=2))

        if decision == "Promote":
            raise SystemExit(0)
        else:
            raise SystemExit(2)

    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        if getattr(e, "code", None) == "unsupported_construct":
            _refuse_unsupported(str(getattr(e, "construct", "")), args.json)
        diag = {"ok": False, "error": str(e)}
        print(json.dumps(diag, indent=2))
        sys.exit(2)


if __name__ == "__main__":
    main()
