"""Frozen upstream logs v0.2 event contract; no local repo/network dependency."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

import pytest

from wellman.runtime_feedback import analyze_events, main
from wellman.selection_contracts import ContractError, canonical_bytes, payload_digest

# Snapshot of wellmanifest/logs contracts/logs.contract.json, event v1 schema.
EVENT_SCHEMA = json.loads(r'''{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://wellmanifest.dev/schemas/logs/event.v1.json","type":"object","additionalProperties":false,"required":["schema","eventId","stream","sequence","eventType","severity","mode","occurredAt","correlationId","causationId","producer","source","code","subjectRef","outcome","subjectState","evidence","inputHash","receiptRef","previousHash","eventHash","rawOutputIncluded","secretMaterialIncluded"],"properties":{"schema":{"const":"wellmanifest.logs/event/v1"},"eventId":{"type":"string","minLength":8,"maxLength":128,"pattern":"^event:[A-Za-z0-9._:-]+$"},"stream":{"type":"string","minLength":1,"maxLength":64,"pattern":"^[a-z][a-z0-9._-]*$"},"sequence":{"type":"integer","minimum":1,"maximum":9007199254740991},"eventType":{"oneOf":[{"enum":["contract_registered","validation_started","validation_passed","validation_failed","error_raised","remediation_started","remediation_completed"]},{"type":"string","minLength":3,"maxLength":64,"pattern":"^(?!logs\\.)[a-z][a-z0-9]*(?:\\.[a-z][a-z0-9_]*)+$"}]},"severity":{"enum":["DEBUG","INFO","WARNING","ERROR","CRITICAL"]},"mode":{"enum":["PLAN","APPLY"]},"occurredAt":{"type":"string","format":"date-time","maxLength":40},"correlationId":{"type":"string","minLength":1,"maxLength":128,"pattern":"^[A-Za-z0-9._:-]+$"},"causationId":{"oneOf":[{"type":"null"},{"type":"string","minLength":1,"maxLength":128,"pattern":"^[A-Za-z0-9._:-]+$"}]},"producer":{"type":"string","minLength":3,"maxLength":128,"pattern":"^(human|agent|service):[A-Za-z0-9._:-]+$"},"source":{"type":"string","minLength":3,"maxLength":64,"pattern":"^[a-z][a-z0-9]*(?:\\.[a-z][a-z0-9_]*)*$"},"code":{"oneOf":[{"type":"null"},{"type":"string","pattern":"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$"}]},"subjectRef":{"type":"string","minLength":3,"maxLength":160,"pattern":"^[a-z][a-z0-9+.-]*:[A-Za-z0-9._:/-]+$"},"outcome":{"enum":["OBSERVED","ACCEPTED","REJECTED","SUCCEEDED","FAILED"]},"subjectState":{"oneOf":[{"type":"null"},{"type":"string","minLength":1,"maxLength":32,"pattern":"^[a-z][a-z0-9_]*$"}]},"evidence":{"type":"array","minItems":0,"maxItems":16,"uniqueItems":true,"items":{"$ref":"#/$defs/evidence"}},"inputHash":{"type":"string","pattern":"^[a-f0-9]{64}$"},"receiptRef":{"oneOf":[{"type":"null"},{"type":"string","minLength":11,"maxLength":160,"pattern":"^receipt://[A-Za-z0-9._:/-]+$"}]},"previousHash":{"type":"string","pattern":"^[a-f0-9]{64}$"},"eventHash":{"type":"string","pattern":"^[a-f0-9]{64}$"},"rawOutputIncluded":{"const":false},"secretMaterialIncluded":{"const":false}},"$defs":{"evidence":{"type":"object","additionalProperties":false,"required":["path","sha256"],"properties":{"path":{"type":"string","minLength":1,"maxLength":240,"pattern":"^(?!/)(?!.*(?:^|/)\\.\\.(?:/|$))[A-Za-z0-9._/-]+$"},"sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}}}}}''')
CONTRACT = canonical_bytes({'schema': 'wellmanifest.logs/contract-bundle/v1',
                            'schemas': {'event': EVENT_SCHEMA}})
PIN = hashlib.sha256(CONTRACT).hexdigest()
RULES = {'WMX-COMMAND-UNKNOWN': ['wellmanifest/nl-uri-dsl-llm', 'wellmanifest/dsl']}
START, END = '2026-10-08T19:00:00Z', '2026-10-08T20:00:00Z'


def event(sequence=1, previous=None, **extra):
    value = {'schema': 'wellmanifest.logs/event/v1', 'eventId': 'event:sample-%s' % sequence,
             'stream': 'willmux-nl', 'sequence': sequence, 'eventType': 'error_raised',
             'severity': 'ERROR', 'mode': 'APPLY', 'occurredAt': '2026-10-08T19:15:00Z',
             'correlationId': 'conversation-1', 'causationId': None, 'producer': 'service:willmux',
             'source': 'willmux.agent', 'code': 'WMX-COMMAND-UNKNOWN',
             'subjectRef': 'urn:willmux:command:1', 'outcome': 'FAILED', 'subjectState': 'failed',
             'evidence': [], 'inputHash': '1'*64, 'receiptRef': None,
             'previousHash': previous['eventHash'] if previous else '0'*64,
             'rawOutputIncluded': False, 'secretMaterialIncluded': False, **extra}
    value['eventHash'] = payload_digest(value)
    return value


def raw(*events):
    return b''.join(canonical_bytes(e) + b'\n' for e in events)


def analyze(data, **extra):
    return analyze_events(data, contract=CONTRACT, contract_sha256=PIN, rules=RULES,
                          stream='willmux-nl', subject_prefix='urn:willmux:',
                          window_start=START, window_end=END, **extra)


def test_recurrence_is_grouped_and_replays_do_not_inflate_failures():
    one = event()
    two = event(2, one, occurredAt='2026-10-08T19:30:00Z')
    result = analyze(raw(one, one, two))
    assert result['uniqueFailures'] == 2
    assert result['duplicateEvents'] == 1
    assert result['groups'][0]['count'] == 2
    assert result['groups'][0]['priority'] == 'recurring'
    assert result['groups'][0]['standardCandidates'] == sorted(RULES['WMX-COMMAND-UNKNOWN'])
    assert result['groups'][0]['id'] == analyze(raw(one))['groups'][0]['id']
    assert not result['executable'] and not result['grantsAuthority']
    assert result['conformance'] == result['groups'][0]['verification'] == 'unverified'


def test_remediation_claim_does_not_prove_repair_and_later_failure_is_visible():
    failure = event()
    repair = event(2, failure, eventType='remediation_completed', severity='INFO', code=None,
                   outcome='SUCCEEDED', subjectState='completed', causationId=failure['eventId'],
                   occurredAt='2026-10-08T19:20:00Z', receiptRef='receipt://willmux/repair')
    later = event(3, repair, occurredAt='2026-10-08T19:30:00Z')
    result = analyze(raw(failure, repair, later))
    group = result['groups'][0]
    assert group['remediationAttempts'] == 1
    assert group['recurrenceAfterAttempt'] is True
    assert group['verification'] == 'unverified'


def test_unrelated_or_earlier_attempt_is_not_counted():
    failure = event()
    other = event(2, failure, eventType='remediation_completed', severity='INFO', code=None,
                  outcome='SUCCEEDED', causationId='event:unrelated', occurredAt='2026-10-08T19:10:00Z')
    assert analyze(raw(failure, other))['groups'][0]['remediationAttempts'] == 0


@pytest.mark.parametrize('mutation', [
    {'severity': 'OTHER'}, {'code': []}, {'receiptRef': 7}, {'eventType': 'logs.spoof'},
    {'unknown': 'sensitive value'}, {'rawOutputIncluded': True}, {'secretMaterialIncluded': True},
    {'sequence': True}, {'occurredAt': '2026-10-08T19:00:00'}, {'occurredAt': 'invalid'},
    {'subjectState': 42}, {'evidence': [{'path': '../secret', 'sha256': '1'*64}]},
])
def test_closed_schema_and_union_assertions_are_enforced_without_raw_output(mutation):
    value = event(**mutation)
    result = analyze(raw(value))
    assert result['uniqueFailures'] == 0 and result['coverage'] == 'partial'
    assert result['diagnostics'] == [{'code': 'RUNTIME-EVENT-INVALID', 'line': 1}]
    assert 'sensitive value' not in json.dumps(result)


@pytest.mark.parametrize('data', [b'{', b'null\n', b'{}\n', b'\xff\n',
                                 b'{"a":1,"a":2}\n', b'\n'])
def test_malformed_line_is_partial_observation(data):
    assert analyze(data)['coverage'] == 'partial'


def test_hash_corruption_chain_gap_and_conflicting_id_are_reported():
    one = event()
    corrupted = deepcopy(one); corrupted['outcome'] = 'SUCCEEDED'
    assert analyze(raw(corrupted))['diagnostics'][0]['code'] == 'RUNTIME-EVENT-INVALID'
    two = event(3, one)
    assert analyze(raw(one, two))['diagnostics'][0]['code'] == 'RUNTIME-CHAIN-BROKEN'
    two = event(2, one, eventId=one['eventId'])
    assert analyze(raw(one, two))['diagnostics'][0]['code'] == 'RUNTIME-EVENT-ID-CONFLICT'


def test_window_and_subject_are_filtered_after_chain_validation():
    old = event(occurredAt='2026-10-08T18:00:00Z')
    foreign = event(2, old, subjectRef='urn:another:process')
    actual = event(3, foreign)
    result = analyze(raw(old, foreign, actual))
    assert result['outsideWindow'] == result['outsideSubject'] == 1
    assert result['uniqueFailures'] == 1
    assert not result['diagnostics']


def test_missing_mapping_is_visible_not_an_invented_standard():
    result = analyze(raw(event(code='WMX-NEW-FAILURE')))
    assert result['unclassifiedFailures'] == 1
    assert result['groups'][0]['standardCandidates'] == []


def test_pin_and_unknown_rule_rejected_before_ingestion():
    with pytest.raises(ContractError, match='digest'):
        analyze_events(b'', contract=CONTRACT, contract_sha256='0'*64, rules={},
                       stream='willmux-nl', subject_prefix='urn:willmux:', window_start=START, window_end=END)
    with pytest.raises(ContractError, match='Unknown'):
        analyze_events(b'', contract=CONTRACT, contract_sha256=PIN,
                       rules={'WMX-NEW-FAILURE': ['wellmanifest/invented']},
                       stream='willmux-nl', subject_prefix='urn:willmux:', window_start=START, window_end=END)


def test_empty_window_never_asserts_absence_or_execution():
    result = analyze(b'')
    assert result['coverage'] == 'observed-window' and result['uniqueFailures'] == 0
    assert any('absence' in text for text in result['limitations'])
    assert result['reportDigest'] == payload_digest({k: v for k, v in result.items() if k != 'reportDigest'})


def test_cli_is_read_only_and_bounded(tmp_path, capsys):
    events, contract, rules = [tmp_path / name for name in ('events.jsonl', 'contract.json', 'rules.json')]
    events.write_bytes(raw(event())); contract.write_bytes(CONTRACT); rules.write_bytes(canonical_bytes(RULES))
    args = ['--events', str(events), '--contract', str(contract), '--contract-sha256', PIN,
            '--rules', str(rules), '--stream', 'willmux-nl', '--subject-prefix', 'urn:willmux:', '--end', END]
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)['uniqueFailures'] == 1
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    assert main(args + ['--since-hours', 'nan']) == 2
    assert 'refused' in capsys.readouterr().err
    link = tmp_path / 'link'; link.symlink_to(events)
    args[1] = str(link)
    assert main(args) == 2


def test_stale_telemetry_is_visible_when_window_is_empty():
    value = event(occurredAt='2026-10-08T18:30:00Z')
    result = analyze(raw(value))
    assert result['activity'] == 'no-events-in-window'
    assert result['latestScopedEventAt'] == value['occurredAt']
    assert result['outsideWindow'] == 1


def test_claim_with_wrong_correlation_is_not_a_repair_attempt():
    failure = event()
    repair = event(2, failure, eventType='remediation_completed', severity='INFO', code=None,
                   outcome='SUCCEEDED', causationId=failure['eventId'], correlationId='unrelated',
                   occurredAt='2026-10-08T19:20:00Z')
    assert analyze(raw(failure, repair))['groups'][0]['remediationAttempts'] == 0


@pytest.mark.parametrize('schemas', [None, [], {'event': {}}, {'event': {'type': 'object'}}])
def test_incompatible_contract_is_refused(schemas):
    contract = canonical_bytes({'schema': 'wellmanifest.logs/contract-bundle/v1', 'schemas': schemas})
    with pytest.raises(ContractError):
        analyze_events(b'', contract=contract, contract_sha256=hashlib.sha256(contract).hexdigest(),
                       rules={}, stream='willmux-nl', subject_prefix='urn:willmux:',
                       window_start=START, window_end=END)
