#!/usr/bin/env python3
"""Idempotent seed for deid client packs (SPIC, CEEC, general_finance)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, engine
from app import models  # noqa: F401 — ensure Base metadata
from app.models_deid import (
    DeidClientPack,
    DeidEntity,
    DeidEntityAlias,
    DeidPatternRule,
    DeidWhitelistTerm,
)
import app.models_deid  # noqa: F401

models.Base.metadata.create_all(bind=engine)


def _get_or_create_pack(db, code: str, name: str, desc: str, default: bool) -> DeidClientPack:
    p = db.query(DeidClientPack).filter(DeidClientPack.code == code).first()
    if p:
        return p
    p = DeidClientPack(code=code, name=name, description=desc, is_default=default, is_active=True)
    db.add(p)
    db.flush()
    return p


def _ensure_entity(db, pack_id: int, canonical: str, etype: str, prefix: str, aliases: list[str]) -> None:
    ent = (
        db.query(DeidEntity)
        .filter(DeidEntity.pack_id == pack_id, DeidEntity.canonical_name == canonical)
        .first()
    )
    if not ent:
        ent = DeidEntity(
            pack_id=pack_id,
            entity_type=etype,
            canonical_name=canonical,
            placeholder_prefix=prefix,
            source="seed",
        )
        db.add(ent)
        db.flush()
    seen: set[str] = set()
    for a in aliases:
        if not a.strip():
            continue
        key = a.casefold()
        if key in seen:
            continue
        seen.add(key)
        exists = (
            db.query(DeidEntityAlias)
            .filter(DeidEntityAlias.entity_id == ent.id, DeidEntityAlias.alias_text == a)
            .first()
        )
        if not exists:
            db.add(
                DeidEntityAlias(
                    entity_id=ent.id,
                    alias_text=a,
                    added_from="seed",
                )
            )


def _ensure_pattern(
    db,
    name: str,
    regex: str,
    etype: str,
    prefix: str,
    pack_id: int | None,
) -> None:
    exists = db.query(DeidPatternRule).filter(DeidPatternRule.name == name).first()
    if not exists:
        db.add(
            DeidPatternRule(
                name=name,
                regex_pattern=regex,
                entity_type=etype,
                placeholder_prefix=prefix,
                pack_id=pack_id,
                priority=10,
            )
        )


def _seed_ceec(db, ceec: DeidClientPack) -> None:
    """中国能源建设集团有限公司（中国能建）体系."""
    ceec_group_aliases = [
        "中国能源建设集团有限公司",
        "中国能源建设集团",
        "中国能建",
        "中国能建集团",
        "中国 能建",
        "ENERGY CHINA",
    ]
    _ensure_entity(
        db,
        ceec.id,
        "中国能源建设集团有限公司",
        "company",
        "公司",
        ceec_group_aliases,
    )

    _ensure_entity(
        db,
        ceec.id,
        "中国能源建设股份有限公司",
        "company",
        "公司",
        [
            "中国能源建设股份有限公司",
            "中国能源建设",
            "601868",
            "601868.SH",
            "3996.HK",
            "03996.HK",
        ],
    )

    subsidiaries = [
        ("中国葛洲坝集团有限公司", ["葛洲坝集团", "中国葛洲坝集团"]),
        (
            "中国葛洲坝集团股份有限公司",
            ["葛洲坝", "中国葛洲坝", "葛洲坝股份"],
        ),
        (
            "电力规划总院有限公司",
            ["电力规划设计总院", "电规院", "电规总院", "电力规划总院"],
        ),
        (
            "中国电力工程顾问集团有限公司",
            ["中国电力工程顾问集团", "中电工程"],
        ),
        (
            "中国能源建设集团规划设计有限公司",
            ["能建规划设计"],
        ),
        (
            "中能建国际建设集团有限公司",
            ["中国能建国际集团", "能建国际", "中能建国际"],
        ),
        (
            "中国能源建设集团国际工程有限公司",
            ["能建国际工程"],
        ),
        (
            "中国能源建设集团投资有限公司",
            ["能建投资", "能建投资公司"],
        ),
        (
            "中国能建集团装备有限公司",
            ["中能建装备", "能建装备"],
        ),
        (
            "中国能源建设集团财务有限公司",
            ["中能建财务公司", "能建财务公司"],
        ),
        (
            "中国能源建设集团资产管理有限公司",
            ["能建资管", "资产管理公司"],
        ),
        (
            "中国能源建设集团融资租赁有限公司",
            ["能建租赁", "融资租赁公司"],
        ),
        (
            "中能建基金管理有限公司",
            ["能建基金", "能建基金公司"],
        ),
        (
            "中国能源建设集团北方建设投资有限公司",
            ["能建北方投资", "北方建设投资"],
        ),
        (
            "中国能源建设集团华东建设投资有限公司",
            ["能建华东投资", "华东建设投资"],
        ),
        (
            "中国能源建设集团南方建设投资有限公司",
            ["能建南方投资", "南方建设投资"],
        ),
        (
            "中国能源建设集团西北建设投资有限公司",
            ["能建西北投资", "西北建设投资"],
        ),
        (
            "中能建西南投资有限公司",
            ["能建西南投资", "西南投资"],
        ),
        (
            "中国能源建设集团北京电力建设有限公司",
            ["北京电建", "北京电力建设"],
        ),
        (
            "中国能源建设集团广东火电工程有限公司",
            ["广东火电", "广东火电工程"],
        ),
        (
            "中国能源建设集团浙江火电建设有限公司",
            ["浙江火电", "浙江火电建设"],
        ),
        (
            "中国能源建设集团江苏省电力建设第三工程有限公司",
            ["江苏电建三公司", "江苏电建三"],
        ),
        (
            "中国葛洲坝集团易普力股份有限公司",
            ["易普力", "葛洲坝易普力"],
        ),
        (
            "中国能源建设集团天津电力建设有限公司",
            ["天津电建", "天津电力建设"],
        ),
        (
            "中国能源建设集团山西电力建设有限公司",
            ["山西电建", "山西电力建设"],
        ),
    ]
    for name, aliases in subsidiaries:
        _ensure_entity(db, ceec.id, name, "company", "公司", [name, *aliases])

    _ensure_pattern(
        db,
        "中国能建区域电力建设",
        r"中国能源建设集团.{2,10}电力建设.{0,6}有限公司",
        "company",
        "公司",
        ceec.id,
    )
    _ensure_pattern(
        db,
        "中国能建区域能源建设",
        r"中国能源建设集团.{2,10}能源建设有限公司",
        "company",
        "公司",
        ceec.id,
    )
    _ensure_pattern(
        db,
        "中国能建省级设计院",
        r"中国能源建设集团.{2,6}省.{0,4}电力设计.{0,4}有限公司",
        "company",
        "公司",
        ceec.id,
    )


def seed_db(db) -> None:
    """Seed using an existing session (tests) or call seed() for CLI."""
    spic = _get_or_create_pack(
        db,
        "spic",
        "国家电投",
        "国家电力投资集团有限公司体系",
        True,
    )
    general = _get_or_create_pack(
        db,
        "general_finance",
        "通用财务",
        "通用财务脱敏规则与白名单",
        True,
    )
    ceec = _get_or_create_pack(
        db,
        "ceec",
        "中国能建",
        "中国能源建设集团有限公司体系",
        True,
    )

    spic.is_default = False
    general.is_default = True
    ceec.is_default = True
    db.flush()

    _seed_ceec(db, ceec)

    spic_group_aliases = [
        "国家电力投资集团有限公司",
        "国家电投",
        "国家电投集团",
        "国家 电投",
        "中国电投",
        "中国电力投资集团公司",
        "中电投",
        "SPIC",
    ]
    _ensure_entity(
        db,
        spic.id,
        "国家电力投资集团有限公司",
        "company",
        "公司",
        spic_group_aliases,
    )

    subsidiaries = [
        ("国家核电技术有限公司", ["国家核电"]),
        ("电投产融控股股份有限公司", ["电投产融", "东方能源"]),
        ("上海电力股份有限公司", ["上海电力"]),
        ("国家电投集团吉林电力股份有限公司", ["吉电股份"]),
        ("国家电投集团远达环保股份有限公司", ["远达环保"]),
        ("五凌电力有限公司", ["五凌电力"]),
        ("黄河上游水电开发有限责任公司", ["黄河水电"]),
        ("国家电投集团资本控股有限公司", ["资本控股"]),
        ("国家电投集团财务有限公司", ["电投财务", "财务公司"]),
    ]
    for name, aliases in subsidiaries:
        _ensure_entity(db, spic.id, name, "company", "公司", [name, *aliases])

    _ensure_entity(db, spic.id, "国家开发投资集团有限公司", "company", "公司", ["国投", "国家开发投资"])
    _ensure_entity(db, general.id, "示例银行股份有限公司", "company", "公司", ["示例银行"])

    _ensure_pattern(db, "统一社会信用代码", r"\b[0-9A-Z]{18}\b", "custom", "证件", None)
    _ensure_pattern(db, "手机号", r"\b1[3-9]\d{9}\b", "custom", "手机", None)
    _ensure_pattern(db, "邮箱", r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", "custom", "邮箱", None)
    _ensure_pattern(db, "银行卡号", r"\b\d{16,19}\b", "custom", "账号", None)
    _ensure_pattern(
        db,
        "国家电投区域公司",
        r"国家电投集团.{2,8}电力有限公司",
        "company",
        "公司",
        spic.id,
    )

    whitelist_terms = [
            ("应收账款", "exact", "会计科目"),
            ("应付账款", "exact", "会计科目"),
            ("固定资产", "exact", "会计科目"),
            ("货币资金", "exact", "会计科目"),
            ("资产负债表", "exact", "报表"),
            ("利润表", "exact", "报表"),
            ("现金流量表", "exact", "报表"),
            ("企业会计准则", "exact", "准则"),
            ("毛利率", "exact", "比率"),
            ("净资产收益率", "exact", "比率"),
            ("ROE", "exact", "比率"),
            ("ROA", "exact", "比率"),
            (r"\d+(\.\d+)?%", "regex", "比率"),
            (r"\d{1,3}(,\d{3})*(\.\d+)?", "regex", "金额"),
    ]
    for term, ttype, cat in whitelist_terms:
        exists = (
            db.query(DeidWhitelistTerm)
            .filter(DeidWhitelistTerm.term == term, DeidWhitelistTerm.pack_id.is_(None))
            .first()
        )
        if not exists:
            db.add(
                DeidWhitelistTerm(
                    term=term,
                    term_type=ttype,
                    category=cat,
                    pack_id=None,
                )
            )

    db.commit()


def seed():
    db = SessionLocal()
    try:
        seed_db(db)
        print("deid seed OK: spic + ceec + general_finance")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
