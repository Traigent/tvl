"""RFC 0005: breach persistence and census aggregates (TVL 1.5 draft)."""
from __future__ import annotations

import copy
import hashlib
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
IDENTITY = {'contract_digest': 'c' * 64, 'monitor_revision': 'r1', 'agent': 'agent_1', 'environment': 'production',
            'schedule': 'daily_24h'}


def win(index, verdict, **override):
    """A finalized, available window recorded under the full persistence identity."""
    return {'index': index, 'verdict': verdict, 'available': True, **IDENTITY, **override}


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
    identity = IDENTITY
    slots = persistence_slots(4, 1, [win(0, 'BREACHED'), win(1, 'BREACHED')], identity)
    assert [s['verdict'] for s in slots] == ['UNKNOWN', 'UNKNOWN', 'BREACHED', 'BREACHED']
    assert [s.get('reason') for s in slots[:2]] == ['persistence_history_gap'] * 2
    # k=3 cannot be decided yet: B=2, U=2 -> UNKNOWN; k=2 is already definite.
    assert persistence_result(3, 4, [s['verdict'] for s in slots])[0] == 'UNKNOWN'
    assert persistence_result(2, 4, [s['verdict'] for s in slots])[0] == 'BREACHED'


def test_older_decided_windows_never_fill_a_gap_and_other_identities_are_placeholders():
    identity = IDENTITY
    windows = [win(0, 'BREACHED'), win(1, 'BREACHED'), win(4, 'MET')]
    slots = persistence_slots(3, 4, windows, identity)
    assert [s['verdict'] for s in slots] == ['UNKNOWN', 'UNKNOWN', 'MET']
    other = [dict(w, contract_digest='d' * 64) for w in windows]
    assert all(s['reason'] == 'persistence_history_gap' for s in persistence_slots(3, 1, other, identity)[1:])


def test_event_ledger_occurrence_zero_reconsideration_and_replay():
    identity = IDENTITY
    windows = [win(0, 'UNKNOWN'), win(1, 'MET'), win(2, 'BREACHED'), win(3, 'BREACHED')]
    events = [{'id': 'e1', 'window': 2, 'event': 'episode_continued'},
              {'id': 'e1r', 'window': 2, 'event': 'episode_continued', 'replay_of': 'e1'},
              {'id': 'e2', 'window': 3, 'event': 'episode_continued'},
              {'id': 'e2r', 'window': 3, 'event': 'episode_continued', 'replay_of': 'e2'}]
    out = persistence_decisions({'breached_in': 2, 'of_last': 3}, 'episode_continued', windows, events, identity)
    assert [(d['decision'], d['delivered'], d['replay']) for d in out] == [
        ('withheld', False, False), ('withheld', False, True), ('qualified', True, False), ('qualified', False, True)]
    assert {d['occurrence'] for d in out} == {0}


def test_events_exist_only_at_breached_windows_and_guards_follow_strong_kleene():
    identity = IDENTITY
    windows = [win(i, v) for i, v in enumerate(['BREACHED', 'BREACHED', 'MET'])]
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


COVERAGE = {'census': True, 'unit_histories_complete': True, 'producer_set_complete': True,
            'producer_sequences_contiguous': True, 'response_deadlines_covered': True, 'watermark_ms': DUE}


def spec_of(units, op='sum', metric='cost_usd', bound=None, at=DUE, **extra):
    return {'op': op, 'metric': metric, 'bound': bound or {'lte': 50}, 'window': WINDOW, 'evaluated_at_ms': at,
            'units': units, 'coverage': dict(COVERAGE), **extra}


def verdict(op, metric, bound, values, at=DUE, **extra):
    units = [{'key': f'u{i}', 'membership': True, 'status': 'completed', 'value': v} for i, v in enumerate(values)]
    return aggregate_verdict(spec_of(units, op, metric, bound, at, **extra))


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
    assert aggregate_verdict(spec_of(units)) == {'verdict': 'UNKNOWN', 'reason': 'incomplete'}  # not BREACHED, not zero-filled


@pytest.mark.parametrize('score', ['1.01', '-0.1', '2', 'NaN', None])
def test_scores_outside_unit_interval_are_invalid(score):
    assert verdict('mean', 'score', {'gte': 0.5}, ['0.9', score]) == {'verdict': 'UNKNOWN', 'reason': 'incomplete'}


