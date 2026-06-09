"""WordprocessingML namespace helpers — transitional + strict OOXML."""
from __future__ import annotations

from xml.etree import ElementTree as ET

W_NS_TRANSITIONAL = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W_NS_STRICT = "http://purl.oclc.org/ooxml/wordprocessingml/main"
W_NS_CANDIDATES = (W_NS_TRANSITIONAL, W_NS_STRICT)
XML_NS = "http://www.w3.org/XML/1998/namespace"


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if tag.startswith("{") else tag


def detect_w_ns(root: ET.Element) -> str:
    """Pick wordprocessing namespace from document root or first w:* element."""
    root_local = local_name(root.tag)
    if root_local == "document" and root.tag.startswith("{"):
        return root.tag[1:].split("}", 1)[0]
    for el in root.iter():
        if local_name(el.tag) in ("p", "r", "t", "tbl", "document"):
            if el.tag.startswith("{"):
                return el.tag[1:].split("}", 1)[0]
    return W_NS_TRANSITIONAL


def w_qname(ns: str, local: str) -> str:
    return f"{{{ns}}}{local}"


def iter_w(root: ET.Element, local: str):
    for el in root.iter():
        if local_name(el.tag) == local:
            yield el
