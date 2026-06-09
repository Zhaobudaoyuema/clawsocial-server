"""Read plain rPr from styles.xml Normal / docDefaults."""
from pathlib import Path
from xml.etree import ElementTree as ET

from app.deid.engine.xml.ns import detect_w_ns, iter_w, local_name, w_qname

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def plain_rpr_xml(work_dir: Path) -> str:
    """Minimal plain run properties for replaced paragraphs."""
    styles = work_dir / "word" / "styles.xml"
    east = "宋体"
    ascii_font = "Calibri"
    if styles.exists():
        try:
            root = ET.parse(styles).getroot()
            w_ns = detect_w_ns(root)
            for style in iter_w(root, "style"):
                if style.get(w_qname(w_ns, "type")) == "paragraph":
                    sid = style.get(w_qname(w_ns, "styleId"))
                    if sid in ("Normal", "a", "1"):
                        rpr = next(iter_w(style, "rPr"), None)
                        if rpr is not None:
                            rfonts = next(iter_w(rpr, "rFonts"), None)
                            if rfonts is not None:
                                east = rfonts.get(w_qname(w_ns, "eastAsia")) or east
                                ascii_font = rfonts.get(w_qname(w_ns, "ascii")) or ascii_font
                            break
        except ET.ParseError:
            pass
    return (
        f'<w:rPr xmlns:w="{W_NS}">'
        f'<w:rFonts w:ascii="{ascii_font}" w:hAnsi="{ascii_font}" w:eastAsia="{east}"/>'
        f"<w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/>"
        f"</w:rPr>"
    )