def test_incomplete_beats_insufficient_and_unknown_membership_is_unresolved():
    units = [{'key': 'u1', 'membership': 'unknown', 'status': 'completed', 'value': None}]
    assert aggregate_verdict(spec_of(units, bound={'lte': 5})) == {'verdict': 'UNKNOWN', 'reason': 'incomplete'}


def test_late_unit_makes_the_census_incomplete_and_replays_count_once():
    base = [{'key': 'u1', 'membership': True, 'status': 'completed', 'value': '10'}]
    at = DUE + 10 ** 9
    assert aggregate_verdict(spec_of(base, at=at))['sum'] == '10'
    late = base + [{'key': 'u2', 'membership': True, 'status': 'completed', 'value': '999', 'arrived_ms': DUE + 1}]
    assert aggregate_verdict(spec_of(late, at=at)) == {'verdict': 'UNKNOWN', 'reason': 'incomplete'}  # never MET
    replay = base + [dict(base[0], value='10.0', arrived_ms=DUE + 1)]
    assert aggregate_verdict(spec_of(replay, at=at)) == aggregate_verdict(spec_of(base, at=at))
    assert aggregate_verdict(spec_of(base * 3, at=at))['member_count'] == 1


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


LEGACY_DECLARATIONS_DIGEST = '7b989e6ec6dfe582c7c7f790e4c2e426558237454f45dadce2d876b16e0f5311'
LEGACY_CONTRACT_DIGEST = '8aef83829a042975c1f4067bc2cbbad4a8d7789e29fd4a98d163b01c2b08632f'
LEGACY_LOCAL_DIGEST = 'c24867285f4e78d18e1f9039201e4781a2ad7fa9ad77dc0083b6edcb9575cbe1'
FROZEN_SCHEMA_SHA256 = {  # sha256 of the bytes at origin/main (5ba03c6)
    'tvl-runtime-contract.schema.json': 'ae5f4567fc39484226ef5b59c1ef2ddbb49f67e343809e8180f3c06aa34cb601',
    'tvl-runtime-local.schema.json': '7815f51455aa18fd6ca822489a51faaad545ce7184fdc9bb291fc615fbf09fe2',
    'tvl-runtime-contract-v2.schema.json': '2f9119d63fe0334ed671156231e1c85dacc543b29802352f89e5df8f52642a45',
    'tvl-runtime-local-v2.schema.json': '9e69577f6d77bfe6c6862864844e6c63f20f95b7761d23c574d7937fda52aa40',
    'tvl-runtime-report.schema.json': 'a4928b05272aadc2f31cbac4f741a31ba136ae5896552baffb2ce9d9b4b992ca',
}


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
        # Pinned from origin/main (5ba03c6), computed there, not from this tree's code.
        assert canonical_json_digest(contract['declarations']) == LEGACY_DECLARATIONS_DIGEST
        assert canonical_json_digest(contract) == LEGACY_CONTRACT_DIGEST
        assert canonical_json_digest(local) == LEGACY_LOCAL_DIGEST
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
    for name, pinned in FROZEN_SCHEMA_SHA256.items():
        assert hashlib.sha256((ROOT / 'spec/grammar' / name).read_bytes()).hexdigest() == pinned, name


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


# --------------------------------------------------------------------------- review fixes D1-D12
@pytest.mark.parametrize('coverage', [
    'absent', None, {**COVERAGE, 'census': False}, {**COVERAGE, 'unit_histories_complete': 1},
    {**COVERAGE, 'watermark_ms': DUE - 1}, {**COVERAGE, 'watermark_ms': True}])
def test_d1_missing_or_unattested_coverage_is_incomplete_never_complete_by_default(coverage):
    spec = spec_of([{'key': 'u1', 'membership': True, 'status': 'completed', 'value': '10'}])
    if coverage == 'absent':
        del spec['coverage']
    else:
        spec['coverage'] = coverage
    assert aggregate_verdict(spec) == {'verdict': 'UNKNOWN', 'reason': 'incomplete'}


