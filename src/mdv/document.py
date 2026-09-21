from pathlib import Path

MARKDOWN_SUFFIXES = {".md", ".markdown", ".mdown", ".mkd", ".mkdn"}


def load_document(path: Path) -> str:
    """Read Markdown directly; convert other local documents with MarkItDown."""
    if not path.is_file():
        raise OSError(f"Not a file: {path}")
    if path.suffix.lower() in MARKDOWN_SUFFIXES:
        return path.read_text(encoding="utf-8-sig")
    from markitdown import MarkItDown

    return MarkItDown(enable_plugins=False).convert_local(str(path)).text_content
