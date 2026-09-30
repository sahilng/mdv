from unittest.mock import Mock

import pytest
from rich.color import Color
from textual.widgets import MarkdownViewer, TextArea

from mdv.app import Viewer
from mdv.cli import main
from mdv.editor import MarkdownEditor
from mdv.preview import AlignedPreview
from mdv.rendered import RenderMarkdown, SOURCE


SOURCE_TEXT = (
    "# Heading\n\n**bold** and *italic* and `inline`\ncontinued line\n\n"
    "| A | B |\n| - | - |\n| 1 | 2 |\n\n"
    "```python\nx = 1\n```\n\n[link](https://example.com)\n"
)


def source_style(projection, index):
    for strip in projection.rows:
        for segment in strip:
            if segment.style and segment.style.meta.get(SOURCE) == index:
                return segment.style
    raise AssertionError(f"No rendered source character at {index}")


async def settle(app, pilot):
    await pilot.pause(0.15)
    await app.workers.wait_for_complete()
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


async def test_live_continuous_navigation_edit_toggle_undo_and_save(tmp_path):
    path = tmp_path / "live.md"
    path.write_text(SOURCE_TEXT)
    app = Viewer(path, live_edit=True)
    async with app.run_test(size=(80, 25)) as pilot:
        await settle(app, pilot)
        editor = app.query_one(MarkdownEditor)
        assert editor.has_focus
        assert not app.query_one(AlignedPreview).display
        assert len(app.query(TextArea)) == 1
        assert editor.text == SOURCE_TEXT
        projection = editor.projection
        for index, char in enumerate(SOURCE_TEXT):
            if not char.isspace():
                assert index in projection.positions, (index, char)
        for marker in ("#", "**", "```", "https", "| -"):
            assert source_style(projection, SOURCE_TEXT.index(marker)).color == Color.parse("#808080")
        assert source_style(projection, SOURCE_TEXT.index("bold")).bold
        assert source_style(projection, SOURCE_TEXT.index("italic")).italic
        assert projection.offset((3, 0)).y > projection.offset((2, 0)).y
        await pilot.press(*(["down"] * (len(projection.rows) + 5)))
        assert editor.cursor_location == editor.document.end
        await pilot.press("T", "a", "i", "l")
        await settle(app, pilot)
        assert editor.text == SOURCE_TEXT + "Tail"
        assert "Tail" in "\n".join(row.text for row in editor.projection.rows)
        await pilot.press("ctrl+l")
        await settle(app, pilot)
        assert app.query_one(AlignedPreview).display
        await pilot.press("ctrl+l")
        await settle(app, pilot)
        assert editor.cursor_location == editor.document.end
        await pilot.press("ctrl+z")
        await settle(app, pilot)
        assert editor.text == SOURCE_TEXT
        await pilot.press("ctrl+y", "ctrl+s", "escape")
        assert path.read_text() == SOURCE_TEXT + "Tail"
        assert not app.editing


async def test_live_new_file_discard(tmp_path):
    path = tmp_path / "new.md"
    app = Viewer(path, live_edit=True)
    async with app.run_test() as pilot:
        await settle(app, pilot)
        await pilot.press("x", "escape")
        assert app.editing
        await pilot.press("ctrl+d")
        assert not app.editing
        assert not path.exists()


