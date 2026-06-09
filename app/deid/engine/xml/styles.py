"""Read plain rPr from styles.xml Normal / docDefaults."""
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def plain_rpr_xml(work_dir: Path) -> str:
    """Minimal plain run properties for replaced paragraphs."""
    styles = work_dir / "word" / "styles.xml"
    east = "宋体"
    ascii_font = "Calibri"
    if styles.exists():
        try:
            root = ET.parse(styles).getroot()
            for style in root.findall(f".//{{{W_NS}}}style"):
                if style.get(f"{{{W_NS}}}type") == "paragraph":
                    sid = style.get(f"{{{W_NS}}}styleId")
                    if sid in ("Normal", "a", "1"):
                        rpr = style.find(f"{{{W_NS}}}rPr")
                        if rpr is not None:
                            rfonts = rpr.find(f"{{{W_NS}}}rFonts")
                            if rfonts is not None:
                                east = rfonts.get(f"{{{W_NS}}}eastAsia") or east
                                ascii_font = rfonts.get(f"{{{W_NS}}}ascii") or ascii_font
                            break
        except ET.ParseError:
            pass
    return (
        f'<w:rPr xmlns:w="{W_NS}">'
        f'<w:rFonts w:ascii="{ascii_font}" w:hAnsi="{ascii_font}" w:eastAsia="{east}"/>'
        f"<w:sz w:val=\"24\"/><w:szCs w:val=\"24\"/>"
        f"</w:rPr>"
    )
