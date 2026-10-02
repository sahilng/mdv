"""Read-mode Markdown layout with source coordinates attached to rendered cells.

Textual owns block layout, CSS, tables, and syntax highlighting. Source metadata
survives its renderer and lets the editor navigate the resulting terminal cells.
"""

import asyncio
from functools import cached_property, lru_cache
from bisect import bisect_right
from dataclasses import dataclass, field
from collections.abc import Sequence
from collections import OrderedDict
import re

from rich.cells import cell_len
from rich.segment import Segment
from textual.content import Content, Span
from textual.geometry import Offset, Region
from textual.strip import Strip
from textual.style import Style
from textual.widgets import Markdown, TextArea
from textual.widgets._markdown import MarkdownBlock, MarkdownListItem, MarkdownFence, MarkdownParagraph, MarkdownTable, MarkdownTableContent
from markdown_it import MarkdownIt
from markdown_it.token import Token

from .preview import cached_source_columns
from .html import HTMLMarkdownParser


SOURCE = "mdv_source"
GRAY = "#808080"


def located(content: Content, source: str, start: int, *, controls: bool, breaks: bool) -> Content:
    return _located(content.plain, tuple(content.spans), source, start, controls, breaks)


@lru_cache(maxsize=512)
def _located(plain, original_spans, source, start, controls, breaks) -> Content:
    """Project the read renderer's inline styles onto source, or annotate output."""
    content = Content(plain, spans=original_spans)
    columns = cached_source_columns(source, content.plain)
    if controls:
        spans = []
        text = source if breaks else source.replace("\n", " ")
        styles = [[] for _ in content.plain]
        for span in content.spans:
            for position in range(span.start, min(span.end, len(styles))):
                styles[position].append(span.style)
        for index, char in enumerate(source):
            first, last = columns[index:index + 2]
            visible = last == first + 1 and content.plain[first:last] == char
            if not visible and char == "\n" and last == first + 1:
                visible = True
            if visible:
                for style in styles[first] if first < len(styles) else []:
                    # Links select text while editing, rather than executing actions.
                    if isinstance(style, Style) and style.meta.get("@click"):
                        spans.append(Span(index, index + 1, "$link-color underline"))
                    else:
                        spans.append(Span(index, index + 1, style))
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


class CachedMarkdownFence(MarkdownFence):
    @classmethod
    @lru_cache(maxsize=128)
    def highlight(cls, code, language, ansi=False, dark=False):
        return super().highlight(code, language, ansi=ansi, dark=dark)


