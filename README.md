# 跨语种运输异常的责任与补救进度

本地文本工作区用于保存跨语种异常语义和代码映射相关的合成记录，并提供基础规范化和词项查看能力。

## 环境

需要 Python 3.11 或更新版本。运行程序仅使用 Python 标准库。测试依赖固定为 pytest 8.3.4，可执行 `python -m pip install -r requirements-dev.txt` 安装。

## 运行

运行 `PYTHONPATH=src python -m nlp_shipping_exception_resolution.desk_cli` 用登记的扫描核对原件、替换件和整单到达状态。扫描按发生时点比较。错投不计签收。替换件的签收只覆盖其关联原件。

运行 `PYTHONPATH=src python -m nlp_shipping_exception_resolution.report_cli` 生成值班客服核对报告：在结构化扫描之外，将中英文扫描备注和客服消息按原文分析后作为证据并入。报告区分提出改派、承运商接受、交接和实地送达；“handed over/改派/交接”不等于签收，只按包裹号字面出现归属，未指明箱件或出现未登记号码的记录进入 `unresolved` 交人工确认，不按最新号码或近似文案合并。每项结论的 `basis` 标注所用扫描（含时间与来源文件）或文本 `record_id`，原文统一保留在 `evidence_ledger` 与 `customer_communications` 中。整单仅在每个原件由本件或其有效补件完成交付时判为到齐，并给出在途补件的协调口径。

从项目根目录执行 `PYTHONPATH=src python -m nlp_shipping_exception_resolution.cli ingest fixtures/records.json` 导入样例，随后执行 `PYTHONPATH=src python -m nlp_shipping_exception_resolution.cli list` 查看记录。工作数据写入 `var/records.json`。业务查询使用 fixtures/business.json 中的初始资料，约定见 fixtures/business-contract.md。执行 PYTHONPATH=src python -m nlp_shipping_exception_resolution.cli business 可查看当前业务目录结果。

样例为本地合成文本。记录包含来源、修订号和原文，当前工作区对空白做统一处理，并提供字符及英文词项切分。

## 测试

执行 `python -m pytest -q` 检查规范化、记录持久化和来源筛选。
