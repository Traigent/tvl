"""Quick helper for Chapter 2 to inspect a TVL spec and print the knobs."""
from pathlib import Path
import textwrap

import yaml


def load_spec(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def ensure_sections(spec: dict, required: list[str]) -> list[str]:
    missing = [section for section in required if section not in spec]
    return missing


def _format_domain(domain: object) -> str:
    if isinstance(domain, list):
        return f"choices={domain}"
    if isinstance(domain, dict):
        if "range" in domain:
            resolution = domain.get("resolution")
            if resolution is not None:
                return f"range={domain['range']}, resolution={resolution}"
            return f"range={domain['range']}"
        if "set" in domain:
            return f"set={domain['set']}"
        if "registry" in domain:
            return f"registry={domain.get('registry')}"
        if "components" in domain:
            return "tuple[components]"
        return "domain=<object>"
    return "domain=<unknown>"


def print_tvars(tvars: list[dict]) -> None:
    print("Tuned Variables (tvars)")
    print("----------------------")
    for entry in tvars:
        name = entry.get("name", "<unnamed>")
        type_ = entry.get("type", "<untyped>")
        domain = _format_domain(entry.get("domain"))
        print(f"- {name} [{type_}]: {domain}")


def main() -> None:
    spec_path = Path(__file__).with_name("ch2_hello_tvl.tvl.yml")
    spec = load_spec(spec_path)

    required_sections = ["tvl", "environment", "evaluation_set", "tvars", "objectives", "promotion_policy"]
    missing = ensure_sections(spec, required_sections)
    if missing:
        print("Missing sections:", ", ".join(missing))
        return

    module_id = (spec.get("tvl") or {}).get("module", "<unknown>")
    print(textwrap.dedent(
        """\
        Spec loaded successfully.
        module    : {module}
        snapshot  : {snapshot}
        dataset   : {dataset}
        """
    ).format(
        module=module_id,
        snapshot=(spec.get("environment") or {}).get("snapshot_id", "<unknown>"),
        dataset=(spec.get("evaluation_set") or {}).get("dataset", "<unknown>"),
    ))

    print_tvars(spec["tvars"])


if __name__ == "__main__":
    main()
