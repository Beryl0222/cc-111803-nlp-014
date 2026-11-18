import json
from pathlib import Path

def load_facts(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def summarize(facts):
    delivered = sorted({row['package'] for row in facts['scans'] if row['event'] == 'delivered'})
    return {'delivered': delivered, 'open_actions': [row['id'] for row in facts['actions'] if row['status'] != 'complete']}