class RenderMarkdown(Markdown):
    """Use the normal Markdown blocks, adding source syntax only when requested."""

    DEFAULT_CSS = """
    RenderMarkdown.controls MarkdownBullet { display: none; }
    RenderMarkdown.controls MarkdownBlockQuote { border-left: none; padding: 0; }
    RenderMarkdown.controls MarkdownTableContent { keyline: none; }
    """

    def __init__(self, *, controls: bool = False, breaks: bool = False, **kwargs):
        super().__init__("", open_links=False, parser_factory=lambda: HTMLMarkdownParser(editing=True), **kwargs)
        self.controls = controls
        self.breaks = breaks

    def get_block_class(self, token_type):
        if token_type in {"fence", "code_block"}:
            return CachedMarkdownFence
        return super().get_block_class(token_type)

    def on_resize(self) -> None:
        # Mounting may finish before the renderer's new height is laid out.
        # Take another projection once its final geometry is available.
        self.app.schedule_scroll_sync()

    async def update(self, markdown: str) -> None:
        """Keep unchanged mounted blocks when updating an editing document."""
        async with self.lock:
            parser = getattr(self, "_edit_parser", None)
            if parser is None:
                parser = self._edit_parser = (self._parser_factory() if self._parser_factory
                                              else MarkdownIt("gfm-like"))
            env = {}
            tokens = await asyncio.to_thread(parser.parse, markdown, env)
            old = list(self.children)
            previous = getattr(self, "_block_keys", [])
            previous_source = self.source
            self._markdown = markdown
            self._table_of_contents = None
            self._theme = self.app.theme
            lines = markdown.splitlines(keepends=True)
            offsets = [0]
            for line in lines:
                offsets.append(offsets[-1] + len(line))
            environment = repr(env)
            prefix_length = 0
            for before, after in zip(previous_source, markdown):
                if before != after:
                    break
                prefix_length += 1
            suffix_length = 0
            for before, after in zip(reversed(previous_source[prefix_length:]),
                                     reversed(markdown[prefix_length:])):
                if before != after:
                    break
                suffix_length += 1
            line_delta = markdown.count("\n") - previous_source.count("\n")
            self._reuse_blocks = {}
            self._source_lines, self._source_offsets = lines, offsets
            mode = (self.controls, self.breaks, self.app.theme, environment)
            for block, key in zip(old, previous):
                if key[5:] != mode:
                    continue
                cls, first, last, start, raw = key[:5]
                if start + len(raw) <= prefix_length:
                    new_first, new_last = first, last
                elif suffix_length and start >= len(previous_source) - suffix_length:
                    new_first, new_last = first + line_delta, last + line_delta
                else:
                    continue
                self._reuse_blocks[(cls, new_first, new_last, raw)] = (block, start)
            blocks = list(self._parse_markdown(tokens))
            self._reuse_blocks.clear()
            keys = []
            for block in blocks:
                first, last = block.source_range
                keys.append((type(block), first, last, offsets[min(first, len(lines))],
                             "".join(lines[first:last]), self.controls, self.breaks,
                             self.app.theme, environment))
            prefix = 0
            while prefix < min(len(previous), len(keys)) and previous[prefix] == keys[prefix]:
                prefix += 1
            suffix = 0
            while (suffix < min(len(previous), len(keys)) - prefix
                   and (previous[-1 - suffix][0], previous[-1 - suffix][4:])
                   == (keys[-1 - suffix][0], keys[-1 - suffix][4:])):
                suffix += 1
            old_end = len(old) - suffix
            new_end = len(blocks) - suffix
            with self.app.batch_update():
                # Reuse unchanged suffixes even when typing shifts their source offsets.
                for index in range(suffix):
                    if previous[-1 - index] != keys[-1 - index]:
                        self._update_block(old[-1 - index], blocks[-1 - index])
                for block in old[prefix:old_end]:
                    await block.remove()
                added = blocks[prefix:new_end]
                if added:
                    if suffix:
                        await self.mount_all(added, before=old[old_end])
                    else:
                        await self.mount_all(added)
            self._block_keys = keys
            self._last_parsed_line = len(lines) - (1 if lines and lines[-1].strip() else 0)
            self.post_message(Markdown.TableOfContentsUpdated(self, self.table_of_contents))

    def _update_block(self, existing, replacement):
        if existing is replacement:
            return
        existing.source_range = replacement.source_range
        existing._token = replacement._token
        existing._inline_token = replacement._inline_token
        def first_source(content):
            return next((span.style.meta[SOURCE] for span in content.spans
                         if isinstance(span.style, Style) and SOURCE in span.style.meta), 0)

        # These blocks have identical source and visual styles. Retain their
        # rendered content and adjust only its source origin after earlier edits.
        existing._mdv_source_shift = first_source(replacement._content) - first_source(existing._content)
        if isinstance(existing, MarkdownFence):
            shift = first_source(replacement._mdv_content) - first_source(existing._mdv_content)
            for child in existing.walk_children():
                child._mdv_source_shift = shift
        def mounted_blocks(widget):
            for child in widget.children:
                if isinstance(child, MarkdownBlock):
                    yield child
                else:
                    yield from mounted_blocks(child)

        children = existing._blocks or list(mounted_blocks(existing))
        updated_children = []
        for child in replacement._blocks:
            # Textual lays list items out in Horizontal/Vertical containers,
            # discarding the parser's list-item widgets during composition.
            updated_children.extend(child._blocks if isinstance(child, MarkdownListItem) else [child])
        for child, updated in zip(children, updated_children):
            self._update_block(child, updated)
        if isinstance(existing, MarkdownTable):
            headers, rows = existing._get_headers_and_rows()
            updated_headers, updated_rows = replacement._get_headers_and_rows()
            old_cells = [*headers, *[cell for row in rows for cell in row]]
            updated_cells = [*updated_headers, *[cell for row in updated_rows for cell in row]]
            table = existing.query_one(MarkdownTableContent)
            for cell, old, new in zip(table.children, old_cells, updated_cells):
                cell._mdv_source_shift = first_source(new) - first_source(old)

    def _reuse_block(self, cls, first, last):
        raw = "".join(self._source_lines[first:last])
        cached = self._reuse_blocks.pop((cls, first, last, raw), None)
        if cached is None:
            return None
        block, old_start = cached
        row_delta = first - block.source_range[0]
        character_delta = self._source_offsets[min(first, len(self._source_lines))] - old_start
        seen = set()

        def shift(widget):
            if id(widget) in seen:
                return
            seen.add(id(widget))
            widget._mdv_source_shift = getattr(widget, "_mdv_source_shift", 0) + character_delta
            if isinstance(widget, MarkdownBlock):
                a, b = widget.source_range
                widget.source_range = (a + row_delta, b + row_delta)
                for child in widget._blocks:
                    shift(child)
            for child in widget.children:
                shift(child)
        shift(block)
        return block

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
                            "".join(lines[consumed:first]).removesuffix("\n").removesuffix("\r"),
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

        def blocks():
            # Reuse whole top-level token groups before Textual constructs any
            # widgets or inline content. Parsing the full source still resolves
            # references and block boundaries correctly after structural edits.
            group = []
            depth = 0
            for token in layout_tokens():
                group.append(token)
                depth += token.nesting
                if depth:
                    continue
                opening = group[0]
                kind = opening.tag if opening.type == "heading_open" else opening.type
                cls = self.get_block_class(kind) if kind in self.BLOCKS else None
                reused = (self._reuse_block(cls, *opening.map)
                          if cls is not None and opening.map else None)
                if reused is not None:
                    yield reused, True
                else:
                    for block in super(RenderMarkdown, self)._parse_markdown(group):
                        yield block, False
                group = []

        consumed = 0
        for block, reused in blocks():
            first, last = block.source_range
            if self.controls and first > consumed:
                # Whitespace and reference definitions are editable too.
                yield self.syntax_block("".join(lines[consumed:first]).removesuffix("\n").removesuffix("\r"), offsets[consumed], consumed, first)
            if not self.controls and self.breaks and first > consumed + 1 and not "".join(lines[consumed:first]).strip():
                spacer = self.syntax_block("", offsets[consumed], consumed, first)
                spacer.styles.height = first - consumed - 1
                yield spacer
            if not reused:
                decorate(block)
            yield block
            if self.controls and block._token.type == "heading_open" and last > first + 1:
                yield self.syntax_block(lines[last - 1].rstrip("\r\n"), offsets[last - 1], last - 1, last)
            consumed = max(consumed, last)
        if self.controls and (consumed < len(lines) or not tokens or self.source.endswith("\n")):
            yield self.syntax_block("".join(lines[consumed:]), offsets[consumed], consumed, len(lines))

    def syntax_block(self, raw: str, offset: int, first: int, last: int):
        reused = self._reuse_block(MarkdownParagraph, first, last)
        if reused is not None:
            return reused
        token = Token("paragraph_open", "p", 1)
        token.map = [first, last]
        block = MarkdownParagraph(self, token)
        parts = []
        for line in raw.split("\n"):
            parts.append(located(Content(), line, offset, controls=True, breaks=True) if line
                         else Content(" ").stylize(Style.from_meta({SOURCE: offset})))
            offset += len(line) + 1
        content = Content("\n").join(parts)
        block.set_content(content)
        block.styles.margin = 0
        return block


