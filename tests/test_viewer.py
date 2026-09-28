import io
from unittest.mock import AsyncMock, Mock

import pytest
from textual.command import CommandPalette
from textual.widgets import Markdown, MarkdownViewer, Static, TextArea

from mdv.app import Viewer
from mdv.cli import main
from mdv.document import load_document


@pytest.mark.parametrize("dirty", [False, True])
async def test_escape_palette_preserves_edit_mode(tmp_path, dirty):
    path = tmp_path / "edit.md"
    path.write_text("# Original\n")
    app = Viewer(path)
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.press("e")
        editor = app.query_one(TextArea)
        viewer = app.query_one(MarkdownViewer)
        document_screen = app.screen
        if dirty:
            editor.load_text("# Changed\n")
        await pilot.press("ctrl+p")
        assert isinstance(app.screen, CommandPalette)
        await pilot.press("escape")
        assert app.screen is document_screen
        assert app.editing
        assert document_screen.has_class("editing")
        assert editor.has_focus
        assert not viewer.show_table_of_contents
        assert editor.text == ("# Changed\n" if dirty else "# Original\n")
        assert app.dirty is dirty
        await pilot.press("ctrl+d" if dirty else "escape")
        assert not app.editing
        assert not document_screen.has_class("editing")
        assert viewer.show_table_of_contents


async def test_edit_preview_save_and_discard(tmp_path):
    path = tmp_path / "edit.md"
    path.write_text("# Original\n")
    app = Viewer(path)
    async with app.run_test(size=(100, 30)) as pilot:
        await app.workers.wait_for_complete()
        await pilot.press("e")
        editor = app.query_one(TextArea)
        viewer = app.query_one(MarkdownViewer)
        assert editor.has_focus
        assert editor.region.right <= viewer.region.x
        assert not viewer.show_table_of_contents
        editor.load_text("# Updated\n")
        await pilot.pause()
        assert viewer.document.table_of_contents[0][1] == "Updated"
        assert path.read_text() == "# Original\n"
        await pilot.press("escape")
        assert app.editing
        await pilot.press("ctrl+s", "escape")
        assert path.read_text() == "# Updated\n"
        assert not app.editing
        assert viewer.show_table_of_contents
        await pilot.press("e", "q", "r", "t", "e", "j", "k", "g")
        assert app.editing
        assert "qrtejkg" in editor.text
        await pilot.press("ctrl+d")
        assert not app.editing
        assert path.read_text() == "# Updated\n"
        assert viewer.document.table_of_contents[0][1] == "Updated"


async def test_save_failure_keeps_edits(tmp_path, monkeypatch):
    path = tmp_path / "edit.md"
    path.write_text("Original")
    app = Viewer(path)
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.press("e")
        app.query_one(TextArea).load_text("Changed")
        monkeypatch.setattr(type(path), "write_text", Mock(side_effect=OSError("Read-only")))
        await pilot.press("ctrl+s", "escape")
        assert app.dirty
        assert app.query_one(TextArea).text == "Changed"
        assert path.read_text() == "Original"


async def test_converted_document_cannot_be_edited(tmp_path):
    path = tmp_path / "example.html"
    path.write_text("<h1>Hello</h1>")
    app = Viewer(path)
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.press("e")
        assert not app.editing
        assert path.read_text() == "<h1>Hello</h1>"


def test_markdown_and_html(tmp_path):
    markdown = tmp_path / "example.MD"
    markdown.write_text("\ufeff# Hello\n", encoding="utf-8")
    assert load_document(markdown) == "# Hello\n"
    html = tmp_path / "example.html"
    html.write_text("<h1>Hello</h1><p>A <strong>bold</strong> word.</p>")
    converted = load_document(html)
    assert "# Hello" in converted
    assert "**bold**" in converted


def test_pptx(tmp_path):
    from pptx import Presentation

    document = Presentation()
    slide = document.slides.add_slide(document.slide_layouts[1])
    slide.shapes.title.text = "Office document"
    slide.placeholders[1].text = "Conversion works."
    path = tmp_path / "example.pptx"
    document.save(path)
    assert "Conversion works." in load_document(path)


def test_cli(tmp_path, capsys, monkeypatch):
    path = tmp_path / "example.md"
    path.write_text("# Hello")
    assert main([str(path), "--raw"]) == 0
    assert capsys.readouterr().out == "# Hello\n"
    assert main([str(tmp_path / "missing.pdf")]) == 1
    assert "Not a file" in capsys.readouterr().err
    monkeypatch.setattr("sys.stdin", io.StringIO("# Piped\n"))
    assert main([]) == 0
    assert capsys.readouterr().out == "# Piped\n"


async def test_interaction_and_reload(tmp_path):
    path = tmp_path / "example.md"
    path.write_text("# First\n\n" + "Paragraph\n\n" * 100)
    app = Viewer(path)
    async with app.run_test(size=(100, 30)) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        viewer = app.query_one(MarkdownViewer)
        assert viewer.document.table_of_contents[0][1] == "First"
        await pilot.press("t")
        assert not viewer.show_table_of_contents
        await pilot.press("G")
        await pilot.pause()
        assert viewer.scroll_y > 0
        await pilot.press("g")
        await pilot.pause()
        assert viewer.scroll_y == 0
        path.write_text("# Changed\n")
        await pilot.press("r")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert viewer.document.table_of_contents[0][1] == "Changed"
        path.unlink()
        await pilot.press("r")
        await app.workers.wait_for_complete()
        assert "Unable to load" in str(app.query_one("#status", Static).render())
        await pilot.press("q")


async def test_link_click_does_not_trigger_default_file_navigation(tmp_path, monkeypatch):
    browser = Mock(return_value=True)
    monkeypatch.setattr("mdv.app.webbrowser.open", browser)
    path = tmp_path / "links.md"
    path.write_text("[Website](https://example.com)\n\n# Heading\n")
    app = Viewer(path)
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        viewer = app.query_one(MarkdownViewer)
        navigate = AsyncMock()
        monkeypatch.setattr(viewer, "go", navigate)
        for href in ("https://example.com", "missing.md", "#heading"):
            viewer.document.post_message(Markdown.LinkClicked(viewer.document, href))
            await pilot.pause()
        navigate.assert_not_awaited()
        browser.assert_called_once_with("https://example.com", new=2)
        assert app.path == path


async def test_browser_failure_shows_error(tmp_path, monkeypatch):
    path = tmp_path / "links.md"
    path.write_text("# Links\n")
    browser = Mock(return_value=False)
    monkeypatch.setattr("mdv.app.webbrowser.open", browser)
    app = Viewer(path)
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        viewer = app.query_one(MarkdownViewer)
        notify = Mock()
        monkeypatch.setattr(viewer, "notify", notify)
        for failure in (None, OSError("Browser unavailable")):
            browser.side_effect = failure
            viewer.document.post_message(Markdown.LinkClicked(viewer.document, "https://example.com"))
            await pilot.pause()
            assert notify.call_args.kwargs["title"] == "Could not open browser"
            assert notify.call_args.kwargs["severity"] == "error"
