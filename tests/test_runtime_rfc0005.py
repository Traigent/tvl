"""RFC 0005: breach persistence and census aggregates (TVL 1.5 draft)."""
from __future__ import annotations

import copy
import itertools
import json
from fractions import Fraction
from pathlib import Path

import pytest

from tvl.canonical import RuntimeClosedError, canonical_json_digest
from tvl.lints import lint_module, lint_pack
from tvl.runtime import compile_runtime_document, compose_runtime_documents
from tvl.runtime_aggregate import (
    AggregateError,
    aggregate_verdict,
    persistence_decisions,
    persistence_result,
    persistence_slots,
    units_commitment_v1,
    units_commitment_v2,
    validate_report_v2,
)
from tvl.runtime_conformance import _build_synthetic_tokens_for_docs
from tvl.runtime_projection import validate_projected_contract
from tvl.schema import runtime_contract_validator, runtime_local_validator, validator
from tvl.yaml_safe import safe_load

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / 'conformance/cases/runtime'
NEW_CODES = {'runtime_persistence_out_of_range', 'runtime_invalid_persistence',
             'runtime_aggregate_bound_out_of_range', 'runtime_report_numeric'}
DIGEST = 'a' * 64


def case(path):
    return safe_load((CASES / path).read_text())


def persist_module(k=3, n=4):
    d = copy.deepcopy(case('lints/persist-k1-n1-valid.yml')['module'])
    d['responses'][0]['rules'][0]['persist'] = {'breached_in': k, 'of_last': n}
    return d


def agg_module():
    return copy.deepcopy(case('lints/aggregate-sum-mean-valid.yml')['module'])


def tokens(*docs):
    entries = _build_synthetic_tokens_for_docs(docs)
    for i, entry in enumerate(entries):
        entry['hosted'] = f'ref_{i}'
    return {'format': 'tvl-token-map/1', 'tokens': entries}


def codes(doc):
    return {i['code'] for i in (lint_pack(doc) if 'pack' in doc else lint_module(doc))}


def errors(doc):
    return [i for i in (lint_pack(doc) if 'pack' in doc else lint_module(doc)) if i['severity'] == 'error']


# --------------------------------------------------------------------------- k-of-n truth table
def brute_force(k, slots):
    """Definition 14.2: quantify over every MET/BREACHED completion of the UNKNOWN slots."""
    unknown = [i for i, s in enumerate(slots) if s == 'UNKNOWN']
    counts = set()
    for fill in itertools.product(('MET', 'BREACHED'), repeat=len(unknown)):
        h = list(slots)
        for i, v in zip(unknown, fill):
            h[i] = v
        counts.add(sum(v == 'BREACHED' for v in h))
    if all(c >= k for c in counts):
        return 'BREACHED'
    if all(c < k for c in counts):
        return 'MET'
    return 'UNKNOWN'


@pytest.mark.parametrize('n', [1, 2, 3, 4])
def test_truth_table_matches_completion_semantics_for_every_k_and_history(n):
    for k in range(1, n + 1):
        for slots in itertools.product(('MET', 'BREACHED', 'UNKNOWN'), repeat=n):
            result, reason = persistence_result(k, n, list(slots))
            assert result == brute_force(k, slots), (k, slots)
            breached, unknown = slots.count('BREACHED'), slots.count('UNKNOWN')
            expected = 'BREACHED' if breached >= k else 'MET' if breached + unknown < k else 'UNKNOWN'
            assert result == expected
            assert (reason == 'inconclusive') == (result == 'UNKNOWN')


@pytest.mark.parametrize('slots,expected', [('BBU', 'BREACHED'), ('MMU', 'MET'), ('BMU', 'UNKNOWN')])
def test_rfc_worked_example_k2_n3(slots, expected):
    names = {'B': 'BREACHED', 'M': 'MET', 'U': 'UNKNOWN'}
    assert persistence_result(2, 3, [names[c] for c in slots])[0] == expected


@pytest.mark.parametrize('k,n', [(0, 3), (4, 3), (1, 169), (-1, 3), (True, 3), (1, 0)])
def test_reference_relation_rejects_out_of_range_persistence(k, n):
    with pytest.raises(AggregateError):
        persistence_result(k, n, ['MET'] * (n if type(n) is int and n > 0 else 1))


@pytest.mark.parametrize('k,n,accepted', [(0, 3, False), (4, 3, False), (1, 169, False), (1, 1, True), (3, 3, True),
                                          (168, 168, True), (1, 168, True), (169, 169, False)])
def test_lint_range_k_and_n(k, n, accepted):
    found = codes(persist_module(k, n))
    assert ('runtime_persistence_out_of_range' in found) is (not accepted)


