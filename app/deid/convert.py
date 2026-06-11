"""Convert uploaded documents to Markdown via MarkItDown."""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

SUPPORTED_EXTENSIONS = frozenset({
    ".pdf",
    ".docx",
    ".xlsx",
    ".pptx",
    ".html",
    ".htm",
    ".csv",
    ".txt",
    ".md",
})

MIN_EXTRACT_CHARS = 50

SOURCE_FORMAT_LABELS = {
    "pdf": "PDF",
    "docx": "Word",
    "xlsx": "Excel",
    "pptx": "PPT",
    "html": "HTML",
    "htm": "HTML",
    "csv": "CSV",
    "txt": "TXT",
    "md": "Markdown",
}


def source_format_from_filename(filename: str) -> tuple[str, str]:
    ext = Path(filename or "").suffix.lstrip(".").lower()
    return ext, SOURCE_FORMAT_LABELS.get(ext, ext.upper() or "文档")


def extension_allowed(filename: str) -> bool:
    return Path(filename or "").suffix.lower() in SUPPORTED_EXTENSIONS


def convert_to_markdown(path: Path) -> str:
    """Convert a file to Markdown text."""
    from markitdown import MarkItDown

    result = MarkItDown().convert(str(path))
    return (result.text_content or "").strip()


def ensure_source_markdown(original_path: Path, out_dir: Path) -> Path:
    """
    Write source.md from original upload.
    Returns path to source.md.
    """
    suffix = original_path.suffix.lower()
    if suffix == ".md":
        text = original_path.read_text(encoding="utf-8", errors="replace").strip()
    else:
        try:
            text = convert_to_markdown(original_path)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"文档转换失败：{exc}",
            ) from exc

    if len(text) < MIN_EXTRACT_CHARS:
        raise HTTPException(
            status_code=400,
            detail="文档未能提取有效文本（可能是扫描件 PDF）",
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "source.md"
    dest.write_text(text, encoding="utf-8")
    return dest
