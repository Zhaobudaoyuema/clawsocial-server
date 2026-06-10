"""In-memory entity preview text (matches finish-stage entity replacement)."""
from __future__ import annotations

import copy

from app.deid.engine.plan import ReplacementPlan, build_plan_from_job_entities


def assign_placeholder_map(
    entities: list[dict],
    *,
    type_prefix_map: dict[str, str],
) -> dict[int, str]:
    """
    Assign placeholders using the same sort order as service._assign_placeholders.
    Mutates entity dicts in place (sets placeholder field).
    Returns {entity_id: placeholder} for rows with id.
    """
    active = [e for e in entities if not e.get("is_excluded")]
    sorted_ents = sorted(
        active,
        key=lambda e: (e.get("entity_type", ""), e.get("canonical_name", "")),
    )
    counters: dict[str, int] = {}
    result: dict[int, str] = {}
    for ent in sorted_ents:
        prefix = type_prefix_map.get(ent.get("entity_type", ""), "实体")
        counters[prefix] = counters.get(prefix, 0) + 1
        ph = f"[{prefix}_{counters[prefix]}]"
        ent["placeholder"] = ph
        eid = ent.get("id")
        if eid is not None:
            result[int(eid)] = ph
    return result


def build_preview_text(
    sample: str,
    entities: list[dict],
    pattern_rules: list[dict],
    whitelist: list[dict],
    *,
    type_prefix_map: dict[str, str],
) -> str:
    """Apply entity replacement plan to plain text without writing docx."""
    ents = copy.deepcopy(entities)
    assign_placeholder_map(ents, type_prefix_map=type_prefix_map)
    plan = build_plan_from_job_entities(ents, pattern_rules, whitelist, sample)
    lines: list[str] = []
    for line in sample.split("\n"):
        new_line, _ = plan.apply_to_text(line)
        lines.append(new_line)
    return "\n".join(lines)


def build_preview_plan(
    entities: list[dict],
    pattern_rules: list[dict],
    whitelist: list[dict],
    sample_text: str,
    *,
    type_prefix_map: dict[str, str],
) -> ReplacementPlan:
    """Build replacement plan with pre-assigned placeholders (for finish parity)."""
    ents = copy.deepcopy(entities)
    assign_placeholder_map(ents, type_prefix_map=type_prefix_map)
    return build_plan_from_job_entities(ents, pattern_rules, whitelist, sample_text)