def test_non_integer_coordinates_are_not_range_errors_and_schema_rejects_them():
    d = persist_module()
    d['responses'][0]['rules'][0]['persist']['of_last'] = '4'
    assert 'runtime_invalid_profile' in codes(d)
    assert list(validator().iter_errors(d))
    d = persist_module()
    d['responses'][0]['rules'][0]['persist']['extra'] = 1
    assert list(validator().iter_errors(d))


def test_fewer_than_n_windows_give_unknown_placeholder_slots():
    identity = {'contract_digest': 'c' * 64, 'monitor_revision': 'r1'}
    slots = persistence_slots(4, 1, [{'index': 0, 'verdict': 'BREACHED'}, {'index': 1, 'verdict': 'BREACHED'}], identity)
    assert [s['verdict'] for s in slots] == ['UNKNOWN', 'UNKNOWN', 'BREACHED', 'BREACHED']
    assert [s.get('reason') for s in slots[:2]] == ['persistence_history_gap'] * 2
    # k=3 cannot be decided yet: B=2, U=2 -> UNKNOWN; k=2 is already definite.
    assert persistence_result(3, 4, [s['verdict'] for s in slots])[0] == 'UNKNOWN'
    assert persistence_result(2, 4, [s['verdict'] for s in slots])[0] == 'BREACHED'


def test_older_decided_windows_never_fill_a_gap_and_other_identities_are_placeholders():
    identity = {'contract_digest': 'c' * 64, 'monitor_revision': 'r1'}
    windows = [{'index': 0, 'verdict': 'BREACHED'}, {'index': 1, 'verdict': 'BREACHED'}, {'index': 4, 'verdict': 'MET'}]
    slots = persistence_slots(3, 4, windows, identity)
    assert [s['verdict'] for s in slots] == ['UNKNOWN', 'UNKNOWN', 'MET']
    other = [dict(w, contract_digest='d' * 64) for w in windows]
    assert all(s['reason'] == 'persistence_history_gap' for s in persistence_slots(3, 1, other, identity)[1:])


def test_event_ledger_occurrence_zero_reconsideration_and_replay():
    identity = {'contract_digest': 'c' * 64, 'monitor_revision': 'r1'}
    windows = [{'index': 0, 'verdict': 'UNKNOWN'}, {'index': 1, 'verdict': 'MET'},
               {'index': 2, 'verdict': 'BREACHED'}, {'index': 3, 'verdict': 'BREACHED'}]
    events = [{'id': 'e1', 'window': 2, 'event': 'episode_continued'},
              {'id': 'e1r', 'window': 2, 'event': 'episode_continued', 'replay_of': 'e1'},
              {'id': 'e2', 'window': 3, 'event': 'episode_continued'},
              {'id': 'e2r', 'window': 3, 'event': 'episode_continued', 'replay_of': 'e2'}]
    out = persistence_decisions({'breached_in': 2, 'of_last': 3}, 'episode_continued', windows, events, identity)
    assert [(d['decision'], d['delivered'], d['replay']) for d in out] == [
        ('withheld', False, False), ('withheld', False, True), ('qualified', True, False), ('qualified', False, True)]
    assert {d['occurrence'] for d in out} == {0}


def test_events_exist_only_at_breached_windows_and_guards_follow_strong_kleene():
    identity = {'contract_digest': 'c' * 64, 'monitor_revision': 'r1'}
    windows = [{'index': i, 'verdict': v} for i, v in enumerate(['BREACHED', 'BREACHED', 'MET'])]
    with pytest.raises(AggregateError):  # BBM satisfies 2-of-3 but its MET window emits no breach event
        persistence_decisions({'breached_in': 2, 'of_last': 3}, 'episode_continued', windows,
                              [{'id': 'e', 'window': 2, 'event': 'episode_continued'}], identity)
    windows[2]['verdict'] = 'BREACHED'
    for guards, notified in [({'only_while': [None]}, True), ({'unless': [None]}, True), ({'only_while': [False]}, False),
                             ({'unless': [True]}, False), ({'only_while': [True], 'unless': [False]}, True)]:
        event = {'id': 'e', 'window': 2, 'event': 'episode_continued', **guards}
        out = persistence_decisions({'breached_in': 2, 'of_last': 3}, 'episode_continued', windows, [event], identity)
        assert out[0]['decision'] == 'qualified' and out[0]['notified'] is notified


# --------------------------------------------------------------------------- census aggregates
WINDOW = {'start_ms': 0, 'end_ms': 86_400_000, 'grace_ms': 1_800_000}
DUE = WINDOW['end_ms'] + WINDOW['grace_ms']


