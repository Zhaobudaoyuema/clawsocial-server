"""One-off: extract text from legacy .doc via Word COM (Windows)."""
from __future__ import annotations

import sys
from pathlib import Path

import win32com.client  # type: ignore


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python scripts/extract_doc_text.py <path.doc> [out.txt]", file=sys.stderr)
        sys.exit(2)
    src = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    try:
        doc = word.Documents.Open(str(src), ReadOnly=True)
        text = doc.Content.Text
        doc.Close(False)
    finally:
        word.Quit()
    if out:
        out.write_text(text, encoding="utf-8")
        print(f"wrote {len(text)} chars -> {out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
