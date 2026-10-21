"""RFC 0004: notification-only reactive outcomes, undecided runs and guards."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tvl.canonical import RuntimeClosedError, canonical_json_digest
from tvl.lints import lint_module, lint_pack
from tvl.runtime import compile_runtime_document, compose_runtime_documents
from tvl.runtime_conformance import _build_synthetic_tokens_for_docs
from tvl.runtime_projection import token_map_template, validate_projected_contract
from tvl.schema import runtime_contract_validator, runtime_local_validator, validator
from tvl.yaml_safe import safe_load

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / 'conformance/cases/runtime'


def module():
    return safe_load((CASES / 'projection/outcome-and-guard-closed-enums.yml').read_text())['module']


def tokens(*docs):
    entries = _build_synthetic_tokens_for_docs(docs)
    for i, entry in enumerate(entries):
        entry['hosted'] = f'ref_{i}'
    return {'format': 'tvl-token-map/1', 'tokens': entries}


def codes(doc):
    return {i['code'] for i in (lint_pack(doc) if 'pack' in doc else lint_module(doc))}


def test_compile_new_constructs_and_preserve_hosted_reference_bindings():
    d = module()
    c, local, _ = compile_runtime_document(d, token_map_doc=tokens(d))
    assert c['tvl_version'] == local['tvl_version'] == '1.4'
    assert not list(runtime_contract_validator(c["format"]).iter_errors(c))
    assert not list(runtime_local_validator(local["format"]).iter_errors(local))
    rules = c['declarations']['responses'][0]['rules']
    assert rules[1]['trigger'] == {'rule': rules[0]['id'], 'event': 'optimize_no_candidate'}
    assert rules[1]['unless'] == [{'rule': rules[0]['id'], 'state': 'attempt_open'}]
    assert local['declarations']['responses'][0]['rules'][1]['trigger']['rule'] == 'opt'
    assert rules[2]['trigger']['event'] == 'unknown_for'
    template = token_map_template([d])
    assert all(entry['hosted'] == '' for entry in template['tokens'])
    assert not any(entry['local'] == 'None' for entry in template['tokens'])


@pytest.mark.parametrize('event', ['optimize_no_candidate', 'optimize_failed', 'deploy_refused', 'deploy_failed'])
def test_all_sealed_outcomes_compile(event):
    d = module(); d['responses'][0]['rules'][1]['trigger']['event'] = event
    compile_runtime_document(d, token_map_doc=tokens(d))


@pytest.mark.parametrize('field', ['trigger', 'only_while', 'unless', 'unknown_for'])
@pytest.mark.parametrize('version', [None, '1.3', '1.4'])
def test_version_is_presence_based_for_every_construct(field, version):
    d = module(); rules = d['responses'][0]['rules']
    page = {'id': 'page', 'trigger': {'monitor': 'monitor_main', 'event': 'episode_opened'}, 'do': 'notify'}
    if field == 'trigger': page['trigger'] = {'rule': 'opt', 'event': 'optimize_failed'}
    elif field == 'unknown_for': page['trigger'].update(event='unknown_for', hours=6)
    else: page[field] = []
    d['responses'][0]['rules'] = [rules[0], page]
    if version is None: d.pop('tvl_version')
    else: d['tvl_version'] = version
    expected = 'runtime_version_required' if version is None else 'declared_version_below_constructs'
    assert (expected in codes(d)) == (version != '1.4')


@pytest.mark.parametrize('field', ['only_while', 'unless', 'trigger', 'unknown_for'])
def test_every_reactive_construct_rejects_service_actions(field):
    d = module(); r = d['responses'][0]['rules'][1]
    r.pop('only_while'); r.pop('unless'); r['do'] = 'optimize'
    if field != 'trigger': r['trigger'] = {'monitor': 'monitor_main', 'event': 'episode_opened'}
    if field in {'only_while', 'unless'}: r[field] = []
    if field == 'unknown_for': r['trigger'].update(event='unknown_for', hours=6)
    assert 'runtime_notify_only' in codes(d)


@pytest.mark.parametrize('reference,expected', [('missing', 'runtime_missing_ref'), ('unknown', 'runtime_ref_kind_mismatch'), ('outcome', 'runtime_ref_kind_mismatch')])
def test_outcome_references_are_response_local_and_optimize_only(reference, expected):
    d = module(); d['responses'][0]['rules'][1]['trigger']['rule'] = reference
    assert expected in codes(d)
    if reference == 'missing':
        d['responses'].append({'name': 'other_response', 'rules': [{'id': 'missing', 'trigger': {'monitor': 'monitor_main', 'event': 'episode_opened'}, 'do': 'optimize'}]})
        assert expected in codes(d)


@pytest.mark.parametrize('field', ['only_while', 'unless'])
@pytest.mark.parametrize('guard,expected', [
    ({'rule': 'missing', 'state': 'attempt_open'}, 'runtime_missing_ref'),
    ({'rule': 'outcome', 'state': 'attempt_open'}, 'runtime_ref_kind_mismatch'),
    ({'monitor': 'monitor_gate', 'state': 'episode_open'}, 'runtime_ref_kind_mismatch'),
    ({'monitor': 'monitor_main', 'state': 'attempt_open'}, 'runtime_unknown_kind'),
    ({'monitor': 'monitor_main', 'state': 'invented'}, 'runtime_unknown_kind'),
])
def test_guard_references_and_states(field, guard, expected):
    d = module(); d['responses'][0]['rules'][1][field] = [guard]
    assert expected in codes(d)


def test_cycle_crosses_responses_and_uses_outcome_source_monitor():
    d = module(); r = d['responses'][0]['rules'][1]
    r['unless'] = [{'monitor': 'monitor_other', 'state': 'episode_open'}]
    d['responses'].append({'name': 'other', 'rules': [{'id': 'back', 'trigger': {'monitor': 'monitor_other', 'event': 'episode_opened'}, 'do': 'notify', 'unless': [{'monitor': 'monitor_main', 'state': 'episode_open'}]}]})
    assert 'runtime_guard_cycle' in codes(d)
    d['responses'][1]['rules'][0]['unless'] = []
    assert 'runtime_guard_cycle' not in codes(d)
    r['unless'] = [{'rule': 'opt', 'state': 'attempt_open'}]
    assert 'runtime_guard_cycle' not in codes(d)
    r['only_while'] = [{'monitor': 'monitor_main', 'state': 'episode_open'}]
    assert ('runtime_guard_redundant', 'warning') in {(i['code'], i['severity']) for i in lint_module(d)}


@pytest.mark.parametrize('operation', ['overlay', 'meet'])
@pytest.mark.parametrize('field', ['only_while', 'unless', 'trigger'])
def test_reactive_coordinates_immutable_under_both_operations(operation, field):
    b = module(); o = copy.deepcopy(b); r = o['responses'][0]['rules'][1]
    if field == 'trigger': r[field]['event'] = 'optimize_failed'
    else: r[field] = []
    with pytest.raises(RuntimeClosedError) as exc:
        compose_runtime_documents(b, o, operation=operation)
    assert exc.value.code == 'runtime_incompatible_replacement'


@pytest.mark.parametrize('operation', ['overlay', 'meet'])
def test_guard_order_and_duplicates_do_not_change_comparison_or_compiled_digest(operation):
    b = module(); o = copy.deepcopy(b); r = o['responses'][0]['rules'][1]
    r['only_while'] = r['only_while'] * 2
    r['unless'] = r['unless'] * 3
    composed, _ = compose_runtime_documents(b, o, operation=operation)
    a, _, _ = compile_runtime_document(b, token_map_doc=tokens(b))
    c, _, _ = compile_runtime_document(composed, token_map_doc=tokens(b))
    assert canonical_json_digest(a) == canonical_json_digest(c)


@pytest.mark.parametrize('hours,expected', [(None,'runtime_invalid_ladder'), (0,'runtime_trigger_hours_out_of_range'), (5,'runtime_trigger_hours_out_of_range'), (6,None), (7,None)])
def test_unknown_for_window_boundary(hours, expected):
    d = module(); t = d['responses'][0]['rules'][2]['trigger']
    if hours is None: t.pop('hours')
    else: t['hours'] = hours
    if expected: assert expected in codes(d)
    else: assert not [i for i in lint_module(d) if i['severity'] == 'error']


@pytest.mark.parametrize('artifact', ['hosted', 'local'])
@pytest.mark.parametrize('location,value', [('outcome','success'), ('monitor_event','maybe'), ('guard','unknown')])
def test_compiled_enums_are_closed(artifact, location, value):
    d = module(); c, l, _ = compile_runtime_document(d, token_map_doc=tokens(d))
    a = c if artifact == 'hosted' else l
    rules = a['declarations']['responses'][0]['rules']
    if location == 'outcome': rules[1]['trigger']['event'] = value
    elif location == 'monitor_event': rules[2]['trigger']['event'] = value
    else: rules[1]['unless'][0]['state'] = value
    v = runtime_contract_validator(a['format']) if artifact == 'hosted' else runtime_local_validator(a['format'])
    assert list(v.iter_errors(a))


@pytest.mark.parametrize('field', ['only_while', 'unless', 'trigger'])
def test_projection_detects_valid_but_wrong_hosted_references(field):
    d = module(); tm = tokens(d); c, _, _ = compile_runtime_document(d, token_map_doc=tm)
    r = c['declarations']['responses'][0]['rules'][1]
    if field == 'trigger': r[field]['rule'] = 'another_valid_ref'
    else:
        key = 'monitor' if field == 'only_while' else 'rule'
        r[field][0][key] = 'another_valid_ref'
    with pytest.raises(RuntimeClosedError) as exc:
        validate_projected_contract(c, doc=d, used_tokens=tm['tokens'])
    assert exc.value.code == 'runtime_unsafe_egress'


@pytest.mark.parametrize('construct', ['outcome', 'attempt'])
@pytest.mark.parametrize('operation', ['overlay', 'meet'])
def test_pack_cannot_borrow_module_rules_during_composition(construct, operation):
    case = safe_load((CASES / 'composition/compile-pack-keeps-composed-responses.yml').read_text())
    pack, d = case['base'], case['overlay']; pack['tvl_version'] = d['tvl_version'] = '1.4'
    r = pack['responses'][0]['rules'][0]
    if construct == 'outcome': r['trigger'] = {'rule':'opt', 'event':'optimize_failed'}
    else: r['unless'] = [{'rule':'opt', 'state':'attempt_open'}]
    with pytest.raises(RuntimeClosedError) as exc:
        compose_runtime_documents(pack, d, operation=operation)
    assert exc.value.code == 'runtime_invalid_ladder'


def test_compile_with_pack_keeps_outcome_notifications():
    case = safe_load((CASES / 'composition/compile-pack-keeps-composed-responses.yml').read_text())
    pack, d = case['base'], case['overlay']; d['tvl_version'] = '1.4'
    d['responses'] = [{'name':'repair','rules':[
        {'id':'fix','trigger':{'monitor':'agent_monitor','event':'episode_opened'},'do':'optimize'},
        {'id':'failed','trigger':{'rule':'fix','event':'optimize_failed'},'do':'notify',
         'unless':[{'rule':'fix','state':'attempt_open'}]}]}]
    c, local, _ = compile_runtime_document(d, packs=[pack], token_map_doc=tokens(d,pack))
    rules = next(r['rules'] for r in local['declarations']['responses'] if r['name'] == 'repair')
    assert [r['id'] for r in rules] == ['fix','failed']
    assert c['tvl_version'] == '1.4'


def test_authored_schema_seals_guard_shapes_and_trigger_alternatives():
    d = module(); assert not list(validator().iter_errors(d))
    d['responses'][0]['rules'][1]['trigger']['monitor'] = 'monitor_main'
    assert list(validator().iter_errors(d))
    d = module(); d['responses'][0]['rules'][1]['unless'][0]['monitor'] = 'monitor_main'
    assert list(validator().iter_errors(d))


@pytest.mark.parametrize('name', ['tvl.schema.json', 'tvl-pack.schema.json', 'tvl-runtime-contract.schema.json', 'tvl-runtime-local.schema.json', 'tvl-runtime-contract-v2.schema.json', 'tvl-runtime-local-v2.schema.json'])
def test_editor_schema_copies_identical(name):
    source = (ROOT/'spec/grammar'/name).read_bytes()
    for directory in ['editor_shared/vscode/schemas','vscode-tvl/schemas']:
        assert (ROOT/directory/name).read_bytes() == source


@pytest.mark.parametrize('operation', ['overlay', 'meet'])
@pytest.mark.parametrize('field', ['only_while', 'unless'])
def test_pack_cannot_borrow_module_monitors_for_guards(operation, field):
    case = safe_load((CASES / 'composition/compile-pack-keeps-composed-responses.yml').read_text())
    pack, d = case['base'], case['overlay']; pack['tvl_version'] = d['tvl_version'] = '1.4'
    pack['responses'][0]['rules'][0][field] = [{'monitor':'agent_monitor', 'state':'episode_open'}]
    with pytest.raises(RuntimeClosedError) as exc:
        compose_runtime_documents(pack, d, operation=operation)
    assert exc.value.code == 'runtime_missing_ref'


def test_malformed_13_rule_list_keeps_its_diagnostic():
    d = module(); d['tvl_version'] = '1.3'; d['responses'][0]['rules'] = 3
    assert 'runtime_invalid_profile' in codes(d)



def test_compile_keeps_guard_reference_to_a_checked_packs_unabsorbed_monitor():
    case = safe_load((CASES / 'composition/pack-guard-absorbed-monitor-rewritten.yml').read_text())
    pack, d = case['base'], case['overlay']
    requirement = copy.deepcopy(pack['requirements'][0])
    requirement['name'] = 'floor_second_req'; requirement['violation']['exceeds'] = 3000
    pack['requirements'].append(requirement)
    monitor = copy.deepcopy(pack['monitors'][0])
    monitor['name'] = 'floor_second'; monitor['requirement'] = requirement['name']
    pack['monitors'].append(monitor)
    pack['responses'][0]['rules'][0]['only_while'] = [{'monitor':'floor_second', 'state':'episode_open'}]
    tm = tokens(d, pack)
    c, local, _ = compile_runtime_document(d, packs=[pack], token_map_doc=tm)
    assert len(c['packs_checked']) == 1
    assert 'floor_second' not in {m['name'] for m in local['declarations']['monitors']}
    assert local['declarations']['responses'][0]['rules'][0]['only_while'] == [
        {'monitor':'floor_second', 'state':'episode_open'}]
    hosted = next(t['hosted'] for t in tm['tokens'] if t['namespace'] == 'monitor' and t['local'] == 'floor_second')
    assert c['declarations']['responses'][0]['rules'][0]['only_while'] == [
        {'monitor':hosted, 'state':'episode_open'}]


@pytest.mark.parametrize('kind', ['outcome', 'monitor_guard', 'attempt_guard'])
def test_authored_reactive_enum_hints_preserve_unknown_kind_diagnostics(kind):
    from tvl.schema import load_schema
    d = module(); r = d['responses'][0]['rules'][1]; defs = load_schema()['$defs']
    if kind == 'outcome':
        field = 'event'; target = r['trigger']
        hints = defs['TriggerDecl']['oneOf'][1]['properties'][field]
    else:
        field = 'state'; target = r['only_while' if kind == 'monitor_guard' else 'unless'][0]
        hints = defs['GuardDecl']['oneOf'][0 if kind == 'monitor_guard' else 1]['properties'][field]
    assert hints['examples'] == hints['x-enum'] and 'enum' not in hints and 'const' not in hints
    target[field] = 'CANARY_UNKNOWN'
    assert not list(validator().iter_errors(d))
    with pytest.raises(RuntimeClosedError) as exc:
        compile_runtime_document(d, token_map_doc=None)
    assert exc.value.code == 'runtime_unknown_kind'
    assert 'CANARY' not in exc.value.message


def test_lint_pack_alone_rejects_attempt_open_guard():
    case = safe_load((CASES / 'composition/compile-pack-keeps-composed-responses.yml').read_text())
    pack = case['base']; pack['tvl_version'] = '1.4'
    pack['responses'][0]['rules'][0]['unless'] = [{'rule': 'opt', 'state': 'attempt_open'}]
    assert 'runtime_invalid_ladder' in codes(pack)


def test_attempt_guard_adds_no_edge_even_when_rule_id_equals_a_monitor_name():
    d = module(); rules = d['responses'][0]['rules']
    opt_id = rules[0]['id']
    for r in rules:
        if r.get('trigger', {}).get('rule') == opt_id:
            r['trigger']['rule'] = 'monitor_other'
        for f in ('only_while', 'unless'):
            for g in r.get(f, []):
                if g.get('rule') == opt_id:
                    g['rule'] = 'monitor_other'
    rules[0]['id'] = 'monitor_other'
    d['responses'].append({'name': 'other', 'rules': [{'id': 'back', 'trigger': {'monitor': 'monitor_other', 'event': 'episode_opened'}, 'do': 'notify', 'unless': [{'monitor': 'monitor_main', 'state': 'episode_open'}]}]})
    assert 'runtime_guard_cycle' not in codes(d)


@pytest.mark.parametrize('operation', ['overlay', 'meet'])
def test_guard_order_reversed_does_not_change_comparison_or_digest(operation):
    b = module(); r0 = b['responses'][0]['rules'][1]
    r0['unless'] = [{'rule': 'opt', 'state': 'attempt_open'}, {'monitor': 'monitor_other', 'state': 'episode_open'}]
    o = copy.deepcopy(b); o['responses'][0]['rules'][1]['unless'].reverse()
    composed, _ = compose_runtime_documents(b, o, operation=operation)
    a, _, _ = compile_runtime_document(b, token_map_doc=tokens(b))
    c, _, _ = compile_runtime_document(composed, token_map_doc=tokens(b))
    assert canonical_json_digest(a) == canonical_json_digest(c)


def test_empty_guard_list_compiles_like_absent():
    b = module(); r = b['responses'][0]['rules'][2]
    r.pop('only_while', None); r.pop('unless', None)
    o = copy.deepcopy(b); o['responses'][0]['rules'][2]['only_while'] = []
    a, _, _ = compile_runtime_document(b, token_map_doc=tokens(b))
    c, _, _ = compile_runtime_document(o, token_map_doc=tokens(o))
    assert canonical_json_digest(a) == canonical_json_digest(c)


def test_unknown_for_with_non_mapping_window_does_not_crash():
    d = module()
    mon = next(m for m in d['monitors'] if m['name'] == d['responses'][0]['rules'][2]['trigger']['monitor'])
    mon['window'] = [1]
    assert codes(d)
