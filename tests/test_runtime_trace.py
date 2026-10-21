"""Executable RFC 0004 histories, plus boundary and rejection probes."""
from __future__ import annotations

from copy import deepcopy
from itertools import product
from pathlib import Path

import pytest

from tvl.runtime_conformance import ConformanceFailureError, run_runtime_conformance_case
from tvl.runtime_trace import TraceError, _delivered, notification_trace
from tvl.yaml_safe import safe_load

CASES = Path(__file__).resolve().parents[1] / 'conformance/cases/runtime/semantic_traces'
NAMES = sorted(path.stem for path in CASES.glob('*.yml'))


def load_case(name):
    return safe_load((CASES / f'{name}.yml').read_text())


def run(case):
    return notification_trace(case['module'], case['input']['history'])


def evaluations(case):
    return case['input']['history']['evaluations']


@pytest.mark.parametrize('name', NAMES)
def test_rfc0004_recorded_trace(name):
    case = load_case(name)
    original = deepcopy(case)
    assert run(case) == case['expected']['notifications']
    assert case == original, 'reference relation must not mutate its inputs'


def test_all_thirteen_traces_present():
    assert len(NAMES) == 13


@pytest.mark.parametrize('only,unless', list(product([False, None, True], repeat=2)))
def test_kleene_resolution(only, unless):
    assert _delivered([only], [unless]) == (only is not False and unless is not True)


def test_kleene_lists_and_empty_identities():
    assert _delivered([], [])
    assert not _delivered([True, None, False], [])
    assert not _delivered([], [False, None, True])
    assert _delivered([True, None], [False, None])


@pytest.mark.parametrize('mutation', ['missing', 'extra', 'duplicate', 'wrong_instant', 'wrong_order'])
def test_conformance_requires_exact_notification_sequence(mutation):
    case = load_case('invalid-promotion-evidence-gives-optimize-failed')
    expected = case['expected']['notifications']
    if mutation == 'missing':
        expected.pop()
    elif mutation == 'extra':
        expected.append(dict(response='repair', rule='spurious', event='deploy_failed', instant=9))
    elif mutation == 'duplicate':
        expected.append(deepcopy(expected[0]))
    elif mutation == 'wrong_instant':
        expected[0]['instant'] = 9
    else:
        expected.reverse()
    with pytest.raises(ConformanceFailureError, match='Notification sequence mismatch'):
        run_runtime_conformance_case(case)


@pytest.mark.parametrize('reason', ['resolved', 'withdrawn'])
def test_episode_closure_is_silent_for_both_reasons(reason):
    case = load_case('attempt-closed-by-episode-closure-records-no-outcome')
    evaluations(case)[1]['episodes'][0]['reason'] = reason
    rule = case['module']['responses'][0]['rules'][-1]
    rule['trigger']['event'] = 'episode_' + reason
    assert run(case) == [dict(response='repair', rule='closed_page', event='episode_' + reason, instant=1)]


@pytest.mark.parametrize('state', ['declined', 'expired'])
@pytest.mark.parametrize('effect', ['optimize', 'deploy'])
def test_approval_closes_only_before_the_next_effect_starts(state, effect):
    name = ('optimization-approval-expires-after-start-still-records-outcome' if effect == 'optimize'
            else 'deploy-approval-declined-before-start-closes-without-outcome')
    case = load_case(name)
    records = evaluations(case)[1]['optimizations']
    records[0]['state'] = state
    if effect == 'optimize':
        # Preserve the after-start outcome even on a decline.
        assert run(case)[0]['event'] == 'optimize_failed'
        evaluations(case)[0]['optimizations'].pop()  # remove start
        assert run(case) == []
    else:
        assert run(case) == case['expected']['notifications']


@pytest.mark.parametrize('completion', ['normal', 'error', 'cancelled', 'cost_limit'])
@pytest.mark.parametrize('reverse', [False, True])
def test_any_promote_takes_precedence_over_invalid_and_abnormal_completion(completion, reverse):
    case = load_case('one-promoted-and-one-invalid-candidate-give-no-failure')
    record = evaluations(case)[1]['optimizations'][0]
    record['completion'] = completion
    if reverse:
        record['candidates'].reverse()
    assert run(case) == case['expected']['notifications']


@pytest.mark.parametrize('legacy,verdicts', [('Reject', ['MET']), ('NoDecision', ['MET']),
                                            ('Promote', ['BREACHED']), ('Promote', ['UNKNOWN'])])