@pytest.mark.parametrize("theme", ["textual-dark", "textual-light", "nord"])
async def test_edit_rendering_uses_read_styles_and_theme(tmp_path, monkeypatch, theme):
    from textual.widgets._markdown import MarkdownH1, MarkdownParagraph, MarkdownFence
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr("mdv.app.save_theme", lambda _: None)
    path = tmp_path / "theme.md"
    path.write_text(SOURCE_TEXT)
    app = Viewer(path, show_toc=False)
    app.theme = theme
    async with app.run_test(size=(90, 35)) as pilot:
        await settle(app, pilot)
        read = app.query_one(MarkdownViewer).document
        expected = {}
        for cls, word in ((MarkdownH1, "Heading"), (MarkdownParagraph, "bold"), (MarkdownFence, "x")):
            block = read.query_one(cls)
            # Include children of code blocks, since their Label paints the code.
            segments = [segment for widget in [block, *block.walk_children()]
                        for row in widget.render_lines(widget.region.size.region) for segment in row]
            expected[word] = next(segment.style for segment in segments if word in segment.text)
        await pilot.press("e")
        await settle(app, pilot)
        for live in (False, True):
            if live:
                await pilot.press("ctrl+l")
                await settle(app, pilot)
            projection = (app.query_one(MarkdownEditor).projection if live
                          else app.query_one(AlignedPreview).projection)
            for word, style in expected.items():
                actual = source_style(projection, SOURCE_TEXT.index(word))
                assert (actual.color, actual.bgcolor, actual.bold, actual.italic) == (
                    style.color, style.bgcolor, style.bold, style.italic
                ), (theme, live, word)
            if not live:
                assert projection.offset((3, 0)).y > projection.offset((2, 0)).y
        app.theme = "dracula"
        await settle(app, pilot)
        renderer = app.query_one(RenderMarkdown)
        assert source_style(app.query_one(MarkdownEditor).projection, 2).color == renderer.query_one(MarkdownH1).rich_style.color


async def test_live_mouse_selection_wrap_resize_and_up(tmp_path):
    path = tmp_path / "wrap.md"
    path.write_text("# Title\n\n" + "你好 **world** " * 40 + "\n\nLast\n")
    app = Viewer(path, live_edit=True)
    async with app.run_test(size=(64, 18)) as pilot:
        await settle(app, pilot)
        editor = app.query_one(MarkdownEditor)
        point = editor.projection.offset((2, 5))
        await pilot.click(editor, offset=(point.x, point.y))
        assert editor.cursor_location == (2, 5)
        await pilot.press("shift+right", "shift+right", "X")
        await settle(app, pilot)
        assert editor.text.splitlines()[2].startswith("你好 **Xrld")
        await pilot.press("ctrl+end")
        assert editor.cursor_location == editor.document.end
        await pilot.press(*(["up"] * 100))
        assert editor.cursor_location == (0, 0)
        await pilot.resize_terminal(45, 15)
        await settle(app, pilot)
        assert app.query_one(RenderMarkdown).region.width == editor.scrollable_content_region.width
        assert max(strip.cell_length for strip in editor.projection.rows) <= editor.scrollable_content_region.width


