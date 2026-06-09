"""Extract paragraph full text from OOXML."""
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def paragraph_full_text(p_elem: ET.Element) -> str:
    parts: list[str] = []
    for t in p_elem.iter(f"{{{W_NS}}}t"):
        if t.text:
            parts.append(t.text)
        if t.tail:
            parts.append(t.tail)
    return "".join(parts)


def iter_paragraphs(root: ET.Element) -> list[tuple[ET.Element, str, str]]:
    """Yield (p_elem, full_text, location_tag) including txbx content."""
    results: list[tuple[ET.Element, str, str]] = []
    idx = 0
    for p in root.iter(f"{{{W_NS}}}p"):
        text = paragraph_full_text(p)
        loc = f"p{idx}"
        results.append((p, text, loc))
        idx += 1
    return results