def verdict(op, metric, bound, values, at=DUE, **extra):
    units = [{'key': f'u{i}', 'membership': True, 'status': 'completed', 'value': v} for i, v in enumerate(values)]
    spec = {'op': op, 'metric': metric, 'bound': bound, 'window': WINDOW, 'evaluated_at_ms': at, 'units': units, **extra}
    return aggregate_verdict(spec)


@pytest.mark.parametrize('values,bound,expected', [
    (['20', '30'], {'lte': 50}, 'MET'),
    (['20', '30.01'], {'lte': 50}, 'BREACHED'),
    (['20', '29.99'], {'lte': 50}, 'MET'),
    (['0.1', '0.2'], {'lte': 0.3}, 'MET'),
    (['0.1', '0.2'], {'gte': 0.3}, 'MET'),
    (['0.1', '0.2'], {'gte': 0.31}, 'BREACHED'),
])
def test_sum_is_exact_with_equality_meeting_either_bound(values, bound, expected):
    assert verdict('sum', 'cost_usd', bound, values)['verdict'] == expected


def test_mean_compares_the_exact_sum_with_count_times_bound_never_a_rounded_quotient():
    # 1/3 rounds to 0.3333333333333333 in binary floating point, so a float comparison passes both of these.
    third = ['0', '0', '1']
    assert verdict('mean', 'score', {'gte': 0.333333333333333}, third)['verdict'] == 'MET'
    assert verdict('mean', 'score', {'lte': 0.3333333333333333}, third)['verdict'] == 'BREACHED'
    assert verdict('mean', 'score', {'gte': 0.3333333333333334}, third)['verdict'] == 'BREACHED'
    assert 1 / 3 <= 0.3333333333333333  # the rounded comparison the relation must not use
    out = verdict('mean', 'score', {'gte': 0.8}, ['0.7', '0.9'])
    assert out == {'verdict': 'MET', 'sum': '1.6', 'member_count': 2}


def test_mean_equality_meets_either_bound_by_integer_arithmetic():
    values = ['1', '2', '4', '0']  # sum 7, count 4: mean 7/4 meets 1.75 exactly in both directions
    assert verdict('mean', 'cost_usd', {'lte': '1.75'}, values)['verdict'] == 'MET'
    assert verdict('mean', 'cost_usd', {'gte': '1.75'}, values)['verdict'] == 'MET'
    assert verdict('mean', 'cost_usd', {'lte': '1.74'}, values)['verdict'] == 'BREACHED'
    assert verdict('mean', 'cost_usd', {'gte': '1.76'}, values)['verdict'] == 'BREACHED'


def decimal_milli(milli):
    return f'{milli // 1000}.{milli % 1000:03d}'


def test_mean_matches_a_fraction_oracle_over_a_grid():
    for count in (1, 2, 3, 7):
        for total_milli in range(0, 3 * count * 1000 + 1, 250):
            values = ['0'] * (count - 1) + [decimal_milli(total_milli)]
            for bound_milli in range(0, 3000, 125):
                for direction in ('lte', 'gte'):
                    out = verdict('mean', 'cost_usd', {direction: decimal_milli(bound_milli)}, values)
                    mean, bound = Fraction(total_milli, 1000 * count), Fraction(bound_milli, 1000)
                    held = mean <= bound if direction == 'lte' else mean >= bound
                    assert out['verdict'] == ('MET' if held else 'BREACHED'), (count, total_milli, bound_milli, direction)


def test_empty_population_is_insufficient_never_a_zero_sum():
    assert verdict('sum', 'cost_usd', {'lte': 50}, []) == {'verdict': 'UNKNOWN', 'reason': 'insufficient'}
    assert verdict('sum', 'cost_usd', {'gte': 0}, []) == {'verdict': 'UNKNOWN', 'reason': 'insufficient'}


def test_before_due_is_pending_and_one_millisecond_later_it_decides():
    assert verdict('sum', 'cost_usd', {'lte': 50}, ['1'], at=DUE - 1) == {'verdict': 'UNKNOWN', 'reason': 'aggregate_pending'}
    assert verdict('sum', 'cost_usd', {'lte': 50}, ['1'], at=DUE)['verdict'] == 'MET'


@pytest.mark.parametrize('bad', [None, 'NaN', 'Infinity', '-1', '1e3', '', 'abc', True, 1.5, '0.7.1'])
def test_missing_or_invalid_cost_values_make_the_window_incomplete(bad):
    units = [{'key': 'u1', 'membership': True, 'status': 'completed', 'value': '60'},
             {'key': 'u2', 'membership': True, 'status': 'failed', 'value': bad}]
    spec = {'op': 'sum', 'metric': 'cost_usd', 'bound': {'lte': 50}, 'window': WINDOW, 'evaluated_at_ms': DUE, 'units': units}
    assert aggregate_verdict(spec) == {'verdict': 'UNKNOWN', 'reason': 'incomplete'}  # not BREACHED, not zero-filled


