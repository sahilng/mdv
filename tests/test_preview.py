from textual.content import Content

from mdv.preview import source_columns
from mdv.rendered import located, SOURCE


def test_mapping_removed_syntax_and_repeated_link_destinations():
    source = "[hello](hello)hello"
    columns = source_columns(source, "hellohello")
    assert columns[1:7] == list(range(6))
    assert columns[8] == columns[13] == 5
    assert columns[14:] == list(range(5, 11))


def test_live_source_preserves_every_character_and_style():
    source = "**bold** &amp; 你好"
    content = Content("bold & 你好").stylize("bold", 0, 4)
    result = located(content, source, 10, controls=True, breaks=True)
    assert result.plain == source
    locations = [span.style.meta[SOURCE] for span in result.spans
                 if not isinstance(span.style, str) and SOURCE in span.style.meta]
    assert locations == list(range(10, 10 + len(source)))
    assert any(span.style == "bold" and span.start == 2 for span in result.spans)
    assert any(span.style == "#808080" and span.start == 0 for span in result.spans)


def test_live_soft_breaks_and_split_source_breaks():
    source = "one\ntwo"
    live = located(Content("one two"), source, 0, controls=True, breaks=False)
    split = located(Content("one\ntwo"), source, 0, controls=False, breaks=True)
    assert live.plain == "one two"
    assert split.plain == source


def test_mapping_unicode_tabs_and_escaped_markdown():
    for source, rendered in (("你好 **世界**", "你好 世界"),
                             ("\\*star\\* &amp;", "*star* &"),
                             ("\tcode", "\tcode")):
        columns = source_columns(source, rendered)
        assert len(columns) == len(source) + 1
        assert columns == sorted(columns)
        assert columns[-1] == len(rendered)
