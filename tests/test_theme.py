import io

import pytest
from rich.console import Console
from rich.markdown import Markdown
from textual.widgets import MarkdownViewer

from mdv.app import Viewer
from mdv.cli import main
from mdv.theme import PrintPalette, load_theme, theme_path


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("TEXTUAL_THEME", raising=False)


@pytest.mark.parametrize("name", ["textual-dark", "textual-light", "dracula", "nord"])
async def test_selected_theme_persists_and_matches_print(tmp_path, name):
    path = tmp_path / "sample.md"
    path.write_text("## Heading\n\n```python\nprint(42)\n```\n")
    app = Viewer(path)
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        app.theme = name
        await pilot.pause()
        heading_color = app.query_one(MarkdownViewer).document.query_one("MarkdownH2").styles.color
    assert load_theme() == name
    assert Viewer(path).theme == name
    palette = PrintPalette(load_theme())
    stream = io.StringIO()
    console = Console(file=stream, force_terminal=True, color_system="truecolor", theme=palette.rich_theme())
    assert console.get_style("markdown.h2").color == heading_color.rich_color
    console.print(Markdown(path.read_text(), code_theme=palette))
    assert "Heading" in stream.getvalue()
    assert "\x1b[" in stream.getvalue()


def test_invalid_settings_and_environment_override(monkeypatch):
    theme_path().parent.mkdir(parents=True)
    theme_path().write_text("unknown-theme")
    assert load_theme() == "textual-dark"
    monkeypatch.setenv("TEXTUAL_THEME", "nord")
    assert load_theme() == "nord"


def test_print_cli_uses_selected_theme(tmp_path, monkeypatch):
    class Terminal(io.StringIO):
        def isatty(self):
            return True

    path = tmp_path / "sample.md"
    path.write_text("## Heading\n")
    output = Terminal()
    monkeypatch.setattr("sys.stdout", output)
    monkeypatch.setenv("COLORTERM", "truecolor")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TEXTUAL_THEME", "nord")
    assert main([str(path), "--print"]) == 0
    color = PrintPalette("nord").rich_theme().styles["markdown.h2"].color.triplet
    assert f"38;2;{color.red};{color.green};{color.blue}" in output.getvalue()