def test_live_cli(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    viewer = Mock()
    monkeypatch.setattr("mdv.app.Viewer", viewer)
    path = tmp_path / "new.md"
    assert main(["--live-edit", str(path)]) == 0
    viewer.assert_called_once_with(path, show_toc=True, start_editing=True, live_edit=True)


async def test_live_long_code_and_incomplete_markdown(tmp_path):
    path = tmp_path / "code.md"
    text = "```python\nvalue = '" + "x" * 130 + "'\n```\n"
    path.write_text(text)
    app = Viewer(path, live_edit=True)
    async with app.run_test(size=(65, 20)) as pilot:
        await settle(app, pilot)
        editor = app.query_one(MarkdownEditor)
        editor.move_cursor((1, 120))
        assert editor._cursor_offset.y > 1
        assert editor._cursor_offset == editor.wrapped_document.location_to_offset((1, 120))
        assert editor.projection.index((1, 120)) in editor.projection.positions
        await pilot.press("Y")
        await settle(app, pilot)
        assert editor.document.lines[1][120] == "Y"
        # An unclosed fence still renders and every code character remains editable.
        editor.load_text("```python\n" + "z" * 100)
        await settle(app, pilot)
        editor.move_cursor(editor.document.end)
        assert editor.projection.index(editor.document.end) in editor.projection.positions


@pytest.mark.parametrize("theme", ["textual-dark", "textual-light", "nord"])
async def test_live_cursor_overrides_rendered_colors(tmp_path, monkeypatch, theme):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr("mdv.app.save_theme", lambda _: None)
    path = tmp_path / "cursor.md"
    path.write_text("# Heading\n\n```python\nx = 1\n```\n")
    app = Viewer(path, live_edit=True)
    app.theme = theme
    async with app.run_test(size=(80, 25)) as pilot:
        await settle(app, pilot)
        editor = app.query_one(MarkdownEditor)
        editor.cursor_blink = True
        for location in ((0, 0), (0, 2), (3, 0), editor.document.end):
            editor.move_cursor(location)
            editor._cursor_visible = True
            point = editor.projection.offset(location) - editor.scroll_offset
            strip = editor.render_line(point.y)
            style = next(iter(strip.crop(point.x, point.x + 1))).style
            assert style.color == editor._theme.cursor_style.color
            assert style.bgcolor == editor._theme.cursor_style.bgcolor
            editor._cursor_visible = False
            hidden = next(iter(editor.render_line(point.y).crop(point.x, point.x + 1))).style
            assert (hidden.color, hidden.bgcolor) != (style.color, style.bgcolor)


async def test_live_markers_appear_once_and_survive_toggling(tmp_path):
    source = "- apple\n  - nested\n\n3. third\n4. fourth\n\n> quote\n>\n> ---\n\n---\n"
    path = tmp_path / "markers.md"
    path.write_text(source)
    app = Viewer(path, live_edit=True)
    async with app.run_test(size=(80, 30)) as pilot:
        await settle(app, pilot)
        editor = app.query_one(MarkdownEditor)
        for _ in range(2):
            text = "\n".join(row.text for row in editor.projection.rows)
            for line in ("- apple", "- nested", "3. third", "4. fourth", "> quote", "> ---"):
                assert text.count(line) == 1
            assert "●" not in text and "•" not in text
            assert "│" not in text and "━" not in text and "─" not in text
            for index, char in enumerate(source):
                if not char.isspace():
                    assert index in editor.projection.positions
            await pilot.press("ctrl+l")
            await settle(app, pilot)
            preview = app.query_one(AlignedPreview)
            assert "• apple" in "\n".join(row.text for row in preview.rows)
            await pilot.press("ctrl+l")
            await settle(app, pilot)


async def test_edit_burst_coalesces_and_read_view_updates_on_close(tmp_path, monkeypatch):
    import asyncio

    path = tmp_path / "burst.md"
    path.write_text("# Original\n\nText\n")
    app = Viewer(path, start_editing=True)
    async with app.run_test() as pilot:
        await settle(app, pilot)
        renderer = app.query_one(RenderMarkdown)
        reader = app.query_one(MarkdownViewer).document
        editor = app.query_one(MarkdownEditor)
        original_update = renderer.update
        started, release = asyncio.Event(), asyncio.Event()
        updates = []

        async def delayed_update(text):
            updates.append(text)
            if len(updates) == 1:
                started.set()
                await release.wait()
            await original_update(text)

        monkeypatch.setattr(renderer, "update", delayed_update)
        editor.load_text("# Changed\n\nText\n")
        await asyncio.wait_for(started.wait(), timeout=5)
        for char in "abcdef":
            editor.insert(char, location=editor.document.end)
        await pilot.pause()
        assert reader.source == "# Original\n\nText\n"
        assert len(updates) == 1
        release.set()
        await settle(app, pilot)
        assert len(updates) == 2
        assert app.query_one(AlignedPreview).projection.source == editor.text
        await pilot.resize_terminal(65, 20)
        await settle(app, pilot)
        assert len(updates) == 2  # Reflow reuses the mounted Markdown blocks.
        await pilot.press("ctrl+s", "escape")
        assert reader.source == path.read_text() == editor.text
        assert reader.table_of_contents[0][1] == "Changed"


@pytest.mark.parametrize("initial, location", [("one two", (0, 3)), ("", (0, 0)), ("one\n\n\nlast", (1, 0))])
async def test_live_enter_blank_lines_and_undo(tmp_path, initial, location):
    path = tmp_path / "newlines.md"
    path.write_text(initial)
    app = Viewer(path, live_edit=True)
    async with app.run_test() as pilot:
        await settle(app, pilot)
        editor = app.query_one(MarkdownEditor)
        editor.move_cursor(location)
        before = editor.projection.offset(location)
        await pilot.press("enter")
        await settle(app, pilot)
        after = editor.projection.offset(editor.cursor_location)
        assert after.y > before.y
        assert editor.projection.at(after.x, after.y) == editor.cursor_location
        await pilot.press("X")
        await settle(app, pilot)
        assert editor.document.lines[location[0] + 1].startswith("X")
        await pilot.press("ctrl+z")
        await settle(app, pilot)
        assert editor.text != initial
        await pilot.press("ctrl+z")
        await settle(app, pilot)
        assert editor.text == initial


@pytest.mark.parametrize("live", [False, True])
async def test_edit_reuses_shifted_suffix_and_updates_source_mapping(tmp_path, live):
    from textual.widgets._markdown import MarkdownParagraph, MarkdownTable

    path = tmp_path / "reuse.md"
    path.write_text("First\n\n**Last**\n\n| A | B |\n| - | - |\n| 1 | 2 |\n")
    app = Viewer(path, start_editing=True, live_edit=live)
    async with app.run_test() as pilot:
        await settle(app, pilot)
        renderer = app.query_one(RenderMarkdown)
        editor = app.query_one(MarkdownEditor)
        last = next(block for block in renderer.query(MarkdownParagraph) if "Last" in block._content.plain)
        table = renderer.query_one(MarkdownTable)
        editor.insert("new\n", location=(0, 0))
        await settle(app, pilot)
        assert next(block for block in renderer.query(MarkdownParagraph) if "Last" in block._content.plain) is last
        assert renderer.query_one(MarkdownTable) is table
        assert last.source_range == (3, 4)
        projection = editor.projection if live else app.query_one(AlignedPreview).projection
        assert source_style(projection, editor.text.index("Last")).bold
        assert source_style(projection, editor.text.index("1 | 2"))


@pytest.mark.parametrize("source", ["\n\n\n", "text\n\n\n\n", "\n\ntext\n"])
async def test_live_every_blank_source_row_has_a_cursor_stop(tmp_path, source):
    path = tmp_path / "blank.md"
    path.write_text(source)
    app = Viewer(path, live_edit=True)
    async with app.run_test() as pilot:
        await settle(app, pilot)
        editor = app.query_one(MarkdownEditor)
        previous = -1
        for row in range(len(editor.document.lines)):
            point = editor.projection.offset((row, 0))
            assert point.y > previous
            assert editor.projection.at(point.x, point.y) == (row, 0)
            previous = point.y


async def test_cursor_and_source_update_while_markdown_renderer_is_stalled(tmp_path, monkeypatch):
    import asyncio

    path = tmp_path / 'stalled.md'
    path.write_text('# Heading\n\nline one\nline two\n\n' + 'paragraph\n\n' * 100)
    app = Viewer(path, live_edit=True)
    async with app.run_test(size=(70, 20)) as pilot:
        await settle(app, pilot)
        renderer = app.query_one(RenderMarkdown)
        editor = app.query_one(MarkdownEditor)
        original = renderer.update
        entered, release = asyncio.Event(), asyncio.Event()

        async def stalled(source):
            entered.set()
            await release.wait()
            await original(source)

        monkeypatch.setattr(renderer, 'update', stalled)
        editor.move_cursor((2, 4))
        await pilot.press('X')
        await asyncio.wait_for(entered.wait(), 5)
        await pilot.press('enter', 'Y', 'left', 'right', 'down', 'up')
        assert editor.cursor_location == (3, 1)
        assert editor._cursor_offset == editor.wrapped_document.location_to_offset((3, 1))
        assert editor.get_line(3).plain == editor.document.lines[3]
        scroll = editor.scroll_offset
        cursor = editor._cursor_offset
        release.set()
        await settle(app, pilot)
        assert editor.cursor_location == (3, 1)
        assert editor._cursor_offset == cursor
        assert editor.scroll_offset == scroll
