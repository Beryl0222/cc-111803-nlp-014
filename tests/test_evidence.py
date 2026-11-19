from nlp_shipping_exception_resolution.evidence import analyze_record, build_ledger, classify_events

KNOWN = ['PKG-A', 'PKG-B', 'PKG-C']


def _rec(record_id, text, source='carrier-en'):
    return {'record_id': record_id, 'source': source, 'revision': 1, 'text': text}


def test_english_event_classification_distinguishes_handover_from_delivery():
    assert classify_events('Replacement handed over.') == ('handed_over', 'replacement')
    assert classify_events('Redirection request accepted.') == ('redirect_accepted',)
    assert classify_events('Redirection request submitted.') == ('redirect_requested',)
    assert 'delivered' not in classify_events('Replacement handed over.')


def test_misdelivered_is_not_a_delivery_event():
    assert classify_events('PKG-A misdelivered at depot.') == ('misdelivered',)
    assert 'delivered' not in classify_events('Wrongly delivered to neighbour.')
    assert 'delivered' in classify_events('PKG-B delivered at 15:00.')


def test_chinese_event_classification_maps_to_same_labels():
    assert classify_events('订单 55 部分已改派，原件仍在处理。') == ('handed_over',)
    assert classify_events('已有一件签收；替换件 PKG-C 在途。') == (
        'delivered', 'replacement', 'in_transit')
    assert classify_events('PKG-A 错投') == ('misdelivered',)
    assert 'delivered' not in classify_events('PKG-A 改派')


def test_known_parcel_is_attributed_but_handover_keeps_caution():
    evidence = analyze_record(_rec('t', 'PKG-A replacement handed over'), KNOWN)
    assert evidence.attributed
    assert evidence.parcels == ('PKG-A',)
    assert evidence.caution is not None
    assert evidence.unresolved_reason is None


def test_unattributed_handover_is_quarantined_not_merged():
    evidence = analyze_record(_rec('t', 'Replacement handed over.'), KNOWN)
    assert not evidence.attributed
    assert evidence.unresolved_reason is not None
    assert evidence.caution is not None


def test_unknown_parcel_id_is_quarantined():
    evidence = analyze_record(_rec('t', 'PKG-Z delivered at depot'), KNOWN)
    assert not evidence.attributed
    assert 'PKG-Z' in evidence.unresolved_reason or evidence.unresolved_reason


def test_multi_parcel_text_without_clause_split_is_quarantined():
    evidence = analyze_record(_rec('t', 'PKG-A 与 PKG-B 已改派'), KNOWN)
    assert not evidence.attributed
    assert set(evidence.parcels) == {'PKG-A', 'PKG-B'}
    assert evidence.unresolved_reason is not None


def test_ledger_keeps_every_record_for_provenance():
    ledger = build_ledger([_rec('t1', 'PKG-A delivered'), _rec('t2', '未知情况')], KNOWN)
    assert {row.record_id for row in ledger.records} == {'t1', 't2'}
    assert ledger.by_id('t1').attributed
