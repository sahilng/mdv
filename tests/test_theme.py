import io
import re

import pytest
from textual.command import CommandList, CommandPalette
from textual.widgets import MarkdownViewer

from mdv.app import Viewer
from mdv.cli import main
from mdv.theme import PrintPalette, load_theme, theme_path


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("TEXTUAL_THEME", raising=False)


@pytest.mark.parametrize("name", ["textual-dark", "textual-light", "dracula", "nord",
                                   "ansi-dark", "ansi-light"])
async def test_selected_theme_persists_for_interactive_viewer(tmp_path, name):
    path = tmp_path / "sample.md"
    path.write_text("## Heading\n\n```python\nprint(42)\n```\n")
    app = Viewer(path)
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        app.theme = name
        await pilot.pause()
    assert load_theme() == name
    assert Viewer(path).theme == name


def test_invalid_settings_and_environment_override(monkeypatch):
    theme_path().parent.mkdir(parents=True)
    theme_path().write_text("unknown-theme")
    assert load_theme() == "textual-dark"
    monkeypatch.setenv("TEXTUAL_THEME", "nord")
    assert load_theme() == "nord"


def test_print_cli_uses_terminal_colors_independent_of_viewer_theme(tmp_path, monkeypatch):
    class Terminal(io.StringIO):
        def isatty(self):
            return True

    path = tmp_path / "sample.md"
    path.write_text("## Heading\n\n[Example](https://example.com)\n")
    output = Terminal()
    monkeypatch.setattr("sys.stdout", output)
    monkeypatch.setenv("COLORTERM", "truecolor")
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TEXTUAL_THEME", "nord")
    assert main([str(path), "--print"]) == 0
    first = output.getvalue()
    output.seek(0)
    output.truncate()
    monkeypatch.setenv("TEXTUAL_THEME", "tokyo-night")
    assert main([str(path), "--print"]) == 0
    without_link_ids = lambda value: re.sub(r";id=\d+;", ";id=;", value)
    assert without_link_ids(output.getvalue()) == without_link_ids(first)
    assert "Example" in first and "\x1b[" in first


def test_print_text_and_links_inherit_terminal_colors():
    styles = PrintPalette().rich_theme().styles
    for key in ("markdown.text", "markdown.paragraph", "markdown.h1", "markdown.h2",
                "markdown.link", "markdown.link_url"):
        assert styles[key].color is None
        assert styles[key].bgcolor is None
    assert styles["markdown.link"].underline
    assert styles["markdown.code"].reverse


async def test_theme_highlight_previews_and_escape_restores(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text("# Heading\n")
    app = Viewer(path)
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        original = app.theme
        app.action_change_theme()
        await pilot.pause(0.1)
        assert isinstance(app.screen, CommandPalette)
        commands = app.screen.query_one(CommandList)
        assert commands.option_count > 1
        await pilot.press("down")
        await pilot.pause()
        preview = app.theme
        assert preview != original
        await pilot.press("down")
        await pilot.pause()
        assert app.theme != preview
        await pilot.press("escape")
        assert app.theme == original

        app.action_change_theme()
        await pilot.pause(0.1)
        await pilot.press("down")
        await pilot.pause()
        selected = app.theme
        await pilot.press("enter")
        await pilot.pause()
        assert app.theme == selected
    assert load_theme() == selected


async def test_palette_does_not_dim_and_ansi_previews_keep_text_visible(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text("# Heading\n\nBody paragraph\n")
    app = Viewer(path)
    async with app.run_test(size=(80, 20)) as pilot:
        await app.workers.wait_for_complete()
        await pilot.press("ctrl+p")
        assert isinstance(app.screen, CommandPalette)
        assert app.screen.styles.background.is_transparent
        await pilot.press("escape")

        app.action_change_theme()
        await pilot.pause(0.1)
        assert app.screen.styles.background.is_transparent
        commands = app.screen.query_one(CommandList)
        text_colors = []
        for index, name in enumerate(("ansi-dark", "ansi-light")):
            commands.highlighted = index
            await pilot.pause()
            assert app.theme == name
            screenshot = app.export_screenshot()
            match = re.search(r'class="([^"]+)"[^>]*>Body&#160;paragraph</text>', screenshot)
            assert match is not None
            color = re.search(rf"\.{re.escape(match.group(1))} \{{ fill: (#[0-9a-f]{{6}})", screenshot)
            assert color is not None
            text_colors.append(color.group(1))
        assert text_colors[0] != "#000000"
        assert text_colors[0] != text_colors[1]


@pytest.mark.parametrize("name", ["ansi-dark", "ansi-light"])
async def test_ansi_inline_code_has_contrasting_text(tmp_path, name):
    path = tmp_path / "sample.md"
    path.write_text("A `visible code` example\n")
    app = Viewer(path)
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        app.theme = name
        await pilot.pause()
        paragraph = app.query_one(MarkdownViewer).document.query_one("MarkdownParagraph")
        style = paragraph.get_component_rich_style("code_inline")
        assert style.color is not None
        assert style.bgcolor is not None
        assert style.color != style.bgcolor
        print_style = PrintPalette().rich_theme().styles["markdown.code"]
        assert print_style.reverse
