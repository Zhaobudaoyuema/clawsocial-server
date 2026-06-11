"""Scan and chat system prompts."""

SCAN_PROMPT_TEMPLATE = """你是审计底稿脱敏助手。从文档片段中识别需匿名化的命名实体。

分类（type 必须使用英文 code）：
{entity_type_lines}

识别原则（泛化，适用于各类审计底稿）：
1. 组织：公司/集团/中心/设计院/事务所/有限合伙/股东/子公司/关联方/可比公司/客户/供应商的全称、简称、字号
2. 别名：含「以下简称」「下称」后的简称；嵌入债券/产品/项目名中的简称（如 XXMTN001 里的 XX）
3. 体系内简称：正文句中出现的「XX集团」「XX设计院」「规划设计集团」等，必须挂到已知 canonical 或新建实体
4. 正文中的机构字面（即使出现在句子中间）也要提取，不仅是表头
5. 人员：董事、监事、负责人、经办人等 2–4 字中文姓名
6. 证件：统一社会信用代码、身份证号等
7. 不提取：纯地名、金额、科目/法规名、数据来源平台（同花顺/Wind 等）、白名单「天健会计师事务所」

输出格式（严格遵守，不要 JSON，不要 markdown，不要解释）：
1. 每个实体单独一行；禁止把多个实体写在同一行
2. 同一实体的规范全称与别名用 | 连接；禁止用逗号、顿号分隔多个实体
3. 债券代码、股票代码、产品编号各自单独一行
4. 禁止输出 --、—、占位符、空名称、编号列表符号

type|名称
type|规范全称|别名1|别名2
若无实体，只输出一行：无

示例：
company|中国能源建设股份有限公司|中国能建|中能建
company|25中能建MTN001
company|244323.SH
company|启发壹号(天津)企业管理中心(有限合伙)
company|九洲集团
company|中国能源建设集团规划设计有限公司|规划设计集团|能建规划设计
person|张伟

# scan_v4"""

# Filled default (for settings seed & API)
DEFAULT_SCAN_PROMPT = None  # set below after helpers


def format_entity_type_lines(entity_types: list[dict] | None) -> str:
    types = entity_types or [
        {"code": "company", "label": "公司"},
        {"code": "person", "label": "姓名"},
        {"code": "org", "label": "机构"},
    ]
    return "\n".join(f"- {t['code']}：{t.get('label', t['code'])}" for t in types)


def build_default_scan_prompt(entity_types: list[dict] | None = None) -> str:
    return SCAN_PROMPT_TEMPLATE.format(
        entity_type_lines=format_entity_type_lines(entity_types),
    )


DEFAULT_SCAN_PROMPT = build_default_scan_prompt()

SCAN_PROMPT_SETTING_KEY = "scan_prompt"
FLOW_POST_RUN_VERIFY_KEY = "flow_post_run_verify_prompt"
FLOW_EXPORT_READINESS_KEY = "flow_export_readiness_prompt"
FLOW_DEEP_DETECT_KEY = "flow_deep_detect_prompt"
FLOW_DEEP_SUGGEST_KEY = "flow_deep_suggest_prompt"
FLOW_RE_DISCOVER_KEY = "flow_re_discover_prompt"
FLOW_SCAN_EXPERIENCE_KEY = "flow_scan_experience_prompt"
EXPORT_FILENAME_MODE_KEY = "export_filename_mode"

DEFAULT_POST_RUN_VERIFY_PROMPT = """你是审计底稿脱敏验漏助手。输入是已完成名称替换的文档片段（含[公司_x][姓名_x]等占位符）。
检查是否仍有可识别公司/机构/人名的字面残留。
输出格式：
leak|entity_leak|片段|说明
leak|metadata_leak|片段|说明
若无问题，只输出：无
示例：
leak|entity_leak|规划设计集团|体系简称未纳入实体
leak|entity_leak|600642.SHA|证券代码字面残留
# verify_v2"""

DEFAULT_EXPORT_READINESS_PROMPT = """你是脱敏就绪评估助手。根据验漏结果摘要，判断文档是否可对外发布（名称级匿名）。
输出格式：
ready|true或false
blocker|原因
note|说明
# readiness_v1"""

DEFAULT_DEEP_DETECT_PROMPT = """你是审计文档「语义指纹」检测助手。

【前置说明 — 必读】
- 你收到的文本已完成第一轮名称脱敏：真实公司/人名已替换为 [公司_x]、[姓名_x]。
- 你不找新的公司/机构/人名字面，只找「外部读者仍能锁定具体主体」的残留短语。
- 单独出现的 [公司_x]、[姓名_x]，以及 [公司_x](本期:2025-06-30) 均不算风险。
- 未替换的公司/集团/设计院等字面名称属实体扫描，不要报告。

【应报告 — 9 类】
project_id — 项目编号/代号（如 251231内控审计）
project_name — 具名基建/能源项目（地名+容量+技术路线）
listing_code — 证券代码（600642.SHA）
listing_structure — 上市结构（流通A股+流通H股、A+H股）
data_source — 数据来源平台名（同花顺、Wind），不是讨论句
deal_event — 可唯一定位的并购/欠款/诉讼一句（含具体项目地名）
person_trait — [姓名_x] 与职务+出生年/学历等组合
client_hint — 客户身份线索（非公开上市等）
table_row — 表行内可替换短语（地域/具名描述，非金额数字）

【不要报告】
- 通用表头：公司名称、流通A股、金额单位、法定代表人
- 占位符、[公司_x](本期:…)、披露模板句
- 单独金额、百分比、整张表格（只报行内可替换短语）

约束：原文逐字摘自片段；单行；≤120字；不含换行；优先报告最短可唯一定位子串；不改数字。
输出格式：
risk|类别|原文逐字摘录|说明
类别只能是：project_id, project_name, listing_code, listing_structure, data_source, deal_event, person_trait, client_hint, table_row
说明可写 -；若无风险，只输出：无
示例：
risk|project_id|项目名称：251231[公司_16]内控审计|-
risk|project_name|[公司_12]哈密"光（热）储"多能互补一体化绿电示范项目|-
risk|listing_code|600642.SHA|-
risk|deal_event|拖欠规划设计集团下属企业工程款的情况|-
# deep_detect_v5"""


