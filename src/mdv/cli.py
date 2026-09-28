import argparse
import sys
from pathlib import Path

from .document import load_document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read Markdown and converted documents in your terminal.")
    parser.add_argument("file", nargs="?", help="local document, or - for Markdown on stdin")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--print", dest="print_only", action="store_true", help="render without opening the interactive viewer")
    mode.add_argument("--raw", action="store_true", help="output Markdown source (including converted documents)")
    parser.add_argument("--no-toc", action="store_true", help="start with the table of contents hidden")
    args = parser.parse_args(argv)
    if args.file is None and sys.stdin.isatty():
        parser.print_help()
        return 0
    path = Path(args.file).expanduser().resolve() if args.file not in (None, "-") else None
    try:
        if path is None and sys.stdin.isatty():
            parser.error("- requires Markdown piped to stdin")
        # Piped input uses print mode so the terminal is never needed for keyboard input.
        interactive = not args.print_only and not args.raw and sys.stdout.isatty() and sys.stdin.isatty()
        if interactive:
            from .app import Viewer

            Viewer(path, show_toc=not args.no_toc).run()
        else:
            content = load_document(path) if path else sys.stdin.read()
            if args.raw or not sys.stdout.isatty():
                sys.stdout.write(content)
                if content and not content.endswith("\n"):
                    sys.stdout.write("\n")
            else:
                from rich.console import Console
                from rich.markdown import Markdown

                from .theme import PrintPalette, load_theme

                palette = PrintPalette(load_theme())
                Console(theme=palette.rich_theme()).print(Markdown(content, code_theme=palette))
        return 0
    except BrokenPipeError:
        return 0
    except Exception as error:
        print(f"mdv: {error}", file=sys.stderr)
        return 1
