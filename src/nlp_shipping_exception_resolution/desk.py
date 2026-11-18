from collections import defaultdict


class ParcelLineage:
    def __init__(self, parcels):
        self.original = {item['id']: item['replacement_for'] or item['id'] for item in parcels}
        if any(original not in self.original or self.original[original] != original for original in self.original.values()):
            raise ValueError('替换件须指向已登记的原件')


class CarrierTimeline:
    def __init__(self, scans):
        self.events = defaultdict(list)
        for scan in scans:
            self.events[scan['package']].append(scan)

    def delivered(self, parcel):
        events = self.events[parcel]
        return bool(events) and max(events, key=lambda scan: scan['time'])['event'] == 'delivered'


class FulfilmentDesk:
    def __init__(self, lineage, timeline, actions):
        self.lineage = lineage
        self.timeline = timeline
        self.actions = actions

    def plan(self):
        complete = {original for parcel, original in self.lineage.original.items() if self.timeline.delivered(parcel)}
        pending = set(self.lineage.original.values()) - complete
        followup = []
        for action in self.actions:
            original = self.lineage.original[action['package']]
            if original in complete and action['status'] == 'planned':
                followup.append({'id': action['id'], 'next': '取消待发'})
            elif original in complete and action['status'] == 'in_transit':
                followup.append({'id': action['id'], 'next': '协调在途件'})
        return {'whole_order_delivered': not pending, 'pending': sorted(pending), 'actions': followup}


def assess(case, registry):
    desk = FulfilmentDesk(ParcelLineage(registry['packages']), CarrierTimeline([*registry['scans'], *case['scans']]), registry['actions'])
    return desk.plan()
