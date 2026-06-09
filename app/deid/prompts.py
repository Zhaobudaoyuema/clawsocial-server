"""Scan and chat system prompts."""

SCAN_PROMPT_TEMPLATE = """你是审计底稿脱敏助手。从文档片段中识别需匿名化的命名实体。

分类（type 必须使用英文 code）：
{entity_type_lines}

识别原则（泛化，适用于各类审计底稿）：
1. 组织：公司/集团/中心/事务所/有限合伙/股东/子公司/关联方/可比公司/客户/供应商的全称、简称、字号
2. 别名：含「以下简称」「下称」后的简称；嵌入债券/产品/项目名中的简称（如 XXMTN001 里的 XX）
3. 人员：董事、监事、负责人、经办人等 2–4 字中文姓名
4. 证件：统一社会信用代码、身份证号等
5. 不提取：纯地名、金额、科目/法规名、数据来源平台（同花顺/Wind 等）、白名单「天健会计师事务所」

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
person|张伟

# scan_v3"""

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

CHAT_DEFAULT_SYSTEM = """你是审计底稿阅读助手。请基于用户提供的文档内容（如有）回答问题。
- 只依据文档与对话上下文作答，不要编造事实
- 若文档中无相关信息，请明确说明
- 回答简洁、专业"""

SCAN_PROMPT_SETTING_KEY = "scan_prompt"
JOB_EXTRA_SEPARATOR = "\n\n--- 本任务补充 ---\n"


def build_scan_user_message(chunk: str, *, index: int, total: int) -> str:
    head = f"【片段 {index}/{total}，约 {len(chunk)} 字】"
    return f"{head}\n{chunk}"


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
        or "scan_v3" not in raw
    ):
        base = build_default_scan_prompt(entity_types)
    else:
        base = raw
    extra = (job_extra or "").strip()
    if not extra:
        return base
    return f"{base}{JOB_EXTRA_SEPARATOR}{extra}"
