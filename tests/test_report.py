import copy
from pathlib import Path

from nlp_shipping_exception_resolution.report import build_report
from nlp_shipping_exception_resolution.report_cli import load_report

FIXTURE = Path(__file__).parents[1] / 'fixtures'

REGISTRY = {
    'order': 'ORD-55',
    'packages': [
        {'id': 'PKG-A', 'replacement_for': None},
        {'id': 'PKG-B', 'replacement_for': None},
        {'id': 'PKG-C', 'replacement_for': 'PKG-A'},
    ],
    'scans': [
        {'package': 'PKG-B', 'event': 'delivered', 'time': '2026-05-12T15:00'},
        {'package': 'PKG-A', 'event': 'misdelivered', 'time': '2026-05-12T11:00'},
    ],
    'actions': [{'id': 'RESHIP-4', 'package': 'PKG-C', 'status': 'in_transit'}],
}

CASE = {'scans': [{'package': 'PKG-A', 'event': 'delivered', 'time': '2026-05-12T17:00'}]}

RECORDS = [
    {'record_id': 'track-a', 'source': 'carrier-en', 'revision': 1,
     'text': 'PKG-A misdelivered at depot. Redirection request accepted.'},
    {'record_id': 'track-b', 'source': 'carrier-zh', 'revision': 1,
     'text': '订单 55 已有一件签收；替换件 PKG-C 在途。'},
    {'record_id': 'support-a', 'source': 'customer-support', 'revision': 1,
     'text': '客户问整单是否到齐，客服回复正在找回 PKG-A。'},
    {'record_id': 'scan-en-late', 'source': 'carrier-en', 'revision': 1,
     'text': 'Replacement handed over.'},
    {'record_id': 'scan-zh-late', 'source': 'carrier-zh', 'revision': 1,
     'text': '订单 55 部分已改派，原件仍在处理。'},
]


def _report():
    return build_report(copy.deepcopy(CASE), copy.deepcopy(REGISTRY), copy.deepcopy(RECORDS))


def test_late_delivery_scan_completes_whole_order_but_keeps_replacement_followup():
    report = _report()
    assert report['whole_order_delivered'] is True
    assert report['pending_originals'] == []
    action = report['remedy_actions'][0]
    assert action['action_id'] == 'RESHIP-4'
    assert action['next_step'] == '补件已在途，需另行协调拦截或退回'


def test_misdelivered_scan_does_not_count_as_signed_before_late_scan():
    registry = copy.deepcopy(REGISTRY)
    report = build_report({'scans': []}, registry, copy.deepcopy(RECORDS))
    assert report['whole_order_delivered'] is False
    assert report['pending_originals'] == ['PKG-A']
    pkg_a = next(row for row in report['packages'] if row['package'] == 'PKG-A')
    assert pkg_a['delivery_state'] == '错投不计签收'
    assert report['remedy_actions'][0]['next_step'] == '原件仍缺，继续推进补救'


def test_replacement_delivery_only_covers_its_own_original():
    registry = copy.deepcopy(REGISTRY)
    case = {'scans': [
        {'package': 'PKG-A', 'event': 'misdelivered', 'time': '2026-05-12T11:00'},
        {'package': 'PKG-C', 'event': 'delivered', 'time': '2026-05-12T18:00'},
    ]}
    report = build_report(case, registry, copy.deepcopy(RECORDS))
    assert report['whole_order_delivered'] is True
    assert report['pending_originals'] == []
    pkg_c = next(row for row in report['packages'] if row['package'] == 'PKG-C')
    assert pkg_c['delivery_state'] == '已实地送达'


def test_duplicate_scans_are_kept_once_and_earlier_late_scan_does_not_overwrite():
    registry = copy.deepcopy(REGISTRY)
    registry['scans'].append({'package': 'PKG-A', 'event': 'delivered',
                              'time': '2026-05-12T17:00'})
    report = build_report(copy.deepcopy(CASE), registry, copy.deepcopy(RECORDS))
    pkg_a = next(row for row in report['packages'] if row['package'] == 'PKG-A')
    delivered_basis = [b for b in pkg_a['basis'] if b['type'] == 'scan'
                       and b['event'] == 'delivered']
    assert len(delivered_basis) == 1


def test_ambiguous_bilingual_records_are_quarantined_with_record_ids():
    report = _report()
    quarantined = {row['record_id']: row for row in report['unresolved']}
    # track-a 归属明确（含 handover 谨慎提示）；两条无归属改派/交接记录被隔离。
    assert 'track-a' not in quarantined
    assert set(quarantined) == {'scan-en-late', 'scan-zh-late'}
    for row in quarantined.values():
        assert row['instruction']
    # 归属不明的记录不得出现在任何包裹的交付依据里。
    for pkg in report['packages']:
        ids = {b.get('record_id') for b in pkg['basis'] if b['type'] == 'text'}
        assert not ids & {'scan-en-late', 'scan-zh-late'}


def test_track_a_accepted_redirection_is_attributed_to_pkg_a_with_handover_caution():
    report = _report()
    track_a = next(row for row in report['evidence_ledger'] if row['record_id'] == 'track-a')
    assert track_a['attributed']
    assert track_a['parcels'] == ['PKG-A']
    assert 'redirect_accepted' in track_a['events']
    assert 'misdelivered' in track_a['events']


def test_every_conclusion_carries_its_own_basis():
    report = _report()
    assert report['conclusions']
    for conclusion in report['conclusions']:
        assert conclusion['basis'], conclusion['statement']


def test_customer_communications_preserve_original_text():
    report = _report()
    comms = report['customer_communications']
    assert len(comms) == 1
    assert comms[0]['record_id'] == 'support-a'
    assert comms[0]['text'] == '客户问整单是否到齐，客服回复正在找回 PKG-A。'


def test_cli_loads_fixture_end_to_end():
    report = load_report(FIXTURE / 'work.json', FIXTURE / 'business.json',
                         FIXTURE / 'records.json')
    assert report['order'] == 'ORD-55'
    assert report['whole_order_delivered'] is True
