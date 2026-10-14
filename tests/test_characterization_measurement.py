"""Characterization tests for the measurement-bundle checks in ``tvl.measurement``.

Pins the exact return values (issue dicts, their order and messages) and the
exceptions raised by ``normalize_measurement_bundle``, ``_evaluate_objectives``,
``_evaluate_chance`` and ``_evaluate_promotion_readiness`` so a
behaviour-preserving refactor cannot reword, reorder, drop or add an issue."""

# Expected values were recorded from the unchanged source before refactoring.

from __future__ import annotations

import copy

import pytest

from tvl import measurement
from tvl.measurement import (
    _evaluate_chance,
    _evaluate_objectives,
    _evaluate_promotion_readiness,
    normalize_measurement_bundle,
)

FUNCS = {
    "normalize": normalize_measurement_bundle,
    "objectives": _evaluate_objectives,
    "chance": _evaluate_chance,
    "readiness": _evaluate_promotion_readiness,
}


def normalize(value):
    return value


CASES = [('norm_empty',
  'normalize',
  ({},),
  {},
  ('ok', ({'objective_values': {}, 'chance_outcomes': {}}, []))),
 ('norm_copies_ids',
  'normalize',
  ({'bundle_id': 'b', 'config_id': 'c', 'module_id': 'm', 'summary': {'trials': 3}, 'other': 1},),
  {},
  ('ok',
   ({'bundle_id': 'b',
     'config_id': 'c',
     'module_id': 'm',
     'summary': {'trials': 3},
     'objective_values': {},
     'chance_outcomes': {}},
    []))),
 ('norm_canonical_passthrough',
  'normalize',
  ({'objective_values': {'q': {'mean': 1}},
    'chance_outcomes': {'s': {'violations': 0, 'trials': 5}}},),
  {},
  ('ok',
   ({'objective_values': {'q': {'mean': 1}},
     'chance_outcomes': {'s': {'violations': 0, 'trials': 5}}},
    []))),
 ('norm_falsy_sections',
  'normalize',
  ({'objective_values': None, 'chance_outcomes': [], 'objectives': {}, 'chance': None},),
  {},
  ('ok', ({'objective_values': {}, 'chance_outcomes': {}}, []))),
 ('norm_legacy_objectives',
  'normalize',
  ({'objectives': {'q': {'observed': 0.5}}},),
  {},
  ('ok',
   ({'objective_values': {}, 'chance_outcomes': {}, 'legacy_objectives': {'q': {'observed': 0.5}}},
    [{'code': 'deprecated_measurement_objectives',
      'message': "Top-level 'objectives' is deprecated. Use 'objective_values.<name>.samples' or "
                 "'objective_values.<name>.mean/std/n'."}]))),
 ('norm_legacy_chance_with_canonical',
  'normalize',
  ({'chance': {'s': {'observed': 0.1, 'trials': 10}},
    'chance_outcomes': {'s': {'violations': 1, 'trials': 10}}},),
  {},
  ('ok',
   ({'objective_values': {},
     'chance_outcomes': {'s': {'violations': 1, 'trials': 10}},
     'legacy_chance': {'s': {'observed': 0.1, 'trials': 10}}},
    [{'code': 'deprecated_measurement_chance',
      'message': "Top-level 'chance' is deprecated. Use 'chance_outcomes.<name>.violations' and "
                 "'chance_outcomes.<name>.trials'."}]))),
 ('norm_legacy_chance_converted',
  'normalize',
  ({'summary': {'trials': 20},
    'chance': {'ok': {'observed': 0.25, 'trials': 8},
               'default_trials': {'observed': 0.05},
               'skipme': 'not a dict',
               'missing_observed': {'trials': 4},
               'bad_trials': {'observed': 0.5, 'trials': 'x'},
               'bad_observed': {'observed': 'y', 'trials': 4},
               'fractional': {'observed': 0.3, 'trials': 7}},
    'objectives': {'q': {'observed': 1}}},),
  {},
  ('ok',
   ({'summary': {'trials': 20},
     'objective_values': {},
     'chance_outcomes': {'ok': {'violations': 2, 'trials': 8},
                         'default_trials': {'violations': 1, 'trials': 20}},
     'legacy_objectives': {'q': {'observed': 1}},
     'legacy_chance': {'ok': {'observed': 0.25, 'trials': 8},
                       'default_trials': {'observed': 0.05},
                       'skipme': 'not a dict',
                       'missing_observed': {'trials': 4},
                       'bad_trials': {'observed': 0.5, 'trials': 'x'},
                       'bad_observed': {'observed': 'y', 'trials': 4},
                       'fractional': {'observed': 0.3, 'trials': 7}}},
    [{'code': 'deprecated_measurement_objectives',
      'message': "Top-level 'objectives' is deprecated. Use 'objective_values.<name>.samples' or "
                 "'objective_values.<name>.mean/std/n'."},
     {'code': 'deprecated_measurement_chance',
      'message': "Top-level 'chance' is deprecated. Use 'chance_outcomes.<name>.violations' and "
                 "'chance_outcomes.<name>.trials'."},
     {'code': 'legacy_chance_not_convertible',
      'message': "Could not convert legacy chance summary 'missing_observed' to canonical counts. "
                 "Provide 'violations' and 'trials' explicitly."},
     {'code': 'legacy_chance_not_convertible',
      'message': "Could not convert legacy chance summary 'bad_trials' to canonical counts. "
                 'Provide integer trials and a numeric observed rate.'},
     {'code': 'legacy_chance_not_convertible',
      'message': "Could not convert legacy chance summary 'bad_observed' to canonical counts. "
                 'Provide integer trials and a numeric observed rate.'},
     {'code': 'legacy_chance_not_convertible',
      'message': "Legacy chance summary 'fractional' does not map cleanly to integer counts. "
                 "Provide canonical 'violations' and 'trials'."}]))),
 ('norm_legacy_chance_no_summary_trials',
  'normalize',
  ({'chance': {'a': {'observed': 0.5}}},),
  {},
  ('ok',
   ({'objective_values': {}, 'chance_outcomes': {}, 'legacy_chance': {'a': {'observed': 0.5}}},
    [{'code': 'deprecated_measurement_chance',
      'message': "Top-level 'chance' is deprecated. Use 'chance_outcomes.<name>.violations' and "
                 "'chance_outcomes.<name>.trials'."},
     {'code': 'legacy_chance_not_convertible',
      'message': "Could not convert legacy chance summary 'a' to canonical counts. Provide "
                 "'violations' and 'trials' explicitly."}]))),
 ('norm_non_mapping_raises',
  'normalize',
  (['x'],),
  {},
  ('raises', 'AttributeError', "'list' object has no attribute 'get'")),
 ('obj_all_branches',
  'objectives',
  ({'objectives': ['junk',
                   {'direction': 'maximize'},
                   {'name': ''},
                   {'name': 'missing'},
                   {'name': 'no_observed'},
                   {'name': 'band_list', 'band': {'target': [0.2, 0.4]}},
                   {'name': 'band_low', 'band': {'target': [0.2, 0.4]}},
                   {'name': 'band_dict', 'band': {'target': {'center': 1.0, 'tol': 0.5}}},
                   {'name': 'band_dict_partial', 'band': {'target': {'center': 1.0}}},
                   {'name': 'band_bad_list', 'band': {'target': [1, 2, 3]}},
                   {'name': 'band_none_target', 'band': {}},
                   {'name': 'slo_min_bad', 'direction': 'MINIMIZE', 'slo': {'threshold': 5}},
                   {'name': 'slo_min_ok', 'direction': 'minimize', 'slo': {'threshold': 5}},
                   {'name': 'slo_max_bad', 'slo': {'threshold': 5}},
                   {'name': 'slo_max_ok', 'direction': None, 'slo': {'threshold': 5}},
                   {'name': 'slo_no_threshold', 'slo': {}},
                   {'name': 'slo_other_direction',
                    'direction': 'sideways',
                    'slo': {'threshold': 0}},
                   {'name': 'band_and_slo',
                    'direction': 'maximize',
                    'band': {'target': [10, 20]},
                    'slo': {'threshold': 50}},
                   {'name': 'legacy_only'},
                   {'name': 'canonical_wins'}]},
   {'objective_values': {'no_observed': {'std': 1},
                         'band_list': {'samples': [0.5, 0.7]},
                         'band_low': {'mean': 0.1},
                         'band_dict': {'mean': 1.4},
                         'band_dict_partial': {'mean': 100},
                         'band_bad_list': {'mean': 100},
                         'band_none_target': {'mean': 100},
                         'slo_min_bad': {'samples': [6, 8]},
                         'slo_min_ok': {'mean': 5},
                         'slo_max_bad': {'mean': 4.5},
                         'slo_max_ok': {'mean': 5},
                         'slo_no_threshold': {'mean': 1},
                         'slo_other_direction': {'mean': -1},
                         'band_and_slo': {'mean': 30},
                         'canonical_wins': {'mean': 2}},
    'legacy_objectives': {'legacy_only': {'observed': '3.5'},
                          'canonical_wins': {'observed': 9},
                          'no_observed': {}}}),
  {},
  ('ok',
   [{'objective': 'missing', 'code': 'missing_measurement', 'message': 'Measurement missing'},
    {'objective': 'no_observed',
     'code': 'missing_observed',
     'message': 'Observed value required for objective checks'},
    {'objective': 'band_list',
     'code': 'band_violation',
     'message': 'Value 0.6 outside band [0.2, 0.4]'},
    {'objective': 'band_low',
     'code': 'band_violation',
     'message': 'Value 0.1 outside band [0.2, 0.4]'},
    {'objective': 'slo_min_bad', 'code': 'slo_violation', 'message': '7.0 > threshold 5'},
    {'objective': 'slo_max_bad', 'code': 'slo_violation', 'message': '4.5 < threshold 5'},
    {'objective': 'band_and_slo',
     'code': 'band_violation',
     'message': 'Value 30.0 outside band [10, 20]'},
    {'objective': 'band_and_slo', 'code': 'slo_violation', 'message': '30.0 < threshold 50'}])),
 ('obj_empty_module', 'objectives', ({}, {}), {}, ('ok', [])),
 ('obj_none_sections',
  'objectives',
  ({'objectives': None}, {'objective_values': None, 'legacy_objectives': None}),
  {},
  ('ok', [])),
 ('obj_empty_samples_fall_to_mean',
  'objectives',
  ({'objectives': [{'name': 'a', 'slo': {'threshold': 1}}]},
   {'objective_values': {'a': {'samples': [], 'mean': 0}}}),
  {},
  ('ok', [{'objective': 'a', 'code': 'slo_violation', 'message': '0.0 < threshold 1'}])),
 ('obj_direction_not_str',
  'objectives',
  ({'objectives': [{'name': 'a', 'direction': 3}]}, {'objective_values': {'a': {'mean': 1}}}),
  {},
  ('raises', 'AttributeError', "'int' object has no attribute 'lower'")),
 ('obj_band_not_mapping',
  'objectives',
  ({'objectives': [{'name': 'a', 'band': [1, 2]}]}, {'objective_values': {'a': {'mean': 1}}}),
  {},
  ('raises', 'AttributeError', "'list' object has no attribute 'get'")),
 ('obj_slo_not_mapping',
  'objectives',
  ({'objectives': [{'name': 'a', 'slo': 3}]}, {'objective_values': {'a': {'mean': 1}}}),
  {},
  ('raises', 'AttributeError', "'int' object has no attribute 'get'")),
 ('obj_band_incomparable',
  'objectives',
  ({'objectives': [{'name': 'a', 'band': {'target': ['x', 'y']}}]},
   {'objective_values': {'a': {'mean': 1}}}),
  {},
  ('raises', 'TypeError', "'<' not supported between instances of 'float' and 'str'")),
 ('obj_direction_checked_before_band',
  'objectives',
  ({'objectives': [{'name': 'a', 'direction': 1, 'band': [1]}]},
   {'objective_values': {'a': {'mean': 1}}}),
  {},
  ('raises', 'AttributeError', "'int' object has no attribute 'lower'")),
 ('obj_band_then_slo_errors_band_first',
  'objectives',
  ({'objectives': [{'name': 'a', 'band': 7, 'slo': 3}]}, {'objective_values': {'a': {'mean': 1}}}),
  {},
  ('raises', 'AttributeError', "'int' object has no attribute 'get'")),
 ('obj_unhashable_name',
  'objectives',
  ({'objectives': [{'name': ['l']}]}, {}),
  {},
  ('raises', 'TypeError', "unhashable type: 'list'")),
 ('obj_both_bounds_one_none',
  'objectives',
  ({'objectives': [{'name': 'a', 'band': {'target': {'center': None, 'tol': 1}}}]},
   {'objective_values': {'a': {'mean': 1}}}),
  {},
  ('ok', [])),
 ('chance_all_branches',
  'chance',
  ({'promotion_policy': {'chance_constraints': ['junk',
                                                {'threshold': 0.1},
                                                {'name': ''},
                                                {'name': 'missing', 'threshold': 0.1},
                                                {'name': 'passes',
                                                 'threshold': 0.2,
                                                 'confidence': 0.9},
                                                {'name': 'fails', 'threshold': 0.01},
                                                {'name': 'defaults'},
                                                {'name': 'no_trials', 'threshold': 0.5}]}},
   {'chance_outcomes': {'passes': {'violations': 0, 'trials': 100},
                        'fails': {'violations': 5, 'trials': 20},
                        'defaults': {'violations': 0, 'trials': 1000},
                        'no_trials': {'violations': 0, 'trials': 0}}}),
  {},
  ('ok',
   [{'constraint': 'missing', 'code': 'missing_measurement', 'message': 'Chance outcome missing'},
    {'constraint': 'fails',
     'code': 'chance_violation',
     'message': 'ci_upper (0.4556) > threshold (0.01)'},
    {'constraint': 'defaults',
     'code': 'chance_violation',
     'message': 'ci_upper (0.0030) > threshold (0.0)'},
    {'constraint': 'no_trials', 'code': 'chance_violation', 'message': 'No trials available'}])),
 ('chance_empty', 'chance', ({}, {}), {}, ('ok', [])),
 ('chance_none_policy',
  'chance',
  ({'promotion_policy': None}, {'chance_outcomes': None}),
  {},
  ('ok', [])),
 ('chance_none_list',
  'chance',
  ({'promotion_policy': {'chance_constraints': None}}, {}),
  {},
  ('ok', [])),
 ('chance_policy_not_mapping',
  'chance',
  ({'promotion_policy': ['x']}, {}),
  {},
  ('raises', 'AttributeError', "'list' object has no attribute 'get'")),
 ('ready_empty', 'readiness', ({}, {}), {}, ('ok', [])),
 ('ready_policy_calibration',
  'readiness',
  ({'promotion_policy': {'require_calibration': {'enabled': True}}}, {}),
  {},
  ('ok',
   [{'code': 'calibration_evidence_unsupported',
     'message': 'This module requires calibration certificates, but the current measurement bundle '
                'and tvl-ci-gate contract cannot validate them.'}])),
 ('ready_policy_calibration_disabled',
  'readiness',
  ({'promotion_policy': {'require_calibration': {'enabled': 0}}}, {}),
  {},
  ('ok', [])),
 ('ready_cvar_calibration',
  'readiness',
  ({'cvars': ['junk',
              {'name': 'c'},
              {'governance': None},
              {'governance': {'require_calibration': 1}}]},
   {}),
  {},
  ('ok',
   [{'code': 'calibration_evidence_unsupported',
     'message': 'This module requires calibration certificates, but the current measurement bundle '
                'and tvl-ci-gate contract cannot validate them.'}])),
 ('ready_cvar_no_calibration',
  'readiness',
  ({'cvars': [{'governance': {'require_calibration': False}}]}, {}),
  {},
  ('ok', [])),
 ('ready_module_mismatch',
  'readiness',
  ({'tvl': {'module': 'a'}}, {'module_id': 'b'}),
  {},
  ('ok',
   [{'code': 'measurement_module_mismatch',
     'message': 'Measurement targets module b but the gate uses module a.'}])),
 ('ready_module_match',
  'readiness',
  ({'tvl': {'module': 'a'}}, {'module_id': 'a'}),
  {},
  ('ok', [])),
 ('ready_module_only_measured', 'readiness', ({'tvl': None}, {'module_id': 'b'}), {}, ('ok', [])),
 ('ready_module_only_expected',
  'readiness',
  ({'tvl': {'module': 'a'}}, {'module_id': ''}),
  {},
  ('ok', [])),
 ('ready_full',
  'readiness',
  ({'tvl': {'module': 'm'},
    'promotion_policy': {'require_calibration': {'enabled': True},
                         'chance_constraints': ['junk',
                                                {'threshold': 1},
                                                {'name': ''},
                                                {'name': 'ok'},
                                                {'name': 'missing'},
                                                {'name': 'partial'},
                                                {'name': 'notdict'}]},
    'cvars': [{'governance': {'require_calibration': True}}],
    'objectives': ['junk',
                   {'direction': 'x'},
                   {'name': ''},
                   {'name': 'samples'},
                   {'name': 'stats'},
                   {'name': 'partial'},
                   {'name': 'empty_samples'},
                   {'name': 'absent'},
                   {'name': 'notdict'}]},
   {'module_id': 'other',
    'objective_values': {'samples': {'samples': [1]},
                         'stats': {'mean': 0, 'std': 0, 'n': 0},
                         'partial': {'mean': 1, 'std': 1},
                         'empty_samples': {'samples': []},
                         'notdict': [1]},
    'chance_outcomes': {'ok': {'violations': 0, 'trials': 0},
                        'partial': {'violations': 1},
                        'notdict': 3}}),
  {},
  ('ok',
   [{'code': 'calibration_evidence_unsupported',
     'message': 'This module requires calibration certificates, but the current measurement bundle '
                'and tvl-ci-gate contract cannot validate them.'},
    {'code': 'measurement_module_mismatch',
     'message': 'Measurement targets module other but the gate uses module m.'},
    {'objective': 'partial',
     'code': 'missing_statistical_evidence',
     'message': 'Promotion gate requires objective_values.partial to provide samples or '
                'mean/std/n.'},
    {'objective': 'empty_samples',
     'code': 'missing_statistical_evidence',
     'message': 'Promotion gate requires objective_values.empty_samples to provide samples or '
                'mean/std/n.'},
    {'objective': 'absent',
     'code': 'missing_statistical_evidence',
     'message': 'Promotion gate requires objective_values.absent to provide samples or '
                'mean/std/n.'},
    {'objective': 'notdict',
     'code': 'missing_statistical_evidence',
     'message': 'Promotion gate requires objective_values.notdict to provide samples or '
                'mean/std/n.'},
    {'constraint': 'missing',
     'code': 'missing_chance_counts',
     'message': "Promotion gate requires chance_outcomes.missing to provide 'violations' and "
                "'trials'."},
    {'constraint': 'partial',
     'code': 'missing_chance_counts',
     'message': "Promotion gate requires chance_outcomes.partial to provide 'violations' and "
                "'trials'."},
    {'constraint': 'notdict',
     'code': 'missing_chance_counts',
     'message': "Promotion gate requires chance_outcomes.notdict to provide 'violations' and "
                "'trials'."}])),
 ('ready_none_sections',
  'readiness',
  ({'promotion_policy': None, 'objectives': None, 'cvars': None},
   {'objective_values': None, 'chance_outcomes': None}),
  {},
  ('ok', [])),
 ('ready_require_calibration_not_mapping',
  'readiness',
  ({'promotion_policy': {'require_calibration': [1]}}, {}),
  {},
  ('raises', 'AttributeError', "'list' object has no attribute 'get'")),
 ('ready_governance_not_mapping',
  'readiness',
  ({'cvars': [{'governance': [1]}]}, {}),
  {},
  ('raises', 'AttributeError', "'list' object has no attribute 'get'"))]


