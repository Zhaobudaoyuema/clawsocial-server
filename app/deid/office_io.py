"""
Thin wrappers around vendored Anthropic docx office scripts.
MVP: pack skips XSD/redlining validators (zip + condense only).
"""
import shutil
import tempfile
import zipfile
from pathlib import Path

import defusedxml.minidom

from app.deid.vendor.office.helpers import merge_runs as merge_runs_mod


def unpack_docx(
    input_file: str | Path,
    output_directory: str | Path,
    *,
    merge: bool = True,
    fast: bool = False,
) -> None:
    """Extract docx ZIP; optionally merge adjacent runs in document.xml."""
    input_path = Path(input_file)
    output_path = Path(output_directory)
    if not input_path.exists():
        raise FileNotFoundError(str(input_path))
    output_path.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(input_path, "r") as zf:
        zf.extractall(output_path)
    if not fast:
        for xml_file in list(output_path.rglob("*.xml")) + list(output_path.rglob("*.rels")):
            _pretty_print_xml(xml_file)
    if merge:
        merge_runs_mod.merge_runs(str(output_path))


def pack_docx(
    input_directory: str | Path,
    output_file: str | Path,
    *,
    validate: bool = False,  # noqa: ARG001 — MVP skips heavy validators
    fast: bool = False,
) -> None:
    """Repack unpacked directory into docx (no XSD validation in MVP)."""
    input_dir = Path(input_directory)
    output_path = Path(output_file)
    if not input_dir.is_dir():
        raise NotADirectoryError(str(input_dir))
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_content = Path(temp_dir) / "content"
        shutil.copytree(input_dir, temp_content)
        if not fast:
            for pattern in ("*.xml", "*.rels"):
                for xml_file in temp_content.rglob(pattern):
                    _condense_xml(xml_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in temp_content.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(temp_content))


def _pretty_print_xml(xml_file: Path) -> None:
    try:
        content = xml_file.read_text(encoding="utf-8")
        dom = defusedxml.minidom.parseString(content)
        xml_file.write_bytes(dom.toprettyxml(indent="  ", encoding="utf-8"))
    except Exception:
        pass


def _condense_xml(xml_file: Path) -> None:
    with open(xml_file, encoding="utf-8") as f:
        dom = defusedxml.minidom.parse(f)
    for element in dom.getElementsByTagName("*"):
        if element.tagName.endswith(":t"):
            continue
        for child in list(element.childNodes):
            if (
                child.nodeType == child.TEXT_NODE
                and child.nodeValue
                and child.nodeValue.strip() == ""
            ) or child.nodeType == child.COMMENT_NODE:
                element.removeChild(child)
    xml_file.write_bytes(dom.toxml(encoding="UTF-8"))
