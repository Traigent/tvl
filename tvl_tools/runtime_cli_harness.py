"""In-process CLI invocation for the packaged runtime conformance runner."""

from __future__ import annotations

import functools
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
from typing import Any, Dict, Optional

import yaml


def invoke_entrypoint(
    *,
    entrypoint: str,
    doc_path: Path,
    extra_args: list[str],
    measurement_role: Optional[str] = None,
    monitor_outcomes: Optional[Dict[str, Any]] = None,
    measurement_format: Optional[str] = None,
    tmp_dir: Path,
) -> tuple[int, Dict[str, Any]]:
    """Invoke a TVL CLI entrypoint in-process for conformance checks and return (exit_code, output_dict)."""
    cfg_path = tmp_dir / "config.yml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "config_id": "cfg0",
                "module_id": "conformance.runtime",
                "assignments": {"model_choice": "small"},
            }
        ),
        encoding="utf-8",
    )
    inc_meas: Dict[str, Any] = {
        "objective_values": {"quality": {"samples": [1.0, 1.0, 1.0]}},
    }
    cand_meas: Dict[str, Any] = {
        "objective_values": {"quality": {"samples": [1.1, 1.1, 1.1]}},
    }
    if monitor_outcomes is not None:
        if measurement_role == "incumbent":
            inc_meas["monitor_outcomes"] = monitor_outcomes
        else:
            cand_meas["monitor_outcomes"] = monitor_outcomes

    inc_path = tmp_dir / "incumbent.yml"
    cand_path = tmp_dir / "candidate.yml"
    if measurement_format == "tvl-runtime-report/1":
        cand_path.write_text(
            json.dumps({"format": "tvl-runtime-report/1"}),
            encoding="utf-8",
        )
    else:
        cand_path.write_text(yaml.safe_dump(cand_meas), encoding="utf-8")
    inc_path.write_text(yaml.safe_dump(inc_meas), encoding="utf-8")

    if entrypoint == "tvl-validate":
        from tvl_tools.tvl_validate.cli import main as fn

        argv = [entrypoint, str(doc_path), "--format", "json"]
    elif entrypoint == "tvl-lint":
        from tvl_tools.tvl_lint.cli import main as fn

        argv = [entrypoint, str(doc_path), "--format", "json"]
    elif entrypoint == "tvl-parse":
        from tvl_tools.tvl_parse.cli import main as fn

        argv = [entrypoint, str(doc_path), "--format", "json"]
    elif entrypoint == "tvl-check-structural":
        from tvl_tools.tvl_check_structural.cli import main as fn

        argv = [entrypoint, str(doc_path), "--json"]
    elif entrypoint == "tvl-check-operational":
        from tvl_tools.tvl_check_operational.cli import main as fn

        argv = [entrypoint, str(doc_path), "--json"]
    elif entrypoint == "tvl-config-validate":
        from tvl_tools.tvl_config_validate.cli import main as fn

        argv = [entrypoint, str(doc_path), str(cfg_path), "--json"]
    elif entrypoint == "tvl-measure-validate":
        from tvl_tools.tvl_measure_validate.cli import main as fn

        argv = [entrypoint, str(doc_path), str(cfg_path), str(cand_path), "--json"]
    elif entrypoint == "tvl-ci-gate":
        from tvl_tools.tvl_ci_gate.cli import main as fn

        if "--policy" in extra_args:
            argv = [entrypoint, str(inc_path), str(cand_path), "--policy", str(doc_path), "--json"]
        else:
            argv = [entrypoint, str(doc_path), str(inc_path), str(cand_path), "--json"]
    elif entrypoint == "tvl-microsim-bridge":
        from tvl_tools.microsim_bridge.cli import main as bridge_main

        argv = [entrypoint, str(doc_path), "--dry-run"]
        # The bridge takes its argv explicitly; bind it so every entrypoint is
        # invoked uniformly as fn() below.
        fn = functools.partial(bridge_main, argv[1:])
    else:
        raise ValueError(f"Unknown entrypoint: {entrypoint}")

    out_buf = io.StringIO()
    err_buf = io.StringIO()
    old_argv = sys.argv
    exit_code = 0
    try:
        sys.argv = argv
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            fn()
    except SystemExit as exc:
        exit_code = int(exc.code) if isinstance(exc.code, int) else 2
    finally:
        sys.argv = old_argv

    stdout_text = out_buf.getvalue().strip()
    stderr_text = err_buf.getvalue().strip()
    parsed: Dict[str, Any] = {}
    lines = stdout_text.splitlines()
    if stdout_text:
        try:
            parsed = json.loads(stdout_text)
        except Exception:  # noqa: BLE001
            try:
                parsed = json.loads(lines[0])
            except Exception:  # noqa: BLE001
                parsed = {"raw_stdout": stdout_text}
    if stderr_text.startswith("unsupported_construct:"):
        construct = stderr_text.split(":", 1)[1].strip()
        parsed.setdefault("code", "unsupported_construct")
        parsed.setdefault("construct", construct)
    return exit_code, parsed