def test_candidate_uses_existing_rfc0003_promotion_join(legacy, verdicts):
    case = load_case('invalid-promotion-evidence-gives-optimize-failed')
    record = evaluations(case)[1]['optimizations'][0]
    record['candidates'] = [dict(evidence_valid=True, legacy_decision=legacy, monitor_verdicts=verdicts)]
    assert run(case)[0]['event'] == 'optimize_no_candidate'


@pytest.mark.parametrize('checks,write,exhausted,expected', [
    ('passed', 'failed', True, 'deploy_failed'),
    ('refused', 'not_attempted', False, 'deploy_refused'),
    ('unreachable', 'not_attempted', False, None),
    ('passed', 'failed', False, None),
])
def test_deploy_checks_and_finite_retry_exhaustion(checks, write, exhausted, expected):
    case = load_case('deploy-write-fails-then-succeeds-on-same-occurrence-retry')
    evaluations(case)[:] = evaluations(case)[:2]
    record = evaluations(case)[1]['optimizations'][1]
    record.update(checks=checks, write=write, retries_exhausted=exhausted)
    events = run(case)
    if expected:
        assert [e['event'] for e in events] == [expected, 'episode_continued']
    else:
        assert events == []


def test_deploy_approval_expiry_after_write_started_preserves_terminal_outcome():
    case = load_case('deploy-write-fails-then-succeeds-on-same-occurrence-retry')
    records = evaluations(case)[1]['optimizations']
    approval = deepcopy(records[0])
    approval.update(fact='approval', effect='deploy', state='expired')
    records.insert(1, approval)
    records[-1]['retries_exhausted'] = True
    evaluations(case)[:] = evaluations(case)[:2]
    assert run(case)[0]['event'] == 'deploy_failed'


def test_promoted_candidate_with_deploy_never_closes_without_outcome():
    case = load_case('one-promoted-and-one-invalid-candidate-give-no-failure')
    case['module']['responses'][0]['rules'] = [
        rule for rule in case['module']['responses'][0]['rules']
        if not rule['id'].startswith('deploy_')]
    case['module']['responses'][0]['rules'][0]['deploy'] = 'never'
    evaluations(case)[:] = evaluations(case)[:3]
    assert run(case) == [dict(response='repair', rule='page_unless_repair', event='episode_continued', instant=2)]


def test_unknown_threshold_met_even_when_deciding_window_arrives_in_same_evaluation():
    case = load_case('initial-counted-window-followed-by-met-fires-unknown-for')
    first, second, *_ = evaluations(case)
    second['windows'].insert(0, first['windows'][0])
    evaluations(case)[:] = [second]
    assert run(case) == [dict(response='repair', rule='undecided', event='unknown_for', instant=12)]


def test_unknown_windows_are_ordered_by_start_not_record_arrival():
    case = load_case('undecided-run-continues-across-window-without-usable-evidence')
    windows = [record['windows'][0] for record in evaluations(case)[:3]]
    evaluations(case)[:] = [dict(instant=18, windows=list(reversed(windows)))]
    assert run(case) == case['expected']['notifications']


def test_no_usable_window_does_not_count_and_met_ends_run():
    case = load_case('undecided-run-continues-across-window-without-usable-evidence')
    evaluations(case)[0]['windows'][0]['usable'] = False
    assert run(case) == []
    case = load_case('undecided-run-continues-across-window-without-usable-evidence')
    evaluations(case)[1]['windows'][0]['verdict'] = 'MET'
    with pytest.raises(TraceError, match='decided window requires usable evidence'):
        run(case)


def test_monitor_revision_resets_unknown_run():
    case = load_case('undecided-run-continues-across-window-without-usable-evidence')
    evaluations(case)[1]['revisions'] = [dict(kind='monitor', name='monitor_main', value='2')]
    assert run(case) == []


def test_corrected_records_change_run_without_withdrawing_fired_event():
    case = load_case('initial-counted-window-followed-by-met-fires-unknown-for')
    window = deepcopy(evaluations(case)[0]['windows'][0])
    window['verdict'] = 'MET'
    evaluations(case)[1]['windows'] = [window]
    assert run(case) == case['expected']['notifications']