def test_d1_late_unit_is_never_dropped_into_met_even_when_its_value_is_invalid():
    for late in ({'value': '999'}, {'value': None}, {'value': 'NaN'}):
        units = [{'key': 'u1', 'membership': True, 'status': 'completed', 'value': '10'},
                 {'key': 'u2', 'membership': True, 'status': 'completed', 'arrived_ms': DUE + 1, **late}]
        assert aggregate_verdict(spec_of(units)) == {'verdict': 'UNKNOWN', 'reason': 'incomplete'}
    on_time = [{'key': 'u1', 'membership': True, 'status': 'completed', 'value': '10', 'arrived_ms': DUE}]
    assert aggregate_verdict(spec_of(on_time))['verdict'] == 'MET'  # exactly at due is on time


@pytest.mark.parametrize('mutation', [
    lambda w: w.pop('available'), lambda w: w.update(available=False), lambda w: w.update(available=1),
    lambda w: w.pop('contract_digest'), lambda w: w.pop('monitor_revision'), lambda w: w.pop('agent'),
    lambda w: w.pop('environment'), lambda w: w.pop('schedule'), lambda w: w.update(agent='other'),
    lambda w: w.update(environment='staging'), lambda w: w.update(schedule='hourly_1h'),
    lambda w: w.update(contract_digest='d' * 64), lambda w: w.update(monitor_revision='r2')])
def test_d2_a_window_without_full_identity_or_availability_is_a_history_gap(mutation):
    bad = win(0, 'BREACHED')
    mutation(bad)
    slots = persistence_slots(3, 2, [bad, win(1, 'BREACHED'), win(2, 'MET')], IDENTITY)
    assert slots[0] == {'index': 0, 'verdict': 'UNKNOWN', 'reason': 'persistence_history_gap'}
    assert [s['verdict'] for s in slots[1:]] == ['BREACHED', 'MET']


def test_d2_identity_must_name_every_coordinate():
    for missing in IDENTITY:
        with pytest.raises(AggregateError):
            persistence_slots(1, 0, [win(0, 'MET')], {k: v for k, v in IDENTITY.items() if k != missing})


def test_d3_an_opened_rule_is_not_redelivered_at_a_continuation_but_a_continued_rule_is_evaluated_each_time():
    windows = [win(0, 'UNKNOWN'), win(1, 'BREACHED'), win(2, 'BREACHED')]
    events = [{'id': 'e1', 'window': 1, 'event': 'episode_opened'}, {'id': 'e2', 'window': 2, 'event': 'episode_continued'}]
    out = persistence_decisions({'breached_in': 2, 'of_last': 3}, 'episode_opened', windows, events, IDENTITY)
    assert [(d['decision'], d['delivered']) for d in out] == [('withheld', False), ('not_eligible', False)]
    out = persistence_decisions({'breached_in': 2, 'of_last': 3}, 'episode_continued', windows, events[1:], IDENTITY)
    assert [(d['decision'], d['delivered']) for d in out] == [('qualified', True)]


def test_d3_a_persist_rule_cannot_change_its_trigger_under_overlay_or_meet():
    for operation in ('overlay', 'meet'):
        base, overlay = persist_module(3, 4), persist_module(3, 4)
        other = 'episode_continued' if base['responses'][0]['rules'][0]['trigger']['event'] == 'episode_opened' else 'episode_opened'
        overlay['responses'][0]['rules'][0]['trigger']['event'] = other
        with pytest.raises(RuntimeClosedError):
            compose_runtime_documents(base, overlay, operation=operation)


MIXED_UNITS = [
    {'agent': 'agent_1', 'environment': 'production', 'unit_kind': 'alpha', 'unit_id': 'zeta', 'membership': True,
     'state': 'valid', 'value': '3', 'source_digest': DIGEST},
    {'agent': 'agent_1', 'environment': 'production', 'unit_kind': 'beta', 'unit_id': 'alpha', 'membership': True,
     'state': 'valid', 'value': '4', 'source_digest': DIGEST},
]


