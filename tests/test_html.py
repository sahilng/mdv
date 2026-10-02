from rich.console import Console
from markdown_it.token import Token
from textual.widgets import MarkdownViewer
from textual.widgets._markdown import MarkdownH1, MarkdownParagraph, MarkdownTable

from mdv.app import Viewer
from mdv.editor import MarkdownEditor
from mdv.html import (HTMLMarkdownParser, MarkdownAlert,
                      PrintMarkdown, copy_inline_tokens)
from mdv.preview import AlignedPreview
from test_live_editor import settle, source_style


def test_html_tokens_formatting_links_and_code():
    text = 'hello <b>bold</b> <i>italic</i> <a href="https://example.com">link</a><br>end\n\n`<b>code</b>`'
    tokens = HTMLMarkdownParser().parse(text)
    children = tokens[1].children
    assert any(t.type == "strong_open" for t in children)
    assert any(t.type == "em_open" for t in children)
    assert any(t.type == "link_open" and t.attrs["href"] == "https://example.com" for t in children)
    assert any(t.type == "hardbreak" for t in children)
    assert tokens[-2].children[0].content == "<b>code</b>"
    console = Console(record=True, width=80)
    console.print(PrintMarkdown(text))
    output = console.export_text()
    assert "bold" in output and "<b>bold" not in output
    assert "<b>code</b>" in output


def test_cached_inline_tokens_keep_values_and_isolate_mutable_fields():
    child = Token("text", "", 0, content="child", meta={"nested": [1]})
    original = Token("link_open", "a", 1, attrs={"href": "https://example.com"},
                     map=[1, 2], level=2, children=[child], content="link",
                     markup="[", info="info", meta={"nested": [2]},
                     block=True, hidden=True)
    cloned = copy_inline_tokens([original])[0]
    assert cloned == original
    cloned.attrs["href"] = "changed"
    cloned.map[0] = 9
    cloned.meta["nested"].append(3)
    cloned.children[0].meta["nested"].append(4)
    assert original.attrs["href"] == "https://example.com"
    assert original.map == [1, 2]
    assert original.meta["nested"] == [2]
    assert child.meta["nested"] == [1]


async def test_html_blocks_read_and_live_source(tmp_path):
    text = '<h1>Title</h1>\n<p>A <strong>bold</strong> &amp; <em>italic</em> paragraph.</p>\n<table><tr><th>A</th></tr><tr><td>B</td></tr></table>\n'
    path = tmp_path / "html.md"
    path.write_text(text)
    app = Viewer(path)
    async with app.run_test(size=(90, 35)) as pilot:
        await settle(app, pilot)
        reader = app.query_one(MarkdownViewer).document
        assert reader.query_one(MarkdownH1)._content.plain == "Title"
        assert reader.query_one(MarkdownTable)
        assert reader.query_one(MarkdownParagraph)._content.plain == "A bold & italic paragraph."
        await pilot.press("e")
        await settle(app, pilot)
        editor = app.query_one(MarkdownEditor)
        assert editor.text == text
        for index, char in enumerate(text):
            if not char.isspace():
                assert index in editor.projection.positions, (index, char)
        assert source_style(editor.projection, text.index("bold")).bold
        assert source_style(editor.projection, 0).color.name == "#808080"


def test_html_comments_scripts_and_partial_tags():
    parsed = HTMLMarkdownParser().parse('<div>hello<script>hidden()</script><style>.hidden{}</style><!-- hidden -->world</div>')
    assert 'hidden' not in ''.join(t.content for t in parsed)
    for text in ('hello </b>', 'hello <b>world', '<div><b>unfinished', '```html\n<b>literal</b>\n```'):
        console = Console(record=True)
        console.print(PrintMarkdown(text))


def test_inline_html_code():
    children = HTMLMarkdownParser().parse("Text <code>x &lt; 2</code> tail")[1].children
    assert any(token.type == "code_inline" and token.content == "x < 2" for token in children)


