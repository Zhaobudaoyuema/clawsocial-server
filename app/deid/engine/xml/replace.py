"""Replace paragraph text when plan hits — rebuild single plain run."""
from xml.etree import ElementTree as ET

from app.deid.engine.plan import ReplacementPlan
from app.deid.engine.xml.text_extract import iter_paragraphs

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def replace_in_xml_tree(root: ET.Element, plan: ReplacementPlan) -> tuple[int, int]:
    """Returns (paragraphs_touched, replacement_count)."""
    touched = 0
    total = 0
    for p, text, _loc in iter_paragraphs(root):
        if not text.strip():
            continue
        new_text, cnt = plan.apply_to_text(text)
        if cnt == 0:
            continue
        _rebuild_paragraph(p, new_text)
        touched += 1
        total += cnt
    return touched, total


def _rebuild_paragraph(p: ET.Element, new_text: str) -> None:
    saved_ppr = None
    for child in list(p):
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "pPr":
            saved_ppr = child
        p.remove(child)
    if saved_ppr is not None:
        p.append(saved_ppr)
    r = ET.Element(f"{{{W_NS}}}r")
    rpr_el = ET.SubElement(r, f"{{{W_NS}}}rPr")
    rf = ET.SubElement(rpr_el, f"{{{W_NS}}}rFonts")
    rf.set(f"{{{W_NS}}}ascii", "Calibri")
    rf.set(f"{{{W_NS}}}hAnsi", "Calibri")
    rf.set(f"{{{W_NS}}}eastAsia", "宋体")
    sz = ET.SubElement(rpr_el, f"{{{W_NS}}}sz")
    sz.set(f"{{{W_NS}}}val", "24")
    t = ET.SubElement(r, f"{{{W_NS}}}t")
    t.text = new_text
    if new_text and (new_text[0].isspace() or new_text[-1].isspace()):
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    p.append(r)


def process_xml_file(path, plan: ReplacementPlan) -> tuple[int, int]:
    tree = ET.parse(path)
    root = tree.getroot()
    touched, total = replace_in_xml_tree(root, plan)
    if touched:
        tree.write(path, encoding="UTF-8", xml_declaration=True)
    return touched, total
