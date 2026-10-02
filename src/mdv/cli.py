import argparse
import sys
from pathlib import Path

from .document import MARKDOWN_SUFFIXES, load_document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read Markdown and converted documents in your terminal.")
    parser.add_argument("file", nargs="?", help="local document, or - for Markdown on stdin")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--print", dest="print_only", action="store_true", help="render without opening the interactive viewer")
    mode.add_argument("--raw", action="store_true", help="output Markdown source (including converted documents)")
    mode.add_argument("--edit", action="store_true", help="open the Markdown editor, creating a new file on save")
    mode.add_argument("--live-edit", action="store_true", help="edit in one pane with live Markdown styling and gray syntax")
    sidebar = parser.add_mutually_exclusive_group()
    sidebar.add_argument("--toc", dest="show_toc", action="store_true", help="start with the sidebar shown")
    sidebar.add_argument("--no-toc", dest="show_toc", action="store_false", help="start with the sidebar hidden (default)")
    parser.set_defaults(show_toc=False)
    args = parser.parse_args(argv)
    args.edit = args.edit or args.live_edit
    if args.edit and args.file in (None, "-"):
        parser.error("--edit requires a Markdown file path")
    if args.file is None and sys.stdin.isatty():
        parser.print_help()
        return 0
    path = Path(args.file).expanduser().resolve() if args.file not in (None, "-") else None
    try:
        if path is not None:
            if args.edit and path.suffix.lower() not in MARKDOWN_SUFFIXES:
                raise ValueError("Editing is available for Markdown files only.")
            if not path.is_file():
                if path.exists():
                    raise OSError(f"Not a file: {path}")
                if not args.edit:
                    raise OSError(f"Not a file: {path}. Use mde <file.md> to write a new Markdown file.")
                if not path.parent.is_dir():
                    raise OSError(f"Parent directory does not exist: {path.parent}")
        if path is None and sys.stdin.isatty():
            parser.error("- requires Markdown piped to stdin")
        # Piped input uses print mode so the terminal is never needed for keyboard input.
        interactive = not args.print_only and not args.raw and sys.stdout.isatty() and sys.stdin.isatty()
        if args.edit and not interactive:
            raise ValueError("--edit requires an interactive terminal")
        if interactive:
            from .app import Viewer

            Viewer(path, show_toc=args.show_toc, start_editing=args.edit,
                   **({"live_edit": True} if args.live_edit else {})).run()
        else:
            content = load_document(path) if path else sys.stdin.read()
            if args.raw or not sys.stdout.isatty():
                sys.stdout.write(content)
                if content and not content.endswith("\n"):
                    sys.stdout.write("\n")
            else:
                from rich.console import Console

                from .theme import PrintPalette, load_theme

                from .html import PrintMarkdown

                palette = PrintPalette(load_theme())
                Console(theme=palette.rich_theme()).print(PrintMarkdown(content, code_theme=palette))
        return 0
    except BrokenPipeError:
        return 0
    except Exception as error:
        print(f"mdv: {error}", file=sys.stderr)
        return 1


def print_main() -> int:
    return main(["--print", *sys.argv[1:]])


def edit_main() -> int:
    return main(["--edit", *sys.argv[1:]])