@pytest.mark.parametrize('score', ['1.01', '-0.1', '2', 'NaN', None])
def test_scores_outside_unit_interval_are_invalid(score):
    assert verdict('mean', 'score', {'gte': 0.5}, ['0.9', score]) == {'verdict': 'UNKNOWN', 'reason': 'incomplete'}


def test_incomplete_beats_insufficient_and_unknown_membership_is_unresolved():
    units = [{'key': 'u1', 'membership': 'unknown', 'status': 'completed', 'value': None}]
    spec = {'op': 'sum', 'metric': 'cost_usd', 'bound': {'lte': 5}, 'window': WINDOW, 'evaluated_at_ms': DUE, 'units': units}
    assert aggregate_verdict(spec) == {'verdict': 'UNKNOWN', 'reason': 'incomplete'}


def test_late_arrivals_do_not_change_a_finalized_verdict_and_replays_count_once():
    base = [{'key': 'u1', 'membership': True, 'status': 'completed', 'value': '10'}]
    spec = {'op': 'sum', 'metric': 'cost_usd', 'bound': {'lte': 50}, 'window': WINDOW, 'evaluated_at_ms': DUE + 10 ** 9}
    assert aggregate_verdict({**spec, 'units': base})['sum'] == '10'
    late = base + [{'key': 'u2', 'membership': True, 'status': 'completed', 'value': '999', 'arrived_ms': DUE + 1}]
    assert aggregate_verdict({**spec, 'units': late}) == aggregate_verdict({**spec, 'units': base})
    assert aggregate_verdict({**spec, 'units': base * 3})['member_count'] == 1


def test_exact_arithmetic_beyond_float_precision_and_precision_limit():
    big = '9007199254740993'  # 2**53 + 1: not representable as a float
    assert verdict('sum', 'cost_usd', {'lte': '9007199254740993'}, [big])['verdict'] == 'MET'
    assert verdict('sum', 'cost_usd', {'lte': '9007199254740992'}, [big])['verdict'] == 'BREACHED'
    assert verdict('sum', 'cost_usd', {'lte': 1}, ['0.123456789'], precision_scale=6) == {
        'verdict': 'UNKNOWN', 'reason': 'aggregate_precision_limit'}


def test_mean_score_bound_above_one_is_refused_by_the_relation_and_the_lint():
    with pytest.raises(AggregateError):
        verdict('mean', 'score', {'gte': 2}, ['1'])
    assert verdict('sum', 'score', {'lte': 2}, ['1', '1', '1'])['verdict'] == 'BREACHED'  # a score sum may exceed 1


# --------------------------------------------------------------------------- authored lints and version gating
def test_aggregate_lints_and_valid_document_has_no_error():
    assert not errors(agg_module())
    d = agg_module(); d['requirements'][0]['bound'] = {'lte': -0.01}
    assert 'runtime_aggregate_bound_out_of_range' in codes(d)
    d = agg_module(); d['requirements'][0]['bound'] = {'lte': 1, 'gte': 0}
    assert 'runtime_invalid_profile' in codes(d)
    d = agg_module(); d['requirements'][0]['bound'] = {}
    assert 'runtime_invalid_profile' in codes(d)
    d = agg_module(); d['requirements'][0]['aggregate']['source_digest'] = 'NOT-A-DIGEST'
    assert 'runtime_invalid_profile' in codes(d)


@pytest.mark.parametrize('field,value', [('window', None), ('episode', None)])
def test_aggregate_monitor_requires_window_and_episode(field, value):
    d = agg_module(); del d['monitors'][0][field]
    assert 'runtime_invalid_profile' in codes(d)


@pytest.mark.parametrize('forbidden', [('decision', 'min_samples', 10), ('decision', 'max_unresolved_fraction', 0.1),
                                       ('decision', 'confidence', 0.95), ('decision', 'threshold_factor', 2),
                                       ('decision', 'model', 'iid_bernoulli_within_window_v1'),
                                       ('top', 'limits', {'max_active_obligations': 1}), ('top', 'single_producer', True),
                                       ('top', 'profile', 'backend_v1'),
                                       ('evidence', 'sampling', 'unverified')])
def test_aggregate_monitor_forbidden_fields(forbidden):
    group, key, value = forbidden
    d = agg_module(); mon = d['monitors'][0]
    (mon if group == 'top' else mon[group])[key] = value
    assert 'runtime_invalid_profile' in codes(d) or 'runtime_legacy_profile_override' in codes(d)