def test_d4_commitment_orders_by_canonical_key_object_bytes_with_kind_and_id_both_differing():
    report = valid_report()
    key = bytes(range(32))
    # Independent recomputation: the key object serializes unit_id before unit_kind, so beta/alpha sorts first.
    def cj(value):
        return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode()
    entries = sorted(
        ({'key': {k: u[k] for k in ('agent', 'environment', 'unit_kind', 'unit_id')}, 'membership': True,
          'state': 'valid', 'source_digest': DIGEST, 'value': u['value']} for u in MIXED_UNITS),
        key=lambda e: cj(e['key']))
    assert [e['key']['unit_id'] for e in entries] == ['alpha', 'zeta']
    payload = {**{k: report[k] for k in ('contract_digest', 'monitor_ref', 'monitor_revision',
                                          'window_start_ms', 'window_end_ms', 'source_digest')}, 'units': entries}
    import hmac
    expected = hmac.new(key, cj(payload), hashlib.sha256).hexdigest()
    assert units_commitment_v2(key, report, MIXED_UNITS) == expected == units_commitment_v2(key, report, MIXED_UNITS[::-1])


def test_d5_precision_limit_report_may_omit_sum_only_with_the_closed_reason():
    report = valid_report(); del report['sum']
    assert refused(report) == 'runtime_report_numeric'
    report['unknown_reason'] = 'aggregate_precision_limit'
    assert validate_report_v2(report, BINDING) == {'verdict': 'UNKNOWN', 'reason': 'aggregate_precision_limit'}
    assert refused(dict(report, unknown_reason='other')) == 'schema_error'
    assert refused(dict(valid_report(), unknown_reason='aggregate_precision_limit')) == 'runtime_report_numeric'
    incomplete = valid_report(); del incomplete['sum']
    incomplete['counts'].update(missing_value=1, contribution_count=2)
    incomplete['unknown_reason'] = 'aggregate_precision_limit'
    assert refused(incomplete) == 'runtime_report_numeric'  # the exception is for complete reports only
    assert validate_report_v2(valid_report(), BINDING) is None


def test_d6_empty_population_cannot_carry_a_sum_and_sums_must_fully_match():
    report = valid_report()
    report['counts'].update(selected=1, reported=1, member_count=0, contribution_count=0, excluded=1)
    for sum_value in ('5', '0.5', '00', '0.0'):
        assert refused(dict(report, sum=sum_value)) == 'runtime_report_numeric'
    assert validate_report_v2(dict(report, sum='0'), BINDING) is None  # RFC 0005:245-247: absent or exactly "0"
    del report['sum']
    validate_report_v2(report, BINDING)  # no sum for no members
    for bad in ('12.5\n', '12.5 ', '\n12.5', '12.5\r'):
        assert refused(dict(valid_report(), sum=bad)) == 'runtime_report_numeric'


@pytest.mark.parametrize('membership', [1, 0, 'true', 'False', None, [], {}, 1.0])
def test_d7_membership_other_than_true_false_unknown_makes_the_census_incomplete(membership):
    units = [{'key': 'u1', 'membership': True, 'status': 'completed', 'value': '10'},
             {'key': 'u2', 'membership': membership, 'status': 'completed', 'value': '5'}]
    assert aggregate_verdict(spec_of(units)) == {'verdict': 'UNKNOWN', 'reason': 'incomplete'}


def test_d6_unit_value_with_trailing_newline_is_invalid_not_twelve_and_a_half():
    units = [{'key': 'u1', 'membership': True, 'status': 'completed', 'value': '12.5\n'}]
    assert aggregate_verdict(spec_of(units)) == {'verdict': 'UNKNOWN', 'reason': 'incomplete'}


@pytest.mark.parametrize('value', ['9' * 5000, 10 ** 5000, '0.' + '1' * 5000], ids=['long-int-string', 'huge-int', 'long-fraction'])
def test_d8_overlong_numeric_values_are_a_precision_limit_never_a_crash(value):
    units = [{'key': 'u1', 'membership': True, 'status': 'completed', 'value': value}]
    assert aggregate_verdict(spec_of(units)) == {'verdict': 'UNKNOWN', 'reason': 'aggregate_precision_limit'}
    assert aggregate_verdict(spec_of(units, precision_scale=6)) == {'verdict': 'UNKNOWN', 'reason': 'aggregate_precision_limit'}
    # an incomplete census still reports incomplete first
    units.append({'key': 'u2', 'membership': 'unknown', 'status': 'completed'})
    assert aggregate_verdict(spec_of(units)) == {'verdict': 'UNKNOWN', 'reason': 'incomplete'}


