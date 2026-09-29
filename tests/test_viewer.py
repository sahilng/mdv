import io
from unittest.mock import AsyncMock, Mock

import pytest
from textual.command import CommandPalette
from textual.widgets import Markdown, MarkdownViewer, Static, TextArea

from mdv.app import Viewer
from mdv.preview import AlignedPreview
from mdv.cli import main
from mdv.document import load_document


@pytest.mark.parametrize("existing", [False, True])
async def test_start_in_editor_and_save(tmp_path, existing):
    path = tmp_path / "notes.md"
    if existing:
        path.write_text("# Existing\n")
    app = Viewer(path, start_editing=True)
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        editor = app.query_one(TextArea)
        assert app.editing
        assert editor.has_focus
        assert editor.text == ("# Existing\n" if existing else "")
        assert path.exists() is existing
        editor.load_text("# Saved\n")
        await pilot.press("ctrl+s", "escape")
        assert path.read_text() == "# Saved\n"
        assert not app.editing


def test_cli_interactive_validation(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    viewer = Mock()
    monkeypatch.setattr("mdv.app.Viewer", viewer)
    path = tmp_path / "new.md"
    assert main([str(path)]) == 1
    assert "mde" in capsys.readouterr().err
    viewer.assert_not_called()
    assert main(["--edit", str(path)]) == 0
    viewer.assert_called_once_with(path, show_toc=True, start_editing=True)
    viewer.return_value.run.assert_called_once()
    assert not path.exists()
    viewer.reset_mock()
    for invalid in (tmp_path, tmp_path / "new.pdf", tmp_path / "missing" / "new.md"):
        assert main(["--edit", str(invalid)]) == 1
    viewer.assert_not_called()


def test_edit_requires_path_and_terminal(tmp_path, monkeypatch, capsys):
    for args in (["--edit"], ["--edit", "-"], ["--edit", "--print", "file.md"]):
        with pytest.raises(SystemExit) as error:
            main(args)
        assert error.value.code == 2
    capsys.readouterr()
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert main(["--edit", str(tmp_path / "new.md")]) == 1
    assert "interactive terminal" in capsys.readouterr().err


@pytest.mark.parametrize("entry, flag", [("print_main", "--print"), ("edit_main", "--edit")])
def test_shortcuts(entry, flag, monkeypatch):
    from mdv import cli

    main_mock = Mock(return_value=0)
    monkeypatch.setattr(cli, "main", main_mock)
    monkeypatch.setattr("sys.argv", ["shortcut", "notes.md", "--no-toc"])
    assert getattr(cli, entry)() == 0
    main_mock.assert_called_once_with([flag, "notes.md", "--no-toc"])


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


@pytest.mark.parametrize("dirty", [False, True])
async def test_quit_directly_from_editor(tmp_path, monkeypatch, dirty):
    path = tmp_path / "edit.md"
    path.write_text("Original")
    app = Viewer(path, start_editing=True)
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        exit_app = Mock()
        monkeypatch.setattr(app, "exit", exit_app)
        editor = app.query_one(TextArea)
        if dirty:
            editor.load_text("Changed")
        await pilot.press("ctrl+p", "ctrl+q")
        exit_app.assert_not_called()
        await pilot.press("escape", "ctrl+q")
        if dirty:
            exit_app.assert_not_called()
            assert editor.text == "Changed"
            assert path.read_text() == "Original"
            await pilot.press("ctrl+s", "ctrl+q")
            assert path.read_text() == "Changed"
        exit_app.assert_called_once_with()
        assert app.editing


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
        assert editor.region.right <= app.query_one(AlignedPreview).region.x
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


async def test_edit_scroll_sync(tmp_path):
    path = tmp_path / "scroll.md"
    path.write_text("\n\n".join(f"## Section {i}\n\n" + "Some text. " * 20 for i in range(40)))
    app = Viewer(path, start_editing=True)
    async with app.run_test(size=(100, 30)) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        editor = app.query_one(TextArea)
        preview = app.query_one(AlignedPreview)
        assert editor.max_scroll_y > 0
        assert preview.max_scroll_y > 0
        for source, target in ((editor, preview), (preview, editor)):
            for fraction in (1, 0):
                source.scroll_to(y=source.max_scroll_y * fraction, animate=False, immediate=True)
                await pilot.pause()
                assert target.scroll_y == pytest.approx(target.max_scroll_y * fraction, abs=1)
                assert source.scroll_y == pytest.approx(source.max_scroll_y * fraction, abs=1)

        editor.move_cursor(editor.document.end)
        await pilot.pause()
        assert preview.scroll_y == preview.max_scroll_y
        await pilot.press("enter", "x")
        await pilot.pause()
        assert preview.scroll_y == pytest.approx(preview.max_scroll_y, abs=1)
        await pilot.resize_terminal(80, 24)
        await pilot.pause()
        assert preview.scroll_y / preview.max_scroll_y == pytest.approx(
            editor.scroll_y / editor.max_scroll_y, abs=0.01
        )
        await pilot.press("ctrl+s", "escape")
        previous_editor_y = editor.scroll_y
        preview.scroll_to(y=0, animate=False, immediate=True)
        await pilot.pause()
        assert editor.scroll_y == previous_editor_y


async def test_preview_rows_align_with_source(tmp_path):
    source = (
        "# First\n\n\n"
        "## Middle\n\n"
        + " ".join(f"word{i}" for i in range(100))
        + "\ncontinued **bold** text\n\n"
        "> Quote\n>\n> Another paragraph\n\n"
        "- First item\n- Second item\n\n"
        "```python\nprint('hello')\n```\n\n"
        "| A | B |\n| - | - |\n| 1 | 2 |\n\n"
        "## Last\n\n" + "Tail paragraph\n\n" * 30
    )
    path = tmp_path / "blocks.md"
    path.write_text(source)
    app = Viewer(path, start_editing=True)
    async with app.run_test(size=(100, 30)) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        editor = app.query_one(TextArea)
        preview = app.query_one(AlignedPreview)

        async def check_alignment():
            assert preview.content_region.y == editor.content_region.y
            # Native block margins and table borders consume rendered rows;
            # scrolling follows source positions rather than equal row counts.
            for line_index, source_line in enumerate(editor.document.lines):
                for marker in ("First", "Middle", "continued", "Another", "Second", "print", "Last"):
                    if marker in source_line:
                        offset = preview.projection.offset((line_index, source_line.index(marker)))
                        assert marker in preview.rows[offset.y].text
            continuation = editor.document.lines.index("continued **bold** text")
            assert preview.projection.offset((continuation, 0)).y > preview.projection.offset((continuation - 1, 0)).y
            for source_pane, target in ((editor, preview), (preview, editor)):
                for fraction in (0, 1):
                    source_pane.scroll_to(y=int(source_pane.max_scroll_y * fraction), animate=False, immediate=True)
                    await pilot.pause()
                    assert target.scroll_y == target.max_scroll_y * fraction

        await check_alignment()
        await pilot.resize_terminal(61, 24)
        await pilot.pause()
        await check_alignment()
        editor.load_text("Intro\n\n" + editor.text)
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        await check_alignment()
        await pilot.press("ctrl+s", "escape")
        assert not preview.display
        assert app.query_one(MarkdownViewer).display
        assert path.read_text() == "Intro\n\n" + source


async def test_edit_scroll_sync_short_document(tmp_path):
    path = tmp_path / "short.md"
    path.write_text("# Short\n")
    app = Viewer(path, start_editing=True)
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("pagedown", "pageup")
        assert app.query_one(TextArea).scroll_y == 0
        assert app.query_one(AlignedPreview).scroll_y == 0


async def test_aligned_preview_links_and_empty_edits(tmp_path, monkeypatch):
    path = tmp_path / "links.md"
    path.write_text("[Website](https://example.com)\n\n" + "Paragraph\n\n" * 30 + "## Target\n\n" + "Tail\n\n" * 30)
    browser = Mock(return_value=True)
    monkeypatch.setattr("mdv.app.webbrowser.open", browser)
    app = Viewer(path, start_editing=True)
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        editor = app.query_one(TextArea)
        preview = app.query_one(AlignedPreview)
        link = preview.projection.offset((0, 1))
        await pilot.click(preview, offset=(
            preview.content_region.x - preview.region.x + link.x,
            preview.content_region.y - preview.region.y + link.y,
        ))
        await pilot.pause()
        browser.assert_called_once_with("https://example.com", new=2)
        preview.action_link("#target")
        await pilot.pause()
        target_y = editor.wrapped_document.location_to_offset((62, 0)).y
        assert editor.scroll_y == target_y
        assert preview.scroll_y == preview.projection.offset((62, 0)).y
        editor.load_text("")
        await pilot.pause()
        assert all(not row.text.strip() for row in preview.rows)
        assert editor.scroll_y == preview.scroll_y == 0
        await pilot.press("ctrl+d")
        assert not app.editing
        await pilot.press("e")
        await pilot.pause()
        assert "Website" in "".join(row.text for row in preview.rows)


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