def test_aggregate_requires_customer_side_runtime_exact_aggregate_and_not_other_kinds():
    d = agg_module(); d['monitors'][0]['evidence']['source'] = 'backend_trace_metadata'
    assert 'runtime_invalid_profile' in codes(d)
    d = agg_module(); d['monitors'][0]['decision']['method'] = 'exact_count_v1'
    assert 'runtime_invalid_profile' in codes(d)
    d = persist_module(); d['monitors'][0]['decision'] = {'method': 'exact_aggregate_v1'}
    assert 'runtime_invalid_profile' in codes(d)


def test_aggregate_primary_emits_episode_events_but_no_unit_violation():
    d = agg_module(); rule = d['responses'][0]['rules'][0]
    rule['trigger'] = {'monitor': 'daily_spend_prod', 'event': 'unit_violation'}
    assert 'runtime_ref_kind_mismatch' in codes(d)
    rule['trigger'] = {'monitor': 'daily_spend_prod', 'event': 'episode_continued'}
    assert not errors(d)


@pytest.mark.parametrize('version,expected', [(None, 'runtime_version_required'), ('1.3', 'declared_version_below_constructs'),
                                              ('1.4', 'declared_version_below_constructs'), ('1.5', None)])
@pytest.mark.parametrize('build', ['persist', 'aggregate'])
def test_every_new_key_requires_version_1_5(build, version, expected):
    d = persist_module() if build == 'persist' else agg_module()
    if version is None:
        d.pop('tvl_version')
    else:
        d['tvl_version'] = version
    found = codes(d)
    assert (expected in found) if expected else not ({'runtime_version_required', 'declared_version_below_constructs'} & found)


def test_persistence_source_and_action_restrictions():
    d = persist_module(); d['responses'][0]['rules'][0]['do'] = 'optimize'
    assert 'runtime_notify_only' in codes(d)
    d = persist_module(); d['responses'][0]['rules'][0]['trigger']['monitor'] = 'monitor_gate'
    assert codes(d) & {'runtime_ref_kind_mismatch', 'runtime_invalid_persistence'}
    d = persist_module(); d['responses'][0]['rules'][0]['trigger']['event'] = 'unit_violation'
    assert 'runtime_invalid_persistence' in codes(d)
    for coordinate in ({'repeat_after_hours': 6}, {'max_repeats': 2}):
        d = persist_module(); d['responses'][0]['rules'][0].update(coordinate)
        assert 'runtime_invalid_persistence' in codes(d)


# --------------------------------------------------------------------------- 1.4 documents are unchanged
def test_every_pre_15_case_document_has_no_rfc0005_diagnostic():
    checked = 0
    for path in sorted(CASES.rglob('*.yml')):
        doc = safe_load(path.read_text())
        for key in ('module', 'pack', 'base', 'overlay'):
            d = doc.get(key)
            if isinstance(d, dict) and d.get('tvl_version') in {'1.3', '1.4'} and not path.name.startswith(
                    ('persist-', 'aggregate-', 'version-14-')):
                assert not (codes(d) & NEW_CODES), path
                checked += 1
    assert checked > 100


def test_legacy_artifacts_keep_frozen_bytes_and_format_selection():
    frozen = case('projection/deploy-mode-closed.yml')
    module = frozen['module']
    token_map = {'format': 'tvl-token-map/1', 'tokens': frozen['input']['token_map']}
    for version, fmt, tvl_version in (('1.3', 'tvl-runtime-contract/1', '1.3'), ('1.4', 'tvl-runtime-contract/1', '1.3'),
                                      ('1.5', 'tvl-runtime-contract/1', '1.3')):
        d = copy.deepcopy(module); d['tvl_version'] = version
        contract, local, _ = compile_runtime_document(d, token_map_doc=token_map)
        assert contract['format'] == fmt and contract['tvl_version'] == tvl_version
        assert local['format'] == 'tvl-runtime-local/1'
        assert canonical_json_digest(contract['declarations']) is not None
    reactive = case('projection/outcome-and-guard-closed-enums.yml')['module']
    contract, local, _ = compile_runtime_document(reactive, token_map_doc=tokens(reactive))
    assert (contract['format'], contract['tvl_version'], local['format']) == ('tvl-runtime-contract/2', '1.4', 'tvl-runtime-local/2')


