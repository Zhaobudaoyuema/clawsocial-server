"""
博客内容 API。
GET /api/blog/list   — 返回 docs/home/ 目录树（支持嵌套文件夹）
GET /api/blog/{slug} — 读取并返回指定文章的 Markdown 原文
"""
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["blog"])

# docs/home/ 相对于项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
BLOG_ROOT = _PROJECT_ROOT / "docs" / "home"


def _build_tree(root: Path) -> list[dict[str, Any]]:
    """
    递归构建目录树。
    返回 items: [{ type: "folder", name, path, children }, { type: "file", name, slug, path }]
    """
    if not root.exists():
        return []

    items: list[dict[str, Any]] = []

    # 先收集文件夹和文件
    dirs: list[Path] = []
    files: list[Path] = []

    for entry in sorted(root.iterdir()):
        if entry.is_dir():
            dirs.append(entry)
        elif entry.suffix == ".md":
            files.append(entry)

    # 文件夹在前，文件在后（均按字母序）
    for d in dirs:
        children = _build_tree(d)
        items.append({
            "type": "folder",
            "name": d.name,
            "path": str(d.relative_to(BLOG_ROOT)),
            "children": children,
        })

    for f in sorted(files):
        relative = f.relative_to(BLOG_ROOT)
        slug = str(relative.with_suffix("")).replace(os.sep, "/")
        items.append({
            "type": "file",
            "name": f.stem,  # 文件名（无后缀）作为标题
            "slug": slug,
            "path": str(relative),
        })

    return items


@router.get("/api/blog/list")
def list_blog() -> dict[str, list[dict[str, Any]]]:
    """
    返回 docs/home/ 的目录结构。
    响应: { "items": [...] }
    """
    items = _build_tree(BLOG_ROOT)
    return {"items": items}


@router.get("/api/blog/{slug:path}", response_class=PlainTextResponse)
def get_blog_post(slug: str) -> str:
    """
    读取并返回指定文章的 Markdown 原文。
    slug 格式: "文件夹/文件名" 或 "文件名"（无 .md 后缀）
    """
    file_path = BLOG_ROOT / f"{slug}.md"
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"文章不存在: {slug}")
    return file_path.read_text(encoding="utf-8")
