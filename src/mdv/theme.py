"""Share the viewer's selected Textual theme with Rich's print renderer."""

import os
from dataclasses import replace
from pathlib import Path

from rich.style import Style
from rich.syntax import SyntaxTheme
from rich.theme import Theme
from textual.app import App
from textual.highlight import HighlightTheme
from textual.markup import parse_style
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


class PrintPalette(SyntaxTheme):
    def __init__(self, name: str):
        app = App()
        register_visible_ansi_themes(app)
        app.theme = name
        self.variables = app.get_css_variables()
        self.base = parse_style("$foreground on $surface", self.variables)
        self.dark = app.current_theme.dark
        self.ansi = name in {"ansi-dark", "ansi-light"}
        self.syntax_styles = {
            token: self.style(value) for token, value in HighlightTheme.STYLES.items()
        }

    def style(self, value: str) -> Style:
        return (self.base + parse_style(value, self.variables)).rich_style

    def get_style_for_token(self, token_type) -> Style:
        while token_type:
            if token_type in self.syntax_styles:
                return self.syntax_styles[token_type]
            token_type = token_type.parent
        return self.style("")

    def get_background_style(self) -> Style:
        return self.style("")

    def rich_theme(self) -> Theme:
        styles = {
            "markdown.text": self.style(""),
            "markdown.paragraph": self.style(""),
            "markdown.code": self.style(
                ("$text-warning on $warning" if self.dark else "$text-error on $error")
                if self.ansi else ("$text-warning" if self.dark else "$text-error")
            ),
            "markdown.code_block": self.style(""),
            "markdown.block_quote": self.style(""),
            "markdown.list": self.style(""),
            "markdown.item.number": self.style(""),
            "markdown.link": self.style("$link-color underline"),
            "markdown.link_url": self.style("$link-color underline"),
            "markdown.hr": self.style("$secondary"),
            "markdown.h1.border": self.style("$primary"),
            "markdown.table.border": self.style("$foreground 20%"),
            "markdown.table.header": self.style("$primary bold"),
        }
        for level in range(1, 7):
            prefix = f"markdown-h{level}"
            emphasis = self.variables[f"{prefix}-text-style"]
            styles[f"markdown.h{level}"] = self.style(
                f"${prefix}-color on ${prefix}-background "
                + ("" if emphasis == "none" else emphasis)
            )
        return Theme(styles)