# --------------------------------------------------------------------------- compile, projection, schemas
def test_persistence_compiles_to_format_3_and_exports_only_authored_integers():
    d = persist_module(3, 4)
    contract, local, _ = compile_runtime_document(d, token_map_doc=tokens(d))
    assert (contract['format'], contract['tvl_version'], local['format']) == ('tvl-runtime-contract/3', '1.5', 'tvl-runtime-local/3')
    assert not list(runtime_contract_validator(contract['format']).iter_errors(contract))
    assert not list(runtime_local_validator(local['format']).iter_errors(local))
    for artifact in (contract, local):
        assert artifact['declarations']['responses'][0]['rules'][0]['persist'] == {'breached_in': 3, 'of_last': 4}
    text = json.dumps(contract)
    assert 'persistence_history_gap' not in text and 'inconclusive' not in text


def test_aggregate_compiles_with_closed_numeric_summaries_only():
    d = agg_module()
    contract, local, _ = compile_runtime_document(d, token_map_doc=tokens(d))
    assert contract['format'] == 'tvl-runtime-contract/3' and contract['tvl_version'] == '1.5'
    req = contract['declarations']['requirements'][0]
    assert req['aggregate'] == {'op': 'sum', 'metric': 'cost_usd', 'source_digest': DIGEST}
    assert req['bound'] == {'lte': '50'}
    monitor = contract['declarations']['monitors'][0]
    assert monitor['decision'] == {'method': 'exact_aggregate_v1'}
    assert set(monitor['evidence']) == {'source', 'deployment_environment', 'attribution', 'resolution'}
    assert not list(runtime_local_validator(local['format']).iter_errors(local))


def test_bound_tightening_changes_the_contract_digest():
    a, b = agg_module(), agg_module()
    b['requirements'][0]['bound'] = {'lte': 49.99}
    ca, _, _ = compile_runtime_document(a, token_map_doc=tokens(a))
    cb, _, _ = compile_runtime_document(b, token_map_doc=tokens(b))
    assert canonical_json_digest(ca) != canonical_json_digest(cb)


def test_format_tags_are_closed_and_checked_against_constructs():
    d = persist_module()
    contract, local, _ = compile_runtime_document(d, token_map_doc=tokens(d))
    for tag in ('tvl-runtime-contract/1', 'tvl-runtime-contract/2'):
        retagged = dict(contract, format=tag)
        assert list(runtime_contract_validator(tag).iter_errors(retagged))  # persist is refused by the frozen formats
    with pytest.raises(RuntimeClosedError):
        runtime_contract_validator('tvl-runtime-contract/4')
    with pytest.raises(RuntimeClosedError):
        runtime_local_validator('tvl-runtime-local/4')
    plain = case('projection/deploy-mode-closed.yml')
    base_contract, base_local, _ = compile_runtime_document(
        plain['module'], token_map_doc={'format': 'tvl-token-map/1', 'tokens': plain['input']['token_map']})
    assert list(runtime_contract_validator('tvl-runtime-contract/3').iter_errors(
        dict(base_contract, format='tvl-runtime-contract/3', tvl_version='1.5')))
    assert list(runtime_local_validator('tvl-runtime-local/3').iter_errors(
        dict(base_local, format='tvl-runtime-local/3', tvl_version='1.5')))
    for artifact, validator_for in ((contract, runtime_contract_validator), (local, runtime_local_validator)):
        bad = copy.deepcopy(artifact)
        bad['declarations']['responses'][0]['rules'][0]['persist']['of_last'] = 169
        assert list(validator_for(bad['format']).iter_errors(bad))
        bad = copy.deepcopy(artifact)
        bad['declarations']['responses'][0]['rules'][0]['persist']['extra'] = 1
        assert list(validator_for(bad['format']).iter_errors(bad))


def test_hosted_persist_must_equal_the_authored_integers():
    d = persist_module(); tm = tokens(d)
    contract, _, _ = compile_runtime_document(d, token_map_doc=tm)
    contract['declarations']['responses'][0]['rules'][0]['persist']['breached_in'] = 2
    with pytest.raises(RuntimeClosedError) as exc:
        validate_projected_contract(contract, doc=d, used_tokens=tm['tokens'])
    assert exc.value.code == 'runtime_unsafe_egress'


def test_authored_schema_is_closed_for_new_records():
    assert not list(validator().iter_errors(agg_module()))
    d = agg_module(); d['requirements'][0]['bound']['eq'] = 1
    assert list(validator().iter_errors(d))
    d = agg_module(); d['requirements'][0]['aggregate']['extra'] = 1
    assert list(validator().iter_errors(d))
    d = agg_module(); d['requirements'][0]['bound'] = {'lte': 'fifty'}
    assert list(validator().iter_errors(d))