class ProjectedRows(Sequence[Strip]):
    """Build source metadata strips only for rows actually drawn or inspected."""

    CACHE_LIMIT = 512

    def __init__(self, layouts):
        self.layouts = layouts
        self.max_width = getattr(layouts, "max_width", None)
        if self.max_width is None:
            self.max_width = max((width for _, _, width in layouts), default=0)
        self._cache = OrderedDict()

    def __len__(self):
        return len(self.layouts)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[row] for row in range(*index.indices(len(self)))]
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        if index not in self._cache:
            from rich.style import Style as RichStyle
            segments, sources, width = self.layouts[index]
            mapped = []
            for segment, source in zip(segments, sources):
                if source is not None and segment.style is not None:
                    original = segment.style.meta.get(SOURCE)
                    if original is not None and original != source:
                        segment = Segment(segment.text, segment.style + RichStyle.from_meta({SOURCE: source}))
                mapped.append(segment)
            self._cache[index] = Strip(mapped, width)
            if len(self._cache) > self.CACHE_LIMIT:
                self._cache.popitem(last=False)
        else:
            self._cache.move_to_end(index)
        return self._cache[index]


@dataclass
class Projection:
    rows: Sequence[Strip] = field(default_factory=list)
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


class AlignedLayouts(Sequence):
    """Compute glyph layout and source coordinates only for requested rows."""

    CACHE_LIMIT = 512

    def __init__(self, document, editor, glyphs, offsets):
        self.lines = editor.document.lines.copy()
        self.offsets = offsets
        self.glyphs = glyphs
        self.indent_width = editor.indent_width
        self.headings = {token.map[0] for token in document.source_tokens
                         if token.type == "heading_open" and token.tag == "h1" and token.map}
        self.width = (editor.wrap_width if document.controls
                      else getattr(document, "projection_width", document.region.width))
        self.style = document.rich_style
        self.boundaries = []
        self.line_starts = []
        self.rows = []
        self._cache = OrderedDict()
        self.position_maps = {}
        for row, line in enumerate(self.lines):
            boundaries = [0, *editor.wrapped_document.get_offsets(row), len(line)]
            self.boundaries.append(boundaries)
            self.line_starts.append(len(self.rows))
            self.rows.extend((row, start, end) for start, end in zip(boundaries, boundaries[1:]))
        # Rendered editing text is no wider than its source. A source-width
        # bound avoids measuring every off-screen row to size the scroll view.
        self.max_width = max(self.width, editor.wrap_width) if editor.soft_wrap else max(
            self.width, max((cell_len(line.expandtabs(self.indent_width)) for line in self.lines), default=0))

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, row):
        if row < 0:
            row += len(self)
        if not 0 <= row < len(self):
            raise IndexError(row)
        if row not in self._cache:
            line, start, end = self.rows[row]
            segments, sources, positions, x = [], [], {}, 0
            for column in range(start, end):
                index = self.offsets[line] + column
                positions[index] = Offset(x, row)
                for segment in self.glyphs.get(index, []):
                    text = segment.text.replace("\n", " ")
                    if "\t" in text:
                        text = (" " * x + text).expandtabs(self.indent_width)[x:]
                    segments.append(Segment(text, segment.style))
                    sources.append(index)
                    x += cell_len(text)
            positions[self.offsets[line] + end] = Offset(x, row)
            if line in self.headings and len(self.boundaries[line]) == 2:
                padding = max(0, (self.width - x) // 2)
                if padding:
                    segments.insert(0, Segment(" " * padding, self.style))
                    sources.insert(0, None)
                    x += padding
                    positions = {index: point + Offset(padding, 0) for index, point in positions.items()}
            self.position_maps[row] = positions
            self._cache[row] = (segments, sources, x)
            if len(self._cache) > self.CACHE_LIMIT:
                oldest, _ = self._cache.popitem(last=False)
                del self.position_maps[oldest]
        else:
            self._cache.move_to_end(row)
        return self._cache[row]


class AlignedProjection(Projection):
    def __init__(self, layouts, source):
        self.source = source
        self.layouts = layouts
        self.rows = ProjectedRows(layouts)
        self.line_offsets = layouts.offsets[:-1]

    @cached_property
    def positions(self):
        positions = {}
        for row in range(len(self.layouts)):
            self.layouts[row]
            positions.update(self.layouts.position_maps[row])
        return positions

    @cached_property
    def ordered(self):
        return sorted(self.positions)

    @cached_property
    def visual(self):
        visual = {}
        for index, point in self.positions.items():
            visual.setdefault(point.y, []).append((point.x, index))
        return visual

    @cached_property
    def visual_rows(self):
        return sorted(self.visual)

    def offset(self, location):
        index = self.index(location)
        line, column = self.location(index)
        boundaries = self.layouts.boundaries[line]
        wrap = min(len(boundaries) - 2, bisect_right(boundaries, column) - 1)
        row = self.layouts.line_starts[line] + wrap
        self.layouts[row]
        return self.layouts.position_maps[row][index]

    def at(self, x, y):
        row = max(0, min(len(self.layouts) - 1, y))
        self.layouts[row]
        positions = self.layouts.position_maps[row]
        index = min(positions, key=lambda index: abs(positions[index].x - x))
        return self.location(index)


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
        cached = getattr(widget, "_mdv_glyph_cache", None)
        visual_style = widget.visual_style
        if (cached is None or cached[0] is not content or cached[1] != visual_style
                or cached[2] != document.app.theme):
            mapped = {}
            for text, style in content.render(visual_style, end="", parse_style=widget._get_style):
                index = style.meta.get(SOURCE)
                if index is not None and text != "\n":
                    mapped.setdefault(index, []).append(Segment(text, style.rich_style))
            cached = widget._mdv_glyph_cache = (content, visual_style, document.app.theme, mapped)
        shift = getattr(widget, "_mdv_source_shift", 0)
        if shift:
            glyphs.update((index + shift, segments) for index, segments in cached[3].items())
        else:
            glyphs.update(cached[3])

    # Syntax-only table separators and rules still occupy their source rows.
    lines = editor.document.lines
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line) + 1)
    for token in ([] if document.controls else document.source_tokens):
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

    return AlignedProjection(AlignedLayouts(document, editor, glyphs, offsets), document.source)