@pytest.mark.parametrize("case_id,fn,args,kwargs,expected", CASES, ids=[c[0] for c in CASES])
def test_pinned_case(case_id, fn, args, kwargs, expected):
    func = FUNCS[fn]
    args = copy.deepcopy(args)
    kwargs = copy.deepcopy(kwargs)
    if expected[0] == "raises":
        with pytest.raises(Exception) as info:
            func(*args, **kwargs)
        assert type(info.value).__name__ == expected[1]
        assert str(info.value) == expected[2]
    else:
        assert normalize(func(*args, **kwargs)) == expected[1]


def test_chance_without_statistical_runtime(monkeypatch):
    monkeypatch.setattr(measurement, "SCIPY_AVAILABLE", False)
    module = {"promotion_policy": {"chance_constraints": [{"name": "s"}]}}
    assert _evaluate_chance(module, {}) == [
        {
            "code": "missing_statistical_runtime",
            "message": (
                "scipy is required to evaluate chance constraints from violation counts. "
                "Install the runtime dependencies before using this command."
            ),
        }
    ]
    # No named constraint -> no runtime requirement, empty result.
    assert _evaluate_chance({"promotion_policy": {"chance_constraints": [{"x": 1}]}}, {}) == []


def test_chance_forwards_arguments_and_default_reason(monkeypatch):
    calls = []

    class _Result:
        def __init__(self, verdict, reason):
            self.verdict = verdict
            self.reason = reason

    results = iter([_Result("fail", ""), _Result("pass", "ignored"), _Result("inconclusive", "why")])

    def fake(**kwargs):
        calls.append(kwargs)
        return next(results)

    monkeypatch.setattr(measurement, "evaluate_chance_constraint", fake)
    module = {"promotion_policy": {"chance_constraints": [
        {"name": "a"},
        {"name": "b", "threshold": 0.3, "confidence": 0.8},
        {"name": "c", "threshold": None},
    ]}}
    outcomes = {"chance_outcomes": {"a": {"v": 1}, "b": {"v": 2}, "c": {"v": 3}}}
    assert _evaluate_chance(module, outcomes) == [
        {"constraint": "a", "code": "chance_violation", "message": "Chance constraint failed"},
        {"constraint": "c", "code": "chance_violation", "message": "why"},
    ]
    assert calls == [
        {"name": "a", "outcome": {"v": 1}, "threshold": 0.0, "confidence": 0.95},
        {"name": "b", "outcome": {"v": 2}, "threshold": 0.3, "confidence": 0.8},
        {"name": "c", "outcome": {"v": 3}, "threshold": None, "confidence": 0.95},
    ]
