"""Replace paragraph text when plan hits — rebuild single plain run."""
from xml.etree import ElementTree as ET

from app.deid.engine.plan import ReplacementPlan
from app.deid.engine.xml.ns import XML_NS, detect_w_ns, local_name, w_qname
from app.deid.engine.xml.text_extract import iter_paragraphs


def replace_in_xml_tree(root: ET.Element, plan: ReplacementPlan) -> tuple[int, int]:
    """Returns (paragraphs_touched, replacement_count)."""
    touched = 0
    total = 0
    w_ns = detect_w_ns(root)
    for p, text, _loc in iter_paragraphs(root):
        if not text.strip():
            continue
        new_text, cnt = plan.apply_to_text(text)
        if cnt == 0:
            continue
        _rebuild_paragraph(p, new_text, w_ns)
        touched += 1
        total += cnt
    return touched, total


def _rebuild_paragraph(p: ET.Element, new_text: str, w_ns: str) -> None:
    saved_ppr = None
    for child in list(p):
        if local_name(child.tag) == "pPr":
            saved_ppr = child
        p.remove(child)
    if saved_ppr is not None:
        p.append(saved_ppr)
    r = ET.Element(w_qname(w_ns, "r"))
    rpr_el = ET.SubElement(r, w_qname(w_ns, "rPr"))
    rf = ET.SubElement(rpr_el, w_qname(w_ns, "rFonts"))
    rf.set(w_qname(w_ns, "ascii"), "Calibri")
    rf.set(w_qname(w_ns, "hAnsi"), "Calibri")
    rf.set(w_qname(w_ns, "eastAsia"), "宋体")
    sz = ET.SubElement(rpr_el, w_qname(w_ns, "sz"))
    sz.set(w_qname(w_ns, "val"), "24")
    t = ET.SubElement(r, w_qname(w_ns, "t"))
    t.text = new_text
    if new_text and (new_text[0].isspace() or new_text[-1].isspace()):
        t.set(f"{{{XML_NS}}}space", "preserve")
    p.append(r)


def process_xml_file(path, plan: ReplacementPlan) -> tuple[int, int]:
    tree = ET.parse(path)
    root = tree.getroot()
    touched, total = replace_in_xml_tree(root, plan)
    if touched:
        tree.write(path, encoding="UTF-8", xml_declaration=True)
    return touched, total