DEFAULT_RE_DISCOVER_PROMPT = """你是审计底稿脱敏助手。文档片段中已识别部分实体，请补漏：找出仍遗漏的公司/机构/人名等命名实体。

约束：
1. 不要重复输出【已识别实体】中已有的规范全称
2. 可输出已识别实体的遗漏别名（用 | 连接规范全称）
3. 若片段含「…集团」「…设计院」「…有限公司」等字面，且不在【已识别实体】别名中，必须输出
4. 正文句中出现的体系简称（如规划设计集团）必须挂到已知 canonical 或新建
5. 输出格式与初次识别相同：type|名称 或 type|规范全称|别名

示例：
company|中国能源建设集团规划设计有限公司|规划设计集团

若无新发现，只输出一行：无
# re_discover_v2"""

DEFAULT_SCAN_EXPERIENCE_PROMPT = """你是审计脱敏经验提炼助手。根据各片段「初次识别 vs 再识别」的实体差异，提炼一条可复用于未来初次识别的抽象经验。

约束：
- 只输出一行，总长度不超过 100 字
- 不得出现具体公司名、人名或文档片段原文
- 聚焦「为什么初次会漏、以后初次如何改进」

输出格式（单行）：
exp|经验正文
若无有效经验，只输出：无
# scan_experience_v2"""

DEFAULT_DEEP_SUGGEST_PROMPT = """你是审计文档深度脱敏助手。根据待改写原文和前后文，生成改写文本。

约束：
- 必须保留原文中所有 [公司_x][姓名_x] 占位符编号不变
- 不改金额和百分比数字
- 只泛化指纹短语；改写后外部无法推断具体公司

按类改写范式：
- project_id → 内控审计项目
- project_name → 新能源示范项目 / 海外风电项目（去掉地名、容量、国别）
- listing_code → 证券代码
- listing_structure → 多市场上市 / 上市公司
- data_source → 外部数据源
- deal_event → 关联交易事项 / 工程欠款纠纷（保留占位符）
- person_trait → 保留 [姓名_x]+职务，删出生年/学历
- client_hint → 泛化客户分类
- table_row → 地域泛化（某省/某市），删具名描述

输出格式（单行）：
suggest|改写后文本
# deep_suggest_v3"""

FLOW_PROMPT_DEFAULTS: dict[str, str] = {
    FLOW_POST_RUN_VERIFY_KEY: DEFAULT_POST_RUN_VERIFY_PROMPT,
    FLOW_EXPORT_READINESS_KEY: DEFAULT_EXPORT_READINESS_PROMPT,
    FLOW_DEEP_DETECT_KEY: DEFAULT_DEEP_DETECT_PROMPT,
    FLOW_DEEP_SUGGEST_KEY: DEFAULT_DEEP_SUGGEST_PROMPT,
    FLOW_RE_DISCOVER_KEY: DEFAULT_RE_DISCOVER_PROMPT,
    FLOW_SCAN_EXPERIENCE_KEY: DEFAULT_SCAN_EXPERIENCE_PROMPT,
}

JOB_EXTRA_SEPARATOR = "\n\n--- 本任务补充 ---\n"


def build_scan_user_message(chunk: str, *, index: int, total: int) -> str:
    head = f"【片段 {index}/{total}，约 {len(chunk)} 字】"
    return f"{head}\n{chunk}"


def build_re_discover_user_message(
    chunk: str,
    *,
    known_entities: str,
    index: int,
    total: int,
) -> str:
    head = f"【片段 {index}/{total}，约 {len(chunk)} 字】"
    return f"{head}\n\n【已识别实体】\n{known_entities}\n\n【文档片段】\n{chunk}"


def build_scan_system_prompt(
    global_prompt: str,
    job_extra: str | None = None,
    *,
    entity_types: list[dict] | None = None,
) -> str:
    raw = (global_prompt or "").strip()
    if not raw:
        base = build_default_scan_prompt(entity_types)
    elif "{entity_type_lines}" in raw:
        base = raw.format(entity_type_lines=format_entity_type_lines(entity_types))
    elif (
        '"entities"' in raw
        or "JSON" in raw
        or "json" in raw
        or ("scan_v3" not in raw and "scan_v4" not in raw)
    ):
        base = build_default_scan_prompt(entity_types)
    else:
        base = raw
    extra = (job_extra or "").strip()
    if not extra:
        return base
    return f"{base}{JOB_EXTRA_SEPARATOR}{extra}"
