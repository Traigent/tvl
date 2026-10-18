"""Text renderers print an issue's location exactly once (#139)."""

from __future__ import annotations

from tvl_tools.cli_utils import format_issue_line
from tvl_tools.tvl_validate.cli import text_renderer


def test_closed_message_already_carrying_path_is_not_prefixed_again(capsys):
    text_renderer(
        {
            "issues": [
                {
                    "code": "schema_error",
                    "path": ["requirements"],
                    "message": "requirements: expected type: array",
                }
            ]
        }
    )
    assert capsys.readouterr().out == "[schema_error] requirements: expected type: array\n"


def test_plain_message_still_gets_its_path():
    issue = {"code": "invalid_alpha", "path": ["promotion_policy", "alpha"], "message": "must be in (0, 1)"}
    assert format_issue_line(issue) == "[invalid_alpha] promotion_policy.alpha: must be in (0, 1)"


def test_root_path_uses_placeholder():
    assert format_issue_line({"code": "c", "path": [], "message": "bad"}) == "[c] <root>: bad"
