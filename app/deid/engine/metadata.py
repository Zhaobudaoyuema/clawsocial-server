"""OOXML document metadata scrubbing for de-identified exports."""
from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree as ET

_EMAIL_RE = re.compile(r"[\w.-]+@[\w.-]+\.\w+")

# OOXML namespaces in docProps
_CP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
_DC_NS = "http://purl.org/dc/elements/1.1/"
_DCTERMS_NS = "http://purl.org/dc/terms/"
_EP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"

_CORE_CLEAR_TAGS = [
    f"{{{_DC_NS}}}title",
    f"{{{_DC_NS}}}subject",
    f"{{{_DC_NS}}}description",
    f"{{{_DC_NS}}}creator",
    f"{{{_CP_NS}}}keywords",
    f"{{{_CP_NS}}}lastModifiedBy",
    f"{{{_CP_NS}}}lastPrinted",
]

_APP_CLEAR_TAGS = [
    f"{{{_EP_NS}}}Company",
    f"{{{_EP_NS}}}Manager",
]

_RESIDUAL_FIELDS = ("creator", "lastModifiedBy", "Company", "Manager")


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _set_text(elem: ET.Element | None, value: str) -> None:
    if elem is None:
        return
    elem.text = value


def _clear_element(parent: ET.Element, tag: str) -> list[str]:
    cleared: list[str] = []
    for child in list(parent):
        if child.tag == tag:
            name = _local_name(tag)
            if child.text:
                cleared.append(f"{name}={child.text}")
            parent.remove(child)
    return cleared


def scrub_docprops(work_dir: Path, *, label: str = "脱敏工具") -> list[str]:
    """
    Clear identity-bearing fields in docProps. Returns list of cleared field descriptions.
    """
    cleared: list[str] = []
    props = work_dir / "docProps"
    if not props.is_dir():
        return cleared

    core_path = props / "core.xml"
    if core_path.exists():
        tree = ET.parse(core_path)
        root = tree.getroot()
        identity_tags = {f"{{{_DC_NS}}}creator", f"{{{_CP_NS}}}lastModifiedBy"}
        for child in list(root):
            if child.tag in identity_tags:
                if child.text:
                    cleared.append(f"core.{_local_name(child.tag)}={child.text}")
                _set_text(child, label)
            elif child.tag in _CORE_CLEAR_TAGS:
                if child.text:
                    cleared.append(f"core.{_local_name(child.tag)}={child.text}")
                root.remove(child)
        rev = root.find(f"{{{_CP_NS}}}revision")
        if rev is not None:
            rev.text = "1"
        tree.write(core_path, encoding="utf-8", xml_declaration=True)

    app_path = props / "app.xml"
    if app_path.exists():
        tree = ET.parse(app_path)
        root = tree.getroot()
        for tag in _APP_CLEAR_TAGS:
            cleared.extend(f"app.{c}" for c in _clear_element(root, tag))
        tree.write(app_path, encoding="utf-8", xml_declaration=True)

    custom_path = props / "custom.xml"
    if custom_path.exists():
        try:
            tree = ET.parse(custom_path)
            root = tree.getroot()
            for child in list(root):
                if child.text:
                    cleared.append(f"custom.{_local_name(child.tag)}={child.text}")
                root.remove(child)
            tree.write(custom_path, encoding="utf-8", xml_declaration=True)
        except ET.ParseError:
            pass

    return cleared


def scan_metadata_residuals(work_dir: Path) -> list[dict]:
    """Return residual identity metadata still present after scrub."""
    residuals: list[dict] = []
    props = work_dir / "docProps"
    if not props.is_dir():
        return residuals

    core_path = props / "core.xml"
    if core_path.exists():
        try:
            root = ET.parse(core_path).getroot()
            for field, tag in (
                ("creator", f"{{{_DC_NS}}}creator"),
                ("lastModifiedBy", f"{{{_CP_NS}}}lastModifiedBy"),
            ):
                elem = root.find(tag)
                if elem is not None and elem.text:
                    val = elem.text.strip()
                    if val and val != "脱敏工具" and (_EMAIL_RE.search(val) or len(val) > 1):
                        residuals.append({"field": field, "value": val, "location": "core.xml"})
        except ET.ParseError:
            pass

    app_path = props / "app.xml"
    if app_path.exists():
        try:
            root = ET.parse(app_path).getroot()
            for field in ("Company", "Manager"):
                elem = root.find(f"{{{_EP_NS}}}{field}")
                if elem is not None and elem.text and elem.text.strip():
                    residuals.append(
                        {"field": field, "value": elem.text.strip(), "location": "app.xml"}
                    )
        except ET.ParseError:
            pass

    return residuals
