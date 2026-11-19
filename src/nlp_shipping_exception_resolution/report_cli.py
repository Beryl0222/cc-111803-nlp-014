import argparse
import json
from pathlib import Path

from .report import build_report


def load_report(case_path, registry_path, records_path):
    case = json.loads(Path(case_path).read_text(encoding='utf-8'))
    registry = json.loads(Path(registry_path).read_text(encoding='utf-8'))
    records = json.loads(Path(records_path).read_text(encoding='utf-8'))
    return build_report(case, registry, records)


def main():
    parser = argparse.ArgumentParser(description='值班客服跨语种核对报告（带原文依据）')
    parser.add_argument('--case', type=Path, default=Path('fixtures/work.json'))
    parser.add_argument('--registry', type=Path, default=Path('fixtures/business.json'))
    parser.add_argument('--records', type=Path, default=Path('fixtures/records.json'))
    args = parser.parse_args()
    try:
        result = load_report(args.case, args.registry, args.records)
    except (OSError, KeyError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
