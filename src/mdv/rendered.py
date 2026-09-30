"""Read-mode Markdown layout with source coordinates attached to rendered cells.

Textual owns block layout, CSS, tables, and syntax highlighting. Source metadata
survives its renderer and lets the editor navigate the resulting terminal cells.
"""

from bisect import bisect_right
from dataclasses import dataclass, field
import re

from rich.cells import cell_len
from rich.segment import Segment
from textual.content import Content, Span
from textual.geometry import Offset, Region
from textual.strip import Strip
from textual.style import Style
from textual.widgets import Markdown, TextArea
from textual.widgets._markdown import MarkdownFence, MarkdownParagraph
from markdown_it.token import Token

from .preview import source_columns


SOURCE = "mdv_source"
GRAY = "#808080"


def located(content: Content, source: str, start: int, *, controls: bool, breaks: bool) -> Content:
    """Project the read renderer's inline styles onto source, or annotate output."""
    columns = source_columns(source, content.plain)
    if controls:
        spans = []
        # Keep newlines inside paragraphs soft in live mode, as in read mode.
        text = source if breaks else source.replace("\n", " ")
        for index, char in enumerate(source):
            first, last = columns[index:index + 2]
            visible = last == first + 1 and content.plain[first:last] == char
            if not visible and char == "\n" and last == first + 1:
                visible = True
            if visible:
                for span in content.spans:
                    if span.start <= first < span.end:
                        # Links select text while editing, rather than executing actions.
                        if isinstance(span.style, Style) and span.style.meta.get("@click"):
                            spans.append(Span(index, index + 1, "$link-color underline"))
                        else:
                            spans.append(Span(index, index + 1, span.style))
            else:
                spans.append(Span(index, index + 1, GRAY))
            spans.append(Span(index, index + 1, Style.from_meta({SOURCE: start + index})))
        return Content(text, spans=spans)
    spans = list(content.spans)
    assigned = set()
    for index in range(len(source)):
        first, last = columns[index:index + 2]
        for offset in range(first, last):
            if offset not in assigned:
                spans.append(Span(offset, offset + 1, Style.from_meta({SOURCE: start + index})))
                assigned.add(offset)
    return Content(content.plain, spans=spans)


