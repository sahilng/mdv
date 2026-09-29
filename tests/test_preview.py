from rich.console import Console

from mdv.preview import render_source


def test_preview_preserves_blank_and_formatting_rows():
    source = (
        "# Heading\n\n\n"
        "one **bold** line\nnext *italic* line\n\n"
        "```python\nx = 1\n\nprint(x)\n```\n\n"
        "Setext heading\n==============\n\n"
        "| A | B |\n| - | - |\n| 1 | 2 |\n"
    )
    rows = render_source(source)
    assert [row.text.plain for row in rows] == [
        "Heading", "", "", "one bold line", "next italic line", "",
        "", "x = 1", "", "print(x)", "", "",
        "Setext heading", "", "", "│ A │ B │", "┼ ─ ┼ ─ ┼", "│ 1 │ 2 │", "",
    ]
    console = Console()
    assert rows[0].text.get_style_at_offset(console, 0).bold
    assert rows[3].text.get_style_at_offset(console, 4).bold
    assert rows[4].text.get_style_at_offset(console, 5).italic


def test_preview_wrap_boundaries_follow_source_even_when_markup_disappears():
    source = "before **bold** [label](https://example.com/a/long/url) after"
    row = render_source(source)[0]
    assert row.text.plain == "before bold label after"
    for word in ("before", "bold", "label", "after"):
        start = source.index(word)
        assert row.slice(start, start + len(word)).plain == word
    start = source.index("https")
    assert row.slice(start, source.index(")")).plain == ""
    console = Console()
    style = row.text.get_style_at_offset(console, row.text.plain.index("label"))
    assert style.meta["@click"] == "link('https://example.com/a/long/url')"


def test_preview_preserves_unicode_tabs_and_escaped_markdown():
    source = "你好 **世界**\n\tcode\nEscaped \\*star\\* &amp; more\n"
    rows = render_source(source)
    assert [row.text.plain for row in rows] == ["你好 世界", "\tcode", "Escaped *star* & more", ""]
    for original, row in zip(source.split("\n"), rows):
        assert len(row.columns) == len(original) + 1
        assert row.columns == sorted(row.columns)


def test_link_destinations_cannot_steal_wrapped_text_positions():
    source = "[hello](hello)hello"
    row = render_source(source)[0]
    assert row.slice(1, 6).plain == "hello"
    assert row.slice(8, 13).plain == ""
    assert row.slice(14, len(source)).plain == "hello"
    # Code containing link-like text is literal, even next to other formatting.
    source = "**bold** `[hello](hello)hello`"
    row = render_source(source)[0]
    assert row.text.plain == "bold [hello](hello)hello"
    assert row.slice(source.rindex("hello"), len(source) - 1).plain == "hello"