@pytest.mark.parametrize('name', ['tvl.schema.json', 'tvl-pack.schema.json', 'tvl-runtime-contract-v3.schema.json',
                                  'tvl-runtime-local-v3.schema.json'])
def test_editor_schema_copies_identical(name):
    source = (ROOT / 'spec/grammar' / name).read_bytes()
    for directory in ['editor_shared/vscode/schemas', 'vscode-tvl/schemas']:
        assert (ROOT / directory / name).read_bytes() == source


def test_frozen_schemas_keep_their_bytes():
    for name in ('tvl-runtime-contract.schema.json', 'tvl-runtime-local.schema.json',
                 'tvl-runtime-contract-v2.schema.json', 'tvl-runtime-local-v2.schema.json', 'tvl-runtime-report.schema.json'):
        text = (ROOT / 'spec/grammar' / name).read_text()
        assert '1.5' not in text and 'aggregate' not in text and 'persist' not in text, name


# --------------------------------------------------------------------------- composition
def aggregate_pair(direction='lte', low=40, high=80):
    base, overlay = agg_module(), agg_module()
    for d, value in ((base, high), (overlay, low)):
        d['requirements'] = [d['requirements'][0]]
        d['monitors'] = [d['monitors'][0]]
        d['responses'] = [{'name': 'repair', 'rules': []}]
        d['requirements'][0]['bound'] = {direction: value}
    return base, overlay


def test_overlay_may_only_tighten_an_aggregate_bound():
    base, overlay = aggregate_pair('lte', 40, 80)
    composed, _ = compose_runtime_documents(base, overlay, operation='overlay')
    assert composed['requirements'][0]['bound'] == {'lte': 40}
    with pytest.raises(RuntimeClosedError) as exc:
        compose_runtime_documents(overlay, base, operation='overlay')
    assert exc.value.code == 'runtime_overlay_weakens'
    base, overlay = aggregate_pair('gte', 0.9, 0.8)
    composed, _ = compose_runtime_documents(base, overlay, operation='overlay')
    assert composed['requirements'][0]['bound'] == {'gte': 0.9}
    with pytest.raises(RuntimeClosedError) as exc:
        compose_runtime_documents(overlay, base, operation='overlay')
    assert exc.value.code == 'runtime_overlay_weakens'


def test_meet_takes_minimum_lte_and_maximum_gte_in_either_order():
    for direction, low, high, expected in (('lte', 40, 80, 40), ('gte', 0.8, 0.9, 0.9)):
        a, b = aggregate_pair(direction, low, high)
        for x, y in ((a, b), (b, a)):
            composed, _ = compose_runtime_documents(x, y, operation='meet')
            assert composed['requirements'][0]['bound'] == {direction: expected}


@pytest.mark.parametrize('change', ['source', 'direction', 'op', 'metric'])
def test_other_aggregate_identity_changes_are_incompatible_replacements(change):
    base, overlay = aggregate_pair('lte', 40, 80)
    req = overlay['requirements'][0]
    if change == 'source':
        req['aggregate']['source_digest'] = 'b' * 64
    elif change == 'direction':
        req['bound'] = {'gte': 40}
    elif change == 'op':
        req['aggregate']['op'] = 'mean'
    else:
        req['aggregate']['metric'] = 'score'
        req['aggregate']['op'] = 'sum'
    with pytest.raises(RuntimeClosedError) as exc:
        compose_runtime_documents(base, overlay, operation='overlay')
    assert exc.value.code == 'runtime_incompatible_replacement'


@pytest.mark.parametrize('operation', ['overlay', 'meet'])
@pytest.mark.parametrize('change', ['k', 'n', 'removed', 'added'])
def test_persistence_presence_and_coordinates_are_immutable(operation, change):
    base, overlay = persist_module(3, 4), persist_module(3, 4)
    rule = overlay['responses'][0]['rules'][0]
    if change == 'k':
        rule['persist']['breached_in'] = 2
    elif change == 'n':
        rule['persist']['of_last'] = 5
    elif change == 'removed':
        del rule['persist']
    else:
        del base['responses'][0]['rules'][0]['persist']
    with pytest.raises(RuntimeClosedError) as exc:
        compose_runtime_documents(base, overlay, operation=operation)
    assert exc.value.code == 'runtime_incompatible_replacement'


def test_equal_persistence_composes_unchanged():
    composed, _ = compose_runtime_documents(persist_module(3, 4), persist_module(3, 4), operation='overlay')
    assert composed['responses'][0]['rules'][0]['persist'] == {'breached_in': 3, 'of_last': 4}


# --------------------------------------------------------------------------- report/2 and commitments
BINDING = {'contract_digest': 'c' * 64, 'monitor_ref': 'ref_monitor', 'monitor_revision': 'rev1',
           'source_digest': DIGEST, 'window_hours': 24, 'grace_ms': 1_800_000}