def styled_source(document: RenderMarkdown, lines: list[str]):
    """Read visual style runs directly, without rendering source metadata cells."""
    from rich.text import Text

    length = sum(len(line) + 1 for line in lines)
    cells = [None] * length
    for widget in document.walk_children():
        content = widget.render()
        if not isinstance(content, Content):
            continue
        source_cache = getattr(widget, "_mdv_source_styles", None)
        if (source_cache is not None and source_cache[0] is content
                and source_cache[1] == widget.visual_style and source_cache[2] == document.app.theme):
            shift = getattr(widget, "_mdv_source_shift", 0)
            for index, style in source_cache[3]:
                index += shift
                if 0 <= index < length:
                    cells[index] = style
            continue
        visual_spans = []
        source_spans = []
        for span in content.spans:
            if isinstance(span.style, Style) and SOURCE in span.style.meta:
                source_spans.append(span)
            else:
                visual_spans.append(span)
        if not source_spans:
            continue
        key = (content.plain, tuple(visual_spans), widget.visual_style, document.app.theme)
        cached = getattr(widget, "_mdv_visual_cache", None)
        if cached is None or cached[0] != key:
            styles = []
            for text, style in Content(content.plain, spans=visual_spans).render(
                    widget.visual_style, end="", parse_style=widget._get_style):
                styles.extend([style.rich_style.clear_meta_and_links()] * len(text))
            cached = widget._mdv_visual_cache = (key, styles)
        styles = cached[1]
        mapped_styles = [(span.style.meta[SOURCE], styles[span.start])
                         for span in source_spans if span.start < len(styles)]
        widget._mdv_source_styles = (content, widget.visual_style, document.app.theme, mapped_styles)
        shift = getattr(widget, "_mdv_source_shift", 0)
        for index, style in mapped_styles:
            index += shift
            if 0 <= index < length:
                cells[index] = style
    result = []
    offset = 0
    cache = getattr(document, "_mdv_line_styles", {})
    for line in lines:
        runs = []
        start = 0
        active = cells[offset] if line else None
        for column in range(1, len(line) + 1):
            style = cells[offset + column] if column < len(line) else None
            if (style is not active and style != active) or column == len(line):
                if active is not None:
                    runs.append((start, column, active))
                start, active = column, style
        key = (line, tuple(runs))
        styled = cache.get(key)
        if styled is None:
            styled = Text(line, end="", no_wrap=True)
            for start, end, style in runs:
                styled.stylize(style, start, end)
            cache[key] = styled
        result.append(styled)
        offset += len(line) + 1
    document._mdv_line_styles = cache if len(cache) < 2048 else {}
    return result
