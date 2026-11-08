"""Issue #244: a boolean is not an integer in the exploration lints or in Domain.contains.

``isinstance(True, int)`` is true in Python, so these sites accepted ``true`` where a
positive integer (or a numeric/enum member) is required.
"""

import copy
from pathlib import Path

import pytest
import yaml
from tvl.configuration import validate_configuration
from tvl.lints import lint_module
from tvl.model import Domain

ROOT = Path(__file__).resolve().parents[1]
BASE = yaml.safe_load((ROOT / "spec/examples/agent-router.tvl.yml").read_text())


def _errors(doc):
    return {i["code"] for i in lint_module(doc) if i["severity"] == "error"}


@pytest.mark.parametrize("value", [True, False])
@pytest.mark.parametrize(
    "section,key,code",
    [
        ("budgets", "max_trials", "invalid_max_trials"),
        ("parallelism", "max_parallel_trials", "invalid_parallelism"),
        ("convergence", "window", "invalid_convergence_window"),
    ],
)
def test_exploration_integer_fields_reject_bool(section, key, code, value):
    doc = copy.deepcopy(BASE)
    assert code not in _errors(doc)
    doc["exploration"].setdefault(section, {})[key] = value
    if section == "convergence":
        doc["exploration"]["convergence"].update(metric="hypervolume_improvement", threshold=0.01)
    assert code in _errors(doc)


@pytest.mark.parametrize(
    "domain",
    [
        Domain(path="n", kind="int", minimum=0.0, maximum=5.0),
        Domain(path="x", kind="float", minimum=0.0, maximum=5.0),
        Domain(path="e", kind="enum", values=[0, 1, 2]),
        Domain(path="f", kind="enum", values=[1.0, 2.5]),
    ],
    ids=["int", "float", "enum-int", "enum-float"],
)
def test_domain_membership_rejects_bool_for_numeric_members(domain):
    # Membership (configuration validation) is checked in Domain.contains; Domain.encode
    # keeps its pinned coercions (tests/test_domain_encode_characterization.py).
    assert domain.contains(1) or domain.contains(1.0)
    assert not domain.contains(True)


def test_bool_enum_member_matches_only_a_bool():
    domain = Domain(path="b", kind="enum", values=[False, True])
    assert domain.contains(True)
    assert not domain.contains(1)


def test_config_with_bool_for_int_tvar_is_invalid():
    good = yaml.safe_load((ROOT / "spec/configurations/agent-router.config.yml").read_text())
    good["assignments"]["max_hops"] = 1
    assert validate_configuration(BASE, good)["ok"], validate_configuration(BASE, good)
    config = copy.deepcopy(good)
    config["assignments"]["max_hops"] = True
    report = validate_configuration(BASE, config)
    assert not report["ok"], report
    assert "max_hops" in repr(report), report