class RenderMarkdown(Markdown):
    """Use the normal Markdown blocks, adding source syntax only when requested."""

    DEFAULT_CSS = """
    RenderMarkdown.controls MarkdownBullet { display: none; }
    RenderMarkdown.controls MarkdownBlockQuote { border-left: none; padding: 0; }
    RenderMarkdown.controls MarkdownTableContent { keyline: none; }
    """

    def __init__(self, *, controls: bool = False, breaks: bool = False, **kwargs):
        super().__init__("", open_links=False, **kwargs)
        self.controls = controls
        self.breaks = breaks

    def _parse_markdown(self, tokens):
        tokens = list(tokens)
        self.source_tokens = tokens
        lines = self.source.splitlines(keepends=True)
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line))
        # Table inline tokens have no source range. Assign each its raw cell.
        row = None
        cell_column = 0
        table_header = False
        cell_index = 0
        for token in tokens:
            if token.type == "thead_open":
                table_header = True
            elif token.type == "thead_close":
                table_header = False
            if token.type == "tr_open":
                row = token.map[0]
                cell_column = 0
                cell_index = 0
            elif token.type == "tr_close":
                row = None
            elif token.type == "inline" and row is not None:
                raw = lines[row].rstrip("\r\n")
                if cell_column == 0 and raw.lstrip().startswith("|"):
                    cell_column = raw.index("|") + 1
                match = re.search(r"(?<!\\)\|", raw[cell_column:])
                end = cell_column + match.start() if match else len(raw)
                first = 0 if cell_index == 0 else cell_column
                last = min(len(raw), end + 1)
                token.meta["source_slice"] = (offsets[row] + first, raw[first:last])
                if self.controls and table_header and row + 1 < len(lines):
                    separator = lines[row + 1].rstrip("\r\n")
                    bars = [match.start() for match in re.finditer(r"(?<!\\)\|", separator)]
                    boundaries = [0, *[bar + 1 for bar in bars if bar > 0], len(separator)]
                    if cell_index + 1 < len(boundaries):
                        a, b = boundaries[cell_index:cell_index + 2]
                        token.meta["separator_slice"] = (offsets[row + 1] + a, separator[a:b])
                cell_index += 1
                cell_column = end + 1
            if self.breaks and token.type == "inline":
                for child in token.children or []:
                    if child.type == "softbreak":
                        child.type = "hardbreak"

        def decorate(block):
            inline = block._inline_token
            if inline is not None:
                if "source_slice" in inline.meta:
                    start, raw = inline.meta["source_slice"]
                elif inline.map:
                    first, last = inline.map
                    start = offsets[first]
                    raw = "".join(lines[first:last]).rstrip("\r\n")
                else:
                    start, raw = 0, inline.content
                rendered = block._content
                if not self.controls:
                    if "source_slice" in inline.meta:
                        # Keep table cell separators on the source row.
                        leading = "│" if raw.startswith("|") else ""
                        trailing = "│" if raw.endswith("|") else ""
                        inner = raw[int(bool(leading)):len(raw) - int(bool(trailing))]
                        left = len(inner) - len(inner.lstrip())
                        right = len(inner) - len(inner.rstrip())
                        rendered = Content(leading + " " * left) + rendered + " " * right + trailing
                    else:
                        raw_lines = raw.split("\n")
                        parts = rendered.split("\n", allow_blank=True)
                        if len(parts) == len(raw_lines):
                            decorated = []
                            for source_line, part in zip(raw_lines, parts):
                                prefix = re.match(r"^(\s*(?:>\s*)*)(?:(?:[-+*]|\d+[.)])\s+)?", source_line).group()
                                prefix = re.sub(r"[-+*](?=\s)", "•", prefix).replace(">", "│")
                                decorated.append(Content(prefix) + part)
                            rendered = Content("\n").join(decorated)
                content = located(rendered, raw, start, controls=self.controls, breaks=self.breaks)
                if "separator_slice" in inline.meta:
                    separator_start, separator = inline.meta["separator_slice"]
                    content += "\n" + located(Content(), separator, separator_start, controls=True, breaks=True)
                block.set_content(content)
            elif isinstance(block, MarkdownFence):
                first, last = block.source_range
                code_start = first + (block._token.type == "fence")
                tail = lines[last - 1].rstrip("\r\n") if last > code_start else ""
                closing = (block._token.type == "fence" and
                           bool(re.match(r"^\s*" + re.escape(block._token.markup[0]) + r"{3,}\s*$", tail)))
                code_source = "".join(lines[code_start:last - int(closing)]).rstrip("\r\n")
                content = located(block._highlighted_code, code_source, offsets[code_start],
                                  controls=self.controls, breaks=True)
                if self.controls and block._token.type == "fence":
                    opening = located(Content(), lines[first].rstrip("\r\n"), offsets[first],
                                      controls=True, breaks=True)
                    content = opening + "\n" + content
                    if closing:
                        content += "\n" + located(Content(), tail, offsets[last - 1], controls=True, breaks=True)
                block._highlighted_code = content
                block._mdv_content = content
            for child in block._blocks:
                decorate(child)
            if self.controls and block._token.type == "blockquote_open":
                # Quote-only lines have syntax even when the parser omits them.
                children = []
                consumed = block.source_range[0]
                for child in block._blocks:
                    first, last = child.source_range
                    if first > consumed:
                        children.append(self.syntax_block(
                            "".join(lines[consumed:first]).rstrip("\r\n"),
                            offsets[consumed], consumed, first))
                    children.append(child)
                    consumed = max(consumed, last)
                last = block.source_range[1]
                if consumed < last:
                    children.append(self.syntax_block(
                        "".join(lines[consumed:last]).rstrip("\r\n"),
                        offsets[consumed], consumed, last))
                block._blocks = children

        def layout_tokens():
            for token in tokens:
                if self.controls and token.type == "hr":
                    # The native renderer yields rules outside the container
                    # stack. A syntax paragraph keeps nested rules in order.
                    opening = Token("paragraph_open", "p", 1)
                    opening.map = token.map
                    inline = Token("inline", "", 0)
                    inline.map = token.map
                    inline.children = []
                    yield opening
                    yield inline
                    yield Token("paragraph_close", "p", -1)
                else:
                    yield token

        consumed = 0
        for block in super()._parse_markdown(layout_tokens()):
            first, last = block.source_range
            if self.controls and first > consumed:
                # Whitespace and reference definitions are editable too.
                yield self.syntax_block("".join(lines[consumed:first]).rstrip("\r\n"), offsets[consumed], consumed, first)
            if self.breaks and first > consumed + 1 and not "".join(lines[consumed:first]).strip():
                spacer = self.syntax_block("", offsets[consumed], consumed, first)
                spacer.styles.height = first - consumed - 1
                yield spacer
            decorate(block)
            yield block
            if self.controls and block._token.type == "heading_open" and last > first + 1:
                yield self.syntax_block(lines[last - 1].rstrip("\r\n"), offsets[last - 1], last - 1, last)
            consumed = max(consumed, last)
        if self.controls and (consumed < len(lines) or not tokens or self.source.endswith("\n")):
            yield self.syntax_block("".join(lines[consumed:]).rstrip("\r\n"), offsets[consumed], consumed, len(lines))

    def syntax_block(self, raw: str, offset: int, first: int, last: int):
        token = Token("paragraph_open", "p", 1)
        token.map = [first, last]
        block = MarkdownParagraph(self, token)
        content = located(Content(), raw, offset, controls=True, breaks=True)
        if not raw:
            content = Content(" ").stylize(Style.from_meta({SOURCE: offset}))
        block.set_content(content)
        block.styles.margin = 0
        if not raw and offset < len(self.source):
            block.styles.height = 0
        return block


