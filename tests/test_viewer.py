import io
from unittest.mock import AsyncMock, Mock

from textual.widgets import Markdown, MarkdownViewer, Static

from mdv.app import Viewer
from mdv.cli import main
from mdv.document import load_document


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