def test_unknown_repeat_rechecks_guards_and_does_not_redeliver_suppressed_occurrence():
    case = load_case('undecided-guard-does-not-suppress')
    rule = case['module']['responses'][0]['rules'][0]
    rule['trigger'] = dict(monitor='monitor_main', event='unknown_for', hours=6)
    rule['repeat_after_hours'] = 6
    rule['max_repeats'] = 1
    case['module']['responses'][0]['rules'] = [rule]
    def window(start):
        return dict(monitor='monitor_main', start=start, end=start + 6, verdict='UNKNOWN', usable=True)
    evaluations(case)[:] = [dict(instant=6, windows=[window(0), dict(window(0), monitor='other', verdict='MET')]),
                           dict(instant=12, windows=[window(6)], episodes=[dict(monitor='other',scope='other-1',event='opened')]),
                           dict(instant=18, windows=[window(12)])]
    assert run(case) == [dict(response='repair', rule='only_page', event='unknown_for', instant=12)]


def test_attempts_with_identical_rule_ids_in_other_responses_do_not_inhibit():
    case = load_case('attempt-open-visible-to-rule-fired-by-same-evaluation')
    repair = case['module']['responses'][0]
    other = deepcopy(repair)
    other['name'] = 'other_response'
    other['rules'] = [rule for rule in other['rules'] if rule['id'] == 'opening_page' or rule['do'] == 'optimize']
    case['module']['responses'].append(other)
    assert run(case)[0] == dict(response='other_response',rule='opening_page',event='episode_opened',instant=0)


@pytest.mark.parametrize('location', ['history', 'evaluation', 'window', 'episode', 'optimization'])
def test_unknown_fields_fail_closed(location):
    case = load_case('invalid-promotion-evidence-gives-optimize-failed')
    if location == 'history':
        record = case['input']['history']
    elif location == 'evaluation':
        record = evaluations(case)[0]
    elif location == 'episode':
        record = evaluations(case)[0]['episodes'][0]
    elif location == 'optimization':
        record = evaluations(case)[0]['optimizations'][0]
    else:
        case = load_case('initial-counted-window-followed-by-met-fires-unknown-for')
        record = evaluations(case)[0]['windows'][0]
    record['invented'] = True
    with pytest.raises(TraceError, match='unknown record field'):
        run(case)


@pytest.mark.parametrize('mutation', ['backwards', 'duplicate', 'bool_instant', 'future_window', 'unknown_verdict', 'bad_width', 'bool_usable'])
def test_invalid_time_and_window_records_fail_closed(mutation):
    case = load_case('initial-counted-window-followed-by-met-fires-unknown-for')
    if mutation == 'backwards':
        evaluations(case)[1]['instant'] = 5
    elif mutation == 'duplicate':
        evaluations(case)[1]['instant'] = 6
    elif mutation == 'bool_instant':
        evaluations(case)[0]['instant'] = True
    else:
        window = evaluations(case)[0]['windows'][0]
        if mutation == 'future_window':
            evaluations(case)[0]['instant'] = 5
        elif mutation == 'unknown_verdict':
            window['verdict'] = 'maybe'
        elif mutation == 'bad_width':
            window['end'] = 5
        else:
            window['usable'] = 'yes'
    with pytest.raises(TraceError):
        run(case)


def test_unrecognized_fact_and_inconsistent_effect_facts_fail_closed():
    case = load_case('invalid-promotion-evidence-gives-optimize-failed')
    evaluations(case)[1]['optimizations'][0]['fact'] = 'magic'
    with pytest.raises(TraceError):
        run(case)
    case = load_case('deploy-write-fails-then-succeeds-on-same-occurrence-retry')
    evaluations(case)[1]['optimizations'][1]['checks'] = 'refused'
    with pytest.raises(TraceError, match='write without passed checks'):
        run(case)


def test_episode_opened_repeat_rechecks_suppressed_guard():
    case = load_case('attempt-open-visible-to-rule-fired-by-same-evaluation')
    rule = case['module']['responses'][0]['rules'][0]
    rule.update(repeat_after_hours=6, max_repeats=1)
    evaluations(case)[:] = evaluations(case)[:2] + [dict(instant=6), dict(instant=12)]
    assert run(case) == [dict(response='repair', rule='opening_page', event='episode_opened', instant=6)]


def test_episode_closed_before_repeat_cancels_repeat():
    case = load_case('attempt-open-visible-to-rule-fired-by-same-evaluation')
    rule = case['module']['responses'][0]['rules'][0]
    rule.update(repeat_after_hours=6, max_repeats=1)
    evaluations(case)[:] = evaluations(case)[:2] + [
        dict(instant=2, episodes=[dict(monitor='monitor_main',scope='episode-1',event='closed',reason='withdrawn')]),
        dict(instant=6)]
    assert run(case) == []


