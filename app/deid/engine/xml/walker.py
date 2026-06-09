"""Locate target XML parts in an unpacked docx directory."""
from pathlib import Path

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def target_xml_files(work_dir: Path) -> list[Path]:
    """document, headers, footers, notes — MVP core paths."""
    word = work_dir / "word"
    if not word.exists():
        return []
    paths: list[Path] = []
    doc = word / "document.xml"
    if doc.exists():
        paths.append(doc)
    for p in sorted(word.glob("header*.xml")):
        paths.append(p)
    for p in sorted(word.glob("footer*.xml")):
        paths.append(p)
    for name in ("footnotes.xml", "endnotes.xml"):
        fp = word / name
        if fp.exists():
            paths.append(fp)
    return paths