def test_tasks_footnotes_and_alerts_print():
    source = ('- [x] Done\n- [ ] Pending\n\nA note[^details].\n\n'
              '[^details]: The **detail**.\n\n> [!WARNING]\n> Be careful.\n')
    tokens = HTMLMarkdownParser().parse(source)
    tasks = [token.meta["task"] for token in tokens if "task" in token.meta]
    assert tasks == [True, False]
    assert any(token.meta.get("alert") == "warning" for token in tokens)
    assert any(child.content == "[1]" for token in tokens for child in token.children or [])
    console = Console(width=80)
    with console.capture() as capture:
        console.print(PrintMarkdown(source))
    output = capture.get()
    assert "☑ Done" in output and "☐ Pending" in output
    assert "A note[1]." in output and "1 The detail." in output
    assert "Warning: Be careful." in output
    assert "[!WARNING]" not in output and "[^details]" not in output


def test_all_alert_labels_and_footnote_reference_order():
    source = ("First[^later], second[^earlier].\n\n"
              "[^earlier]: Defined first.\n\n[^later]: Defined second.\n\n"
              + "\n\n".join(f"> [!{kind}]\n> Message." for kind in
                              ("NOTE", "TIP", "IMPORTANT", "WARNING", "CAUTION")))
    tokens = HTMLMarkdownParser().parse(source)
    assert [token.meta["alert"] for token in tokens if "alert" in token.meta] == [
        "note", "tip", "important", "warning", "caution"]
    references = [child.content for token in tokens for child in token.children or []
                  if child.type == "text" and child.content in {"[1]", "[2]"}]
    assert references == ["[1]", "[2]"]
    lists = [token.attrs["start"] for token in tokens if token.type == "ordered_list_open"]
    assert lists == [2, 1]


async def test_tasks_footnotes_and_alerts_reader_and_editor(tmp_path):
    source = ('- [x] Done\n- [ ] Pending\n\nA note[^details].\n\n'
              '[^details]: The detail.\n\n> [!NOTE]\n> Useful information.\n')
    path = tmp_path / "features.md"
    path.write_text(source)
    app = Viewer(path)
    async with app.run_test(size=(90, 35)) as pilot:
        await settle(app, pilot)
        reader = app.query_one(MarkdownViewer).document
        from textual.widgets._markdown import MarkdownBullet
        assert [bullet.symbol for bullet in reader.query(MarkdownBullet)][:2] == ["☑ ", "☐ "]
        assert reader.query_one(MarkdownAlert).has_class("mdv-alert-note")
        assert any("The detail." in paragraph._content.plain for paragraph in reader.query(MarkdownParagraph))
        await pilot.press("e")
        await settle(app, pilot)
        editor = app.query_one(MarkdownEditor)
        assert editor.text == source
        assert source.index("The detail.") in editor.projection.positions
        assert source.index("Useful information") in editor.projection.positions
        await pilot.press("ctrl+l")
        await settle(app, pilot)
        assert editor.text == source
        preview = app.query_one(AlignedPreview).projection
        shown = "\n".join(row.text for row in preview.rows)
        assert "☑ Done" in shown and "☐ Pending" in shown


async def test_details_summary_expands_markdown_body(tmp_path):
    from textual.widgets import Collapsible
    from textual.widgets._markdown import MarkdownFence

    source = '# API\n\n<details>\n<summary><strong>Example Request</strong></summary>\n\n```sh\ncurl https://example.com\n```\n\n</details>\n\nTail\n'
    path = tmp_path / 'details.md'
    path.write_text(source)
    app = Viewer(path)
    async with app.run_test() as pilot:
        await settle(app, pilot)
        detail = app.query_one(Collapsible)
        assert detail.title == 'Example Request'
        assert detail.collapsed
        await pilot.click(detail.query_one("CollapsibleTitle"))
        await pilot.pause()
        assert not detail.collapsed
        assert detail.query_one(MarkdownFence).display
        await pilot.press('e')
        await settle(app, pilot)
        assert app.query_one(MarkdownEditor).text == source