@dataclass
class Projection:
    rows: list[Strip] = field(default_factory=list)
    positions: dict[int, Offset] = field(default_factory=dict)
    source: str = ""

    def __post_init__(self):
        self.line_offsets = [0]
        for index, char in enumerate(self.source):
            if char == "\n":
                self.line_offsets.append(index + 1)
        self.ordered = sorted(self.positions)
        self.visual: dict[int, list[tuple[int, int]]] = {}
        for index, offset in self.positions.items():
            self.visual.setdefault(offset.y, []).append((offset.x, index))
        self.visual_rows = sorted(self.visual)

    def index(self, location):
        row, column = location
        return min(len(self.source), self.line_offsets[min(row, len(self.line_offsets) - 1)] + column)

    def location(self, index):
        row = bisect_right(self.line_offsets, index) - 1
        return row, index - self.line_offsets[row]

    def offset(self, location):
        index = self.index(location)
        if index in self.positions:
            return self.positions[index]
        if not self.ordered:
            return Offset(0, 0)
        insertion = bisect_right(self.ordered, index)
        nearest = self.ordered[max(0, insertion - 1)]
        if insertion < len(self.ordered):
            following = self.ordered[insertion]
            if self.location(following)[0] == self.location(index)[0]:
                nearest = following
        point = self.positions[nearest]
        return Offset(point.x + max(0, min(1, index - nearest)), point.y)

    def at(self, x, y):
        if not self.visual_rows:
            return (0, 0)
        row = min(self.visual_rows, key=lambda row: abs(row - y))
        _, index = min(self.visual[row], key=lambda pair: abs(pair[0] - x))
        return self.location(index)


def snapshot(document: RenderMarkdown) -> Projection:
    """Composite mounted read-renderer widgets, including borders and backgrounds."""
    width, height = document.region.size
    origin = document.region.offset
    widgets = [document, *document.walk_children()]
    width = max([width, *[widget.region.right - origin.x for widget in widgets]])
    base = document.rich_style
    rows = [Strip.blank(width, base) for _ in range(height)]
    for widget in widgets:
        if not widget.display or not widget.visible:
            continue
        region = widget.region.translate(-origin)
        if not region.width or not region.height:
            continue
        # Paint parent backgrounds first, then their children.
        for y, strip in enumerate(widget.render_lines(Region(0, 0, region.width, region.height)), region.y):
            if 0 <= y < height:
                left, right = max(0, region.x), min(width, region.right)
                if right > left:
                    rows[y] = Strip.join((rows[y].crop(0, left),
                                          strip.crop(left - region.x, right - region.x),
                                          rows[y].crop(right, width)))
    positions = {}
    for y, strip in enumerate(rows):
        x = 0
        for segment in strip:
            index = segment.style.meta.get(SOURCE) if segment.style else None
            if index is not None:
                positions.setdefault(index, Offset(x, y))
            x += cell_len(segment.text)
    # Source newlines / EOF have no glyph; attach a cursor stop after the last
    # mapped character on that source row. This also handles empty documents.
    for index in [i for i, c in enumerate(document.source) if c == "\n"] + [len(document.source)]:
        if index not in positions and index - 1 in positions:
            previous = positions[index - 1]
            positions[index] = Offset(min(width - 1, previous.x + max(1, cell_len(document.source[index - 1:index]))), previous.y)
    return Projection(rows, positions, document.source)


def aligned_snapshot(document: RenderMarkdown, editor: TextArea) -> Projection:
    """Lay out the shared renderer's styled content on the source wrap rows.

    Read-mode margins, borders and wrapping cannot add rows here. Read the
    unwrapped content so even text clipped by a narrow table remains available.
    """
    glyphs = {}
    for widget in document.walk_children():
        content = widget.render()
        if not isinstance(content, Content):
            continue
        mapped = {}
        for text, style in content.render(widget.visual_style, end="", parse_style=widget._get_style):
            index = style.meta.get(SOURCE)
            if index is not None and text != "\n":
                mapped.setdefault(index, []).append(Segment(text, style.rich_style))
        glyphs.update(mapped)

    # Syntax-only table separators and rules still occupy their source rows.
    lines = editor.document.lines
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line) + 1)
    for token in document.source_tokens:
        if token.type == "table_open":
            row = token.map[0] + 1
            text = lines[row].replace("|", "┼").replace("-", "─").replace(":", "─")
        elif token.type == "hr":
            row = token.map[0]
            text = "─" * len(lines[row])
        else:
            continue
        for column, char in enumerate(text):
            index = offsets[row] + column
            glyphs[index] = [Segment(char, document.rich_style)]

    rows, positions = [], {}
    for line_index, line in enumerate(lines):
        boundaries = [0, *editor.wrapped_document.get_offsets(line_index), len(line)]
        for start, end in zip(boundaries, boundaries[1:]):
            segments, x = [], 0
            for column in range(start, end):
                index = offsets[line_index] + column
                positions[index] = Offset(x, len(rows))
                for segment in glyphs.get(index, []):
                    text = segment.text.replace("\n", " ")
                    if "\t" in text:
                        text = (" " * x + text).expandtabs(editor.indent_width)[x:]
                    segments.append(Segment(text, segment.style))
                    x += cell_len(text)
            positions[offsets[line_index] + end] = Offset(x, len(rows))
            rows.append(Strip(segments))
    return Projection(rows, positions, document.source)
