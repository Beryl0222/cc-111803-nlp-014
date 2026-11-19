"""跨语种扫描备注与客服消息的证据分析。

设计原则：
- 只按包裹号字面出现归属文本，禁止按近似文案或最新号码合并；
- 交接（handed over / 改派）不等于实地送达（delivered / 签收）；
- 无法确认所指箱件的记录进入 unresolved，交值班客服人工确认；
- 每条结论都带 record_id，原文由 ledger 保留。
"""

import re
from dataclasses import dataclass, field

from .text import normalize_text

# 事件规则按特异性排序：先匹配长词组，避免 accepted 被 request 提前吞掉。
# replacement / 替换件 与 handed over / 交接 属于不同事件，分别标注。
# 英文一律用词边界匹配，避免 misdelivered 误命中 delivered；中文按子串匹配。
EVENT_RULES = (
    ('redirect_accepted', ('redirection request accepted', 'redirect accepted',
                           '改派请求已接受', '改派已接受', '承运商接受')),
    ('redirect_requested', ('redirection request', 'redirect request',
                            '提出改派', '申请改派', '改派请求')),
    ('handed_over', (r'\breplacement handed over\b', r'\bhanded over\b', r'\bhandover\b',
                     '交接', '改派')),
    ('misdelivered', (r'\bmisdelivered\b', r'\bmis-delivery\b', r'\bwrongly delivered\b',
                      '错投', '误投')),
    ('delivered', (r'\bdelivered\b', r'\bsigned\b', '签收', '送达', '送到')),
    ('replacement', (r'\breplacement parcel\b', r'\breplacement package\b',
                     r'\breplacement part\b', r'\breplacement\b',
                     '替换件', '补寄件', '补件')),
    ('in_transit', (r'\bin transit\b', r'\bin-transit\b', r'\bon the way\b', '在途')),
)


def _phrase_present(phrase, folded):
    if phrase.startswith('\\b') or phrase.endswith('\\b'):
        return re.search(phrase, folded) is not None
    return phrase in folded


@dataclass(frozen=True)
class TextEvidence:
    record_id: str
    source: str
    revision: int
    text: str
    events: tuple = ()
    parcels: tuple = ()
    attributed: bool = True
    caution: str | None = None
    unresolved_reason: str | None = None


@dataclass
class EvidenceLedger:
    records: list = field(default_factory=list)

    def by_id(self, record_id):
        for record in self.records:
            if record.record_id == record_id:
                return record
        return None


def classify_events(text):
    """返回文本中可识别的事件标签元组，去重并保持规则顺序。

    承运商已接受（accepted）隐含请求已提出，不再重复标注 requested，
    以保留“提出改派”与“承运商接受”两个阶段的区分。
    """
    folded = normalize_text(text).casefold()
    labels = []
    for label, phrases in EVENT_RULES:
        if label == 'redirect_requested' and 'redirect_accepted' in labels:
            continue
        # 错投表述（含 wrongly delivered）不计签收，避免再命中 delivered。
        if label == 'delivered' and 'misdelivered' in labels:
            continue
        if any(_phrase_present(phrase, folded) for phrase in phrases):
            labels.append(label)
    return tuple(labels)


def analyze_record(record, known_parcels):
    """分析单条文本记录。

    known_parcels 为登记在册的全部包裹号（原件与替换件）。
    文本中出现的未知包裹号同样不做归属，避免按近似名称合并。
    """
    text = record['text']
    folded = normalize_text(text).casefold()
    events = classify_events(text)
    mentioned = tuple(pid for pid in known_parcels if pid.casefold() in folded)
    # 找出形如 PKG-? 的包裹号写法，其中未登记的号码一律视为归属不明。
    unknown_mentions = tuple(
        sorted({token.upper() for token in re.findall(r'pkg-[a-z0-9]+', folded)
                if token.upper() not in set(known_parcels)})
    )

    attributed = bool(mentioned) and not unknown_mentions
    caution = None
    unresolved_reason = None

    if not events:
        # 无运输事件词但归属明确的记录（如客服对话）保留在台账中，不隔离；
        # 只有连箱件都指不出的记录才需要人工确认归属。
        if not mentioned or unknown_mentions:
            unresolved_reason = '未识别出可归类的运输事件，且无法对应箱件，归属待值班客服确认'
    elif unknown_mentions:
        unresolved_reason = (f"出现未登记包裹号 {', '.join(unknown_mentions)}，"
                             '不能按近似文案并入已知箱件，归属待值班客服确认')
    elif not mentioned:
        unresolved_reason = '未指明任何箱件，无法确认所指包裹，归属待值班客服确认'
    elif len(mentioned) > 1:
        unresolved_reason = '同条记录提及多个箱件且无法逐句拆分，归属待值班客服确认'
        attributed = False

    if 'handed_over' in events:
        caution = '交接/改派扫描不等于实地送达，不能据此签收或结束找件'

    return TextEvidence(
        record_id=record['record_id'],
        source=record['source'],
        revision=record['revision'],
        text=text,
        events=events,
        parcels=mentioned,
        attributed=attributed,
        caution=caution,
        unresolved_reason=unresolved_reason,
    )


def build_ledger(records, known_parcels):
    return EvidenceLedger([analyze_record(record, known_parcels) for record in records])
