"""Share the viewer's selected Textual theme with Rich's print renderer."""

import os
from dataclasses import replace
from pathlib import Path

from rich.style import Style
from rich.syntax import ANSISyntaxTheme, ANSI_DARK
from rich.theme import Theme
from textual.app import App
from textual.theme import BUILTIN_THEMES


def theme_path() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "mdv" / "theme"


def load_theme() -> str:
    try:
        saved = theme_path().read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        saved = "textual-dark"
    name = os.environ.get("TEXTUAL_THEME") or saved
    return name if name in BUILTIN_THEMES else "textual-dark"


def save_theme(name: str) -> None:
    path = theme_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(name + "\n", encoding="utf-8")


def register_visible_ansi_themes(app: App) -> None:
    """Give ANSI themes explicit terminal colors so foreground and background differ."""
    for name in ("ansi-dark", "ansi-light"):
        theme = BUILTIN_THEMES[name]
        app.register_theme(replace(
            theme,
            foreground=theme.variables["ansi-foreground"],
            background=theme.variables["ansi-background"],
            surface=theme.variables["ansi-background"],
            panel=theme.variables["ansi-background"],
            boost=theme.variables["ansi-background"],
            variables={
                **theme.variables,
                "text-warning": theme.variables["ansi-background"],
                "text-error": theme.variables["ansi-background"],
            },
            ansi=False,
        ))


class PrintPalette(ANSISyntaxTheme):
    """Use terminal foreground and palette colors for non-interactive output."""

    def __init__(self):
        super().__init__(ANSI_DARK)

    def rich_theme(self) -> Theme:
        styles = {
            "markdown.text": Style(),
            "markdown.paragraph": Style(),
            "markdown.code": Style(color="cyan", bold=True),
            "markdown.code_block": Style(),
            "markdown.block_quote": Style(dim=True),
            "markdown.list": Style(),
            "markdown.item.number": Style(bold=True),
            "markdown.link": Style(bold=True, underline=True),
            "markdown.link_url": Style(underline=True),
            "markdown.hr": Style(dim=True),
            "markdown.h1.border": Style(dim=True),
            "markdown.table.border": Style(dim=True),
            "markdown.table.header": Style(bold=True),
            "markdown.h1": Style(bold=True, underline=True),
            "markdown.h2": Style(bold=True),
            "markdown.h3": Style(bold=True),
            "markdown.h4": Style(italic=True),
            "markdown.h5": Style(italic=True),
            "markdown.h6": Style(dim=True),
        }
        return Theme(styles)