def valid_report():
    return copy.deepcopy(case('aggregate_report/aggregate-report-valid.yml')['input']['report'])


def refused(report):
    with pytest.raises(RuntimeClosedError) as exc:
        validate_report_v2(report, BINDING)
    return exc.value.code


def test_valid_report_is_accepted_and_every_binding_field_is_checked():
    validate_report_v2(valid_report(), BINDING)
    for key, value in (('contract_digest', 'd' * 64), ('monitor_ref', 'other'), ('monitor_revision', 'rev2'),
                       ('source_digest', 'b' * 64), ('window_start_ms', 1), ('window_end_ms', 86_400_001)):
        assert refused(dict(valid_report(), **{key: value})) == 'runtime_report_conservation', key


@pytest.mark.parametrize('field,delta', [('selected', 1), ('reported', 1), ('dropped', 1), ('member_count', 1),
                                         ('contribution_count', 1), ('unknown_membership', 1), ('unplaceable', 1),
                                         ('excluded', 1), ('missing_value', 1), ('invalid_value', 1)])
def test_each_count_identity_is_enforced(field, delta):
    report = valid_report(); report['counts'][field] += delta
    assert refused(report) == 'runtime_report_conservation'


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-1', '-0', '1e3', '12.50', '012', '', '1.', '.5', 'x'])
def test_malformed_noncanonical_or_negative_sums_are_numeric_refusals(value):
    assert refused(dict(valid_report(), sum=value)) == 'runtime_report_numeric'


def test_report_numeric_refusal_echoes_no_input():
    with pytest.raises(RuntimeClosedError) as exc:
        validate_report_v2(dict(valid_report(), sum='CANARY'), BINDING)
    assert 'CANARY' not in str(exc.value) and 'CANARY' not in exc.value.message


def test_complete_nonempty_report_needs_a_sum_and_the_shape_is_closed():
    report = valid_report(); del report['sum']
    assert refused(report) == 'runtime_report_numeric'
    report = valid_report(); report['counts'].update(missing_value=1, contribution_count=2)
    del report['sum']
    validate_report_v2(report, BINDING)  # incomplete evidence needs no sum
    assert refused(dict(valid_report(), mean='0.5')) == 'schema_error'
    assert refused(dict(valid_report(), format='tvl-runtime-report/1')) == 'schema_error'
    assert refused(dict(valid_report(), evidence_tier='verified')) == 'schema_error'


UNITS = case('aggregate_report/aggregate-keyed-commitment.yml')['input']['units']


def test_report2_commitment_is_keyed_deterministic_and_order_insensitive():
    report = valid_report()
    key = bytes(range(32))
    a = units_commitment_v2(key, report, UNITS)
    assert a == units_commitment_v2(key, report, list(reversed(UNITS))) == units_commitment_v2(key, report, UNITS + UNITS[:1])
    assert len(a) == 64 and a == a.lower()
    assert a != units_commitment_v2(bytes(32), report, UNITS)  # the secret keys the commitment
    assert a != units_commitment_v2(key, dict(report, source_digest='b' * 64), UNITS)  # window/source binding
    assert a != units_commitment_v2(key, dict(report, window_end_ms=report['window_end_ms'] + 1), UNITS)
    changed = copy.deepcopy(UNITS); changed[0]['value'] = '2.51'
    assert a != units_commitment_v2(key, report, changed)
    equivalent = copy.deepcopy(UNITS); equivalent[0]['value'] = '2.5'  # '2.50' and '2.5' share one canonical value
    assert a == units_commitment_v2(key, report, equivalent)
    with pytest.raises(AggregateError):
        units_commitment_v2(b'short', report, UNITS)


def test_report2_commitment_is_not_the_unkeyed_digest():
    import hashlib
    report = valid_report()
    payload = json.dumps({'units': UNITS}, sort_keys=True).encode()
    assert units_commitment_v2(bytes(32), report, UNITS) != hashlib.sha256(payload).hexdigest()


def test_report1_commitment_is_unchanged():
    import hashlib
    units = [{'unit_id': 'u2', 'class': 'vio'}, {'unit_id': 'u1', 'class': 'sat'}]
    listed = [{'unit_id': 'u1', 'class': 'sat'}, {'unit_id': 'u2', 'class': 'vio'}]
    assert units_commitment_v1(units) == hashlib.sha256(
        (json.dumps(listed, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode()).hexdigest()
    assert 'tvl-runtime-report/1' in (ROOT / 'spec/grammar/tvl-runtime-report.schema.json').read_text()