def test_d8_overlong_bound_is_a_closed_refusal():
    with pytest.raises(AggregateError):
        aggregate_verdict(spec_of([], bound={'lte': '9' * 5000}))


def test_d9_valid_unit_without_value_is_a_closed_error_not_a_key_error():
    unit = dict(MIXED_UNITS[0]); del unit['value']
    with pytest.raises(AggregateError):
        units_commitment_v2(bytes(32), valid_report(), [unit])
    with pytest.raises(AggregateError):
        units_commitment_v2(bytes(32), valid_report(), [dict(MIXED_UNITS[0], value='NaN')])
    missing = {k: v for k, v in unit.items()}; missing['state'] = 'missing'
    assert len(units_commitment_v2(bytes(32), valid_report(), [missing])) == 64


@pytest.mark.parametrize('first,second', [('1', '1.0'), ('1.50', '1.5'), (1, '1.000'), ('0', '0.0')])
def test_d10_numerically_equal_duplicate_values_are_identical_replays(first, second):
    units = [{'key': 'u1', 'membership': True, 'status': 'completed', 'value': first},
             {'key': 'u1', 'membership': True, 'status': 'completed', 'value': second}]
    assert aggregate_verdict(spec_of(units))['member_count'] == 1
    units[1]['value'] = '2'
    assert aggregate_verdict(spec_of(units)) == {'verdict': 'UNKNOWN', 'reason': 'incomplete'}


def test_d12_keyed_commitment_fixture_counts_agree_with_its_units():
    fixture = case('aggregate_report/aggregate-keyed-commitment.yml')['input']
    counts = fixture['report']['counts']
    units = fixture['units']
    members = [u for u in units if u['membership'] is True]
    expected = {
        'selected': len(units), 'reported': len(units), 'dropped': 0,
        'unknown_membership': sum(u['membership'] == 'unknown' for u in units),
        'excluded': sum(u['membership'] is False for u in units),
        'member_count': len(members),
        'contribution_count': sum(u['state'] == 'valid' for u in members),
        'missing_value': sum(u['state'] == 'missing' for u in members),
        'invalid_value': sum(u['state'] == 'invalid' for u in members),
        'unplaceable': 0,
    }
    assert counts == expected
    validate_report_v2(fixture['report'], BINDING)


@pytest.mark.parametrize('first,second', [('1', '1.0000000'), ('1.0000000', '1')])
def test_d10b_duplicate_replay_precision_is_order_independent(first, second):
    units = [{'key': 'u1', 'membership': True, 'status': 'completed', 'value': first},
             {'key': 'u1', 'membership': True, 'status': 'completed', 'value': second}]
    assert aggregate_verdict(spec_of(units, precision_scale=6)) == {
        'verdict': 'MET', 'sum': '1', 'member_count': 1}


def test_d13_malformed_long_contribution_is_incomplete_not_precision_limit():
    for bad in ('x' * 257, '1' * 256 + 'x', '-' + '1' * 300):
        units = [{'key': 'u1', 'membership': True, 'status': 'completed', 'value': bad}]
        assert aggregate_verdict(spec_of(units)) == {'verdict': 'UNKNOWN', 'reason': 'incomplete'}
    long_valid = [{'key': 'u1', 'membership': True, 'status': 'completed', 'value': '1' * 257}]
    assert aggregate_verdict(spec_of(long_valid)) == {'verdict': 'UNKNOWN', 'reason': 'aggregate_precision_limit'}
    assert aggregate_verdict(spec_of([{'key': 'u1', 'membership': True, 'status': 'completed', 'value': -(10 ** 300)}])) == {
        'verdict': 'UNKNOWN', 'reason': 'incomplete'}


def test_d14_declared_precision_scale_checked_per_contribution():
    units = [{'key': 'u1', 'membership': True, 'status': 'completed', 'value': '0.1234567'}]
    assert aggregate_verdict(spec_of(units, precision_scale=6)) == {
        'verdict': 'UNKNOWN', 'reason': 'aggregate_precision_limit'}
    units[0]['value'] = '0.1234560'  # minimal form has scale 6
    assert aggregate_verdict(spec_of(units, precision_scale=6))['verdict'] == 'MET'
