"""Extract paragraph full text from OOXML."""
from xml.etree import ElementTree as ET

from app.deid.engine.xml.ns import iter_w


def paragraph_full_text(p_elem: ET.Element) -> str:
    parts: list[str] = []
    for t in iter_w(p_elem, "t"):
        if t.text:
            parts.append(t.text)
        if t.tail:
            parts.append(t.tail)
    return "".join(parts)


def iter_paragraphs(root: ET.Element):
    """Yield (p_elem, full_text, location_tag) including txbx content."""
    idx = 0
    for p in iter_w(root, "p"):
        text = paragraph_full_text(p)
        yield p, text, f"p{idx}"
        idx += 1
