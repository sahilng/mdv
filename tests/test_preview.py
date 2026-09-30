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


def test_cached_source_projection_distinguishes_styles():
    source = "**word**"
    bold = located(Content("word").stylize("bold"), source, 0, controls=True, breaks=True)
    italic = located(Content("word").stylize("italic"), source, 0, controls=True, breaks=True)
    assert any(span.style == "bold" for span in bold.spans)
    assert any(span.style == "italic" for span in italic.spans)
    assert not any(span.style == "bold" for span in italic.spans)


def test_multiline_mapping_repeated_prose():
    source = "**word** repeated\n" * 1000
    rendered = "word repeated\n" * 1000
    columns = source_columns(source, rendered)
    assert len(columns) == len(source) + 1
    assert columns == sorted(columns)
    for row in (0, 10, 999):
        assert columns[row * len("**word** repeated\n") + 2] == row * len("word repeated\n")


def test_unfinished_bullet_is_not_a_setext_heading_in_editor():
    from mdv.html import HTMLMarkdownParser

    for source in ('Normal text\n-', 'Normal text\n- ',
                   'Normal text\n  - ', '> Normal text\n> - '):
        assert not any(token.type == 'heading_open'
                       for token in HTMLMarkdownParser(editing=True).parse(source))
        assert any(token.type == 'heading_open' and token.tag == 'h2'
                   for token in HTMLMarkdownParser().parse(source))
    for underline in ('--', '---', '----'):
        assert any(token.type == 'heading_open' and token.tag == 'h2'
                   for token in HTMLMarkdownParser(editing=True).parse('Heading\n' + underline))


def test_cached_inline_parsing_preserves_references_and_isolates_mutations():
    from unittest.mock import Mock
    from mdv.html import HTMLMarkdownParser

    parser = HTMLMarkdownParser(editing=True)
    parser.inline.parse = Mock(wraps=parser.inline.parse)
    source = '**bold** [label][target]\nnext ![alt](image.png)\n\n[target]: /first\n'
    initial = parser.parse(source)
    calls = parser.inline.parse.call_count
    inline = next(token for token in initial if token.type == 'inline')
    inline.children[0].meta['source'] = 123
    next(token for token in inline.children if token.type == 'softbreak').type = 'hardbreak'
    next(token for token in inline.children if token.type == 'link_open').attrs['href'] = '/mutated'
    image = next(token for token in inline.children if token.type == 'image')
    image.children[0].content = 'mutated'
    again = parser.parse(source)
    assert parser.inline.parse.call_count == calls
    assert [token.as_dict() for token in again] == [
        token.as_dict() for token in HTMLMarkdownParser(editing=True).parse(source)]
    changed = source.replace('/first', '/second')
    actual = parser.parse(changed)
    assert parser.inline.parse.call_count > calls
    assert [token.as_dict() for token in actual] == [
        token.as_dict() for token in HTMLMarkdownParser(editing=True).parse(changed)]


def test_cached_inline_parsing_matches_fresh_parser_after_structural_edits():
    from mdv.html import HTMLMarkdownParser

    parser = HTMLMarkdownParser(editing=True)
    for source in ('text\n- ', 'text\n- item', '> **bold**\n> next',
                   '```python\n**bold**\n```', '**bold**\nnext',
                   '<b>bold</b> <code>x</code>', '[label][ref]\n\n[ref]: /url',
                   '[label][ref]', '| A | B |\n| - | - |\n| **a** | b |'):
        for _ in range(2):
            assert [token.as_dict() for token in parser.parse(source)] == [
                token.as_dict() for token in HTMLMarkdownParser(editing=True).parse(source)]
