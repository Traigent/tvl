import argparse
import json
from pathlib import Path

from tvl.configuration import load_configuration
from tvl.errors import TVLError
from tvl.loader import load
from tvl.measurement import load_measurement, validate_measurement


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate configuration + measurement bundle against a TVL module")
    parser.add_argument("module", type=Path, help="TVL module YAML")
    parser.add_argument("config", type=Path, help="Configuration YAML")
    parser.add_argument("measurement", type=Path, help="Measurement bundle YAML")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    try:
        module = load(args.module)
        config = load_configuration(args.config)
        measurement = load_measurement(args.measurement)
        report = validate_measurement(module, config, measurement)
        report.update({
            "module": str(args.module),
            "config": str(args.config),
            "measurement": str(args.measurement),
        })

        if args.json:
            print(json.dumps(report, indent=2))
        else:
            if report["ok"]:
                print("Configuration + measurement bundle satisfy structural, operational, and chance requirements.")
            else:
                print("Validation failed.")
            print(f"Promotion-ready: {'yes' if report.get('promotion_ready') else 'no'}")
            if report.get("warnings"):
                print("- Warnings:")
                for issue in report["warnings"]:
                    print(f"    [{issue.get('code', 'warning')}] {issue.get('message', '')}")
            if report.get("promotion_readiness"):
                print("- Promotion readiness issues:")
                for issue in report["promotion_readiness"]:
                    print(f"    {issue}")
            if not report["ok"]:
                if not report["structural"]["ok"]:
                    print("- Structural issues:")
                    for issue in report["structural"]["domains"]:
                        print(f"    [domain] {issue['path']}: {issue['message']}")
                    for issue in report["structural"]["constraints"]:
                        print(f"    [constraint] {issue}")
                if report["operational"]:
                    print("- Operational issues:")
                    for issue in report["operational"]:
                        print(f"    {issue}")
                if report["chance"]:
                    print("- Chance issues:")
                    for issue in report["chance"]:
                        print(f"    {issue}")

        if not report["ok"]:
            raise SystemExit(2)
    except TVLError as exc:
        diag = {
            "ok": False,
            "error": str(exc),
            "module": str(args.module),
            "config": str(args.config),
            "measurement": str(args.measurement),
        }
        print(json.dumps(diag if args.json else diag, indent=2))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