@pytest.mark.parametrize('boundary', ['episode', 'response'])
def test_already_started_optimization_records_outcome_after_pending_scope_closes(boundary):
    case = load_case('invalid-promotion-evidence-gives-optimize-failed')
    if boundary == 'episode':
        evaluations(case)[1]['episodes'] = [dict(monitor='monitor_main',scope='episode-1',event='closed',reason='resolved')]
    else:
        evaluations(case)[1]['revisions'] = [dict(kind='response',name='repair',value='2')]
    evaluations(case)[:] = evaluations(case)[:2]
    assert run(case) == [dict(response='repair',rule='optimize_failed',event='optimize_failed',instant=1)]


def test_finished_promoted_run_cannot_deploy_after_scope_closed_during_run():
    case = load_case('one-promoted-and-one-invalid-candidate-give-no-failure')
    evaluations(case)[1]['episodes'] = [dict(monitor='monitor_main',scope='episode-1',event='closed',reason='resolved')]
    evaluations(case)[:] = evaluations(case)[:2] + [evaluations(case)[3]]
    assert run(case) == []


def test_late_invalid_completion_still_fails_closed():
    case = load_case('attempt-closed-by-episode-closure-records-no-outcome')
    evaluations(case)[1]['optimizations'][0]['completion'] = 'UNSUPPORTED_COMPLETION'
    with pytest.raises(TraceError, match='expected one of'):
        run(case)


def test_unsupported_trigger_and_repeat_combinations_are_explicit():
    case = load_case('undecided-guard-does-not-suppress')
    rule = case['module']['responses'][0]['rules'][1]
    rule['repeat_after_hours'] = 6
    with pytest.raises(TraceError, match='trace repeats support'):
        run(case)
    rule.pop('repeat_after_hours')
    rule['trigger']['event'] = 'unit_violation'
    with pytest.raises(TraceError, match='unsupported trace notification trigger'):
        run(case)


def test_overlapping_unaligned_tumbling_windows_fail_closed():
    case = load_case('initial-counted-window-followed-by-met-fires-unknown-for')
    rule = case['module']['responses'][0]['rules'][0]
    rule['trigger']['hours'] = 9
    first = evaluations(case)[0]['windows'][0]
    overlap = dict(first, start=3, end=9)
    evaluations(case)[:] = [dict(instant=9, windows=[first, overlap])]
    with pytest.raises(TraceError, match='align to tumbling boundaries'):
        run(case)


def test_batched_continuation_facts_each_produce_a_notification():
    case = load_case('attempt-open-visible-to-rule-fired-by-same-evaluation')
    evaluations(case)[2]['episodes'] *= 2
    assert run(case) == [dict(response='repair',rule='page_unless_repair',event='episode_continued',instant=2)] * 2


def test_missed_repeat_evaluation_does_not_invent_a_catch_up_policy():
    case = load_case('attempt-open-visible-to-rule-fired-by-same-evaluation')
    case['module']['responses'][0]['rules'][0].update(repeat_after_hours=6)
    evaluations(case)[:] = evaluations(case)[:2] + [dict(instant=13)]
    with pytest.raises(TraceError, match='repeat due instant must be recorded'):
        run(case)


@pytest.mark.parametrize('field', ['only_while', 'unless'])
@pytest.mark.parametrize('state', ['unevaluated', 'evaluated_closed', 'open', 'resolved', 'withdrawn'])
def test_monitor_guard_uses_recorded_episode_state(field, state):
    case = load_case('undecided-guard-does-not-suppress')
    rule = case['module']['responses'][0]['rules'][0]
    rule.pop('only_while')
    rule[field] = [dict(monitor='other',state='episode_open')]
    case['module']['responses'][0]['rules'] = [rule]
    evaluation = dict(instant=6,episodes=[dict(monitor='monitor_main',scope='source-1',event='opened')])
    if state == 'evaluated_closed':
        evaluation['windows'] = [dict(monitor='other',start=0,end=6,verdict='MET',usable=True)]
    if state in {'open', 'resolved', 'withdrawn'}:
        evaluation['episodes'].append(dict(monitor='other',scope='other-1',event='opened'))
    if state in {'resolved', 'withdrawn'}:
        evaluation['episodes'].append(dict(monitor='other',scope='other-1',event='closed',reason=state))
    evaluations(case)[:] = [evaluation]
    delivered = state == 'unevaluated' or (state == 'open' if field == 'only_while' else state != 'open')
    assert bool(run(case)) is delivered


def test_decided_usable_window_ends_unknown_run():
    case = load_case('undecided-run-continues-across-window-without-usable-evidence')
    evaluations(case)[1]['windows'][0].update(verdict='MET',usable=True)
    assert run(case) == []
