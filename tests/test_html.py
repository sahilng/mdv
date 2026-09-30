from rich.console import Console
from textual.widgets import MarkdownViewer
from textual.widgets._markdown import MarkdownH1, MarkdownParagraph, MarkdownTable

from mdv.app import Viewer
from mdv.editor import MarkdownEditor
from mdv.html import HTMLMarkdownParser, PrintMarkdown
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
        await pilot.press("e", "ctrl+l")
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
        await pilot.press('e', 'ctrl+l')
        await settle(app, pilot)
        assert app.query_one(MarkdownEditor).text == source
