"""值班客服核对报告：结构化扫描与跨语种文本证据合并出结论。

规则要点（对应业务约定）：
- 扫描按发生时点比较，同一包裹以最晚事件为准；
- 错投（misdelivered）不计签收；
- 替换件签收只覆盖其关联原件，不覆盖其他原件；
- 重复导入的相同扫描（包裹/事件/时间一致）只保留一次；
- 整单到齐仅当每个原件的交付责任由本件或其有效补件完成；
- 文本证据只作佐证与澄清，归属不明的记录不进入任何交付结论。
"""

from .evidence import build_ledger


def _merge_scans(registry_scans, case_scans):
    merged = {}
    for scan, origin in [(row, 'business.json') for row in registry_scans] + \
                        [(row, 'work.json') for row in case_scans]:
        key = (scan['package'], scan['event'], scan['time'])
        merged.setdefault(key, {**scan, 'origins': []})['origins'].append(origin)
    return list(merged.values())


def _lineage(packages):
    original_of = {item['id']: item['replacement_for'] or item['id'] for item in packages}
    for original in original_of.values():
        if original not in original_of or original_of[original] != original:
            raise ValueError('替换件须指向已登记的原件')
    originals = sorted({pid for pid, root in original_of.items() if root == pid})
    return original_of, originals


def _scan_basis(scan):
    return {'type': 'scan', 'package': scan['package'], 'event': scan['event'],
            'time': scan['time'], 'origin': '+'.join(scan['origins'])}


def _text_basis(record):
    return {'type': 'text', 'record_id': record.record_id}


def build_report(case, registry, text_records):
    packages = registry['packages']
    known_parcels = [item['id'] for item in packages]
    original_of, originals = _lineage(packages)
    ledger = build_ledger(text_records, known_parcels)

    scans = _merge_scans(registry.get('scans', []), case.get('scans', []))
    timeline = {}
    for scan in scans:
        timeline.setdefault(scan['package'], []).append(scan)
    for rows in timeline.values():
        rows.sort(key=lambda row: row['time'])

    def latest(parcel):
        rows = timeline.get(parcel, [])
        return rows[-1] if rows else None

    def is_delivered(parcel):
        scan = latest(parcel)
        return scan is not None and scan['event'] == 'delivered'

    # 原件交付责任：本件送达，或其有效补件送达。
    covered = set()
    for parcel in known_parcels:
        if is_delivered(parcel):
            covered.add(original_of[parcel])
    pending = sorted(set(originals) - covered)

    def text_evidence(parcel):
        return [_text_basis(row) for row in ledger.records
                if row.attributed and parcel in row.parcels]

    package_results = []
    for item in packages:
        parcel = item['id']
        scan = latest(parcel)
        scan_list = timeline.get(parcel, [])
        if scan is None:
            state = '无扫描'
        elif scan['event'] == 'delivered':
            state = '已实地送达'
        elif scan['event'] == 'misdelivered':
            state = '错投不计签收'
        else:
            state = f"最晚事件 {scan['event']}，未送达"
        basis = [_scan_basis(row) for row in scan_list] + text_evidence(parcel)
        package_results.append({
            'package': parcel,
            'kind': '原件' if item['replacement_for'] is None else '替换件',
            'replacement_for': item['replacement_for'],
            'delivery_state': state,
            'latest_event': scan['event'] if scan else None,
            'latest_time': scan['time'] if scan else None,
            'basis': basis,
        })

    # 每个原件的责任结论。
    conclusions = []
    for original in originals:
        if is_delivered(original):
            statement = f'{original} 原件已实地送达，交付责任完成'
        else:
            replacements = [pid for pid, root in original_of.items()
                            if root == original and pid != original and is_delivered(pid)]
            if replacements:
                statement = f'{original} 由有效补件 {replacements[0]} 的签收覆盖，交付责任完成'
            else:
                latest_scan = latest(original)
                if latest_scan and latest_scan['event'] == 'misdelivered':
                    statement = f'{original} 仅有错投记录，错投不计签收，仍在找回'
                else:
                    statement = f'{original} 无有效送达，仍缺'
        basis = [_scan_basis(row) for row in timeline.get(original, [])]
        for pid, root in original_of.items():
            if root == original and pid != original:
                basis.extend(_scan_basis(row) for row in timeline.get(pid, []))
        basis.extend(text_evidence(original))
        conclusions.append({'package': original, 'statement': statement, 'basis': basis})

    # 补救动作：原件责任完成后按状态分流；未完成则继续推进。
    actions = []
    for action in registry.get('actions', []):
        parcel = action['package']
        if parcel not in original_of:
            raise ValueError(f"动作 {action['id']} 指向未登记包裹 {parcel}")
        original = original_of[parcel]
        status = action['status']
        if original in covered:
            if status == 'planned':
                next_step = '取消待发补件'
            elif status == 'in_transit':
                next_step = '补件已在途，需另行协调拦截或退回'
            else:
                next_step = '原件责任已完成，动作结案'
        else:
            next_step = '原件仍缺，继续推进补救'
        actions.append({
            'action_id': action['id'], 'package': parcel, 'covers_original': original,
            'status': status, 'next_step': next_step,
            'basis': [{'type': 'action', 'action_id': action['id'], 'status': status}]
                     + [_scan_basis(row) for row in timeline.get(original, [])],
        })

    communications = [{
        'record_id': row.record_id,
        'source': row.source,
        'revision': row.revision,
        'text': row.text,
        'events': list(row.events),
        'parcels': list(row.parcels),
        'attributed': row.attributed,
        'caution': row.caution,
        'unresolved_reason': row.unresolved_reason,
    } for row in ledger.records if 'support' in row.source]

    unresolved = []
    for row in ledger.records:
        # 仅隔离归属不明或“交接≠送达”的记录；不含运输事件的普通客服消息不隔离。
        reason = row.unresolved_reason
        if reason is None and row.caution is not None:
            reason = row.caution
        if reason is None:
            continue
        unresolved.append({
            'record_id': row.record_id, 'source': row.source, 'text': row.text,
            'events': list(row.events), 'parcels': list(row.parcels),
            'attributed': row.attributed, 'reason': reason,
            'instruction': '交值班客服人工确认，确认前不得据此结束找件或合并包裹',
        })

    whole_order = not pending
    conclusions.insert(0, {
        'package': registry.get('order'),
        'statement': '整单到齐：每个原件的交付责任均已完成' if whole_order
        else f"整单未到齐，仍缺：{', '.join(pending)}",
        'basis': [b for row in package_results for b in row['basis']
                  if b['type'] == 'scan'],
    })

    return {
        'order': registry.get('order'),
        'whole_order_delivered': whole_order,
        'pending_originals': pending,
        'packages': package_results,
        'remedy_actions': actions,
        'customer_communications': communications,
        'customer_guidance': (
            '可告知客户整单已到齐；同时告知在途补件的协调安排'
            if whole_order else
            f"不可告知整单到齐，仍缺 {', '.join(pending)}，按既有找回口径回复客户"
        ),
        'unresolved': unresolved,
        'conclusions': conclusions,
        'evidence_ledger': [{
            'record_id': row.record_id, 'source': row.source,
            'revision': row.revision, 'text': row.text,
            'events': list(row.events), 'parcels': list(row.parcels),
            'attributed': row.attributed, 'caution': row.caution,
            'unresolved_reason': row.unresolved_reason,
        } for row in ledger.records],
    }


def assess_with_evidence(case, registry, text_records):
    return build_report(case, registry, text_records)
