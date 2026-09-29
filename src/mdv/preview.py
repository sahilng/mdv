"""A Markdown preview laid out on the editor's source rows."""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from markdown_it import MarkdownIt
from markdown_it.rules_inline import image, link
from markdown_it.token import Token
from rich.style import Style
from rich.syntax import Syntax
from rich.text import Text
from textual.geometry import Size
from textual.message import Message
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.widgets import TextArea


def track_link_syntax(rule, image_link: bool = False):
    """Record the syntax removed by a valid link, without guessing at URLs."""
    def tracked(state, silent):
        start, first_token = state.pos, len(state.tokens)
        if not rule(state, silent):
            return False
        if not silent:
            label_start = start + (2 if image_link else 1)
            label_end = state.md.helpers.parseLinkLabel(state, label_start - 1, True)
            for token in state.tokens[first_token:]:
                if token.type == ("image" if image_link else "link_open"):
                    token.meta["hidden_source"] = [(start, label_start), (label_end, state.pos)]
                    break
        return True
    return tracked


_parser = MarkdownIt("gfm-like")
_parser.inline.ruler.at("link", track_link_syntax(link))
_parser.inline.ruler.at("image", track_link_syntax(image, image_link=True))


@dataclass
class SourceLine:
    text: Text
    columns: list[int]

    def slice(self, start: int, end: int) -> Text:
        return self.text[self.columns[start] : self.columns[end]]


def source_columns(source: str, rendered: str, env: dict | None = None) -> list[int]:
    """Locate rendered characters in the source, including removed delimiters.

    This lets the preview break at the editor's *source* wrap boundaries, even
    when formatting or a link destination makes the rendered text shorter.
    """
    if source == rendered:
        return list(range(len(source) + 1))
    # Repeated words in URLs must never be mistaken for visible text after a
    # link. Mask only syntax the Markdown parser actually recognized as a link.
    if "[" in source:
        masked = list(source)
        for token in _parser.parseInline(source, env or {})[0].children or []:
            for start, end in token.meta.get("hidden_source", []):
                masked[start:end] = "\0" * (end - start)
        source = "".join(masked)
    columns = [0] * (len(source) + 1)
    for _, start, end, output_start, output_end in SequenceMatcher(
        None, source, rendered, autojunk=False
    ).get_opcodes():
        if start == end:
            columns[start] = output_end
        else:
            for offset in range(end - start + 1):
                columns[start + offset] = output_start + offset * (output_end - output_start) // (end - start)
    columns[0] = 0
    columns[-1] = len(rendered)
    return columns


def inline_text(tokens: list[Token], style: Style = Style()) -> Text:
    result = Text()
    styles = [style]
    for token in tokens:
        kind = token.type
        if kind.endswith("_open"):
            extra = {
                "strong_open": Style(bold=True),
                "em_open": Style(italic=True),
                "s_open": Style(strike=True),
            }.get(kind, Style())
            if kind == "link_open":
                href = token.attrGet("href") or ""
                extra = Style(underline=True, meta={"@click": f"link({href!r})"})
            styles.append(styles[-1] + extra)
        elif kind.endswith("_close"):
            if len(styles) > 1:
                styles.pop()
        elif kind in {"softbreak", "hardbreak"}:
            result.append("\n")
        elif kind == "code_inline":
            result.append(token.content, styles[-1] + Style(reverse=True))
        elif kind == "image":
            result.append(inline_text(token.children or [], styles[-1] + Style(italic=True)))
        else:
            result.append(token.content, styles[-1])
    return result


def render_source(source: str) -> list[SourceLine]:
    """Render blocks without losing blank lines or syntax-only source rows."""
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    lines = source.split("\n")
    result = [SourceLine(Text(), [0] * (len(line) + 1)) for line in lines]
    env: dict = {}

    def assign(start: int, end: int, rendered: Text) -> None:
        raw = "\n".join(lines[start:end])
        columns = source_columns(raw, rendered.plain, env)
        offset = 0
        for line_index in range(start, end):
            length = len(lines[line_index])
            first, last = columns[offset], columns[offset + length]
            text = rendered[first:last]
            # Multiline inline code may collapse a newline to a space.
            text.plain = text.plain.replace("\n", " ")
            result[line_index] = SourceLine(
                text, [column - first for column in columns[offset : offset + length + 1]]
            )
            offset += length + 1

    heading = False
    table = False
    table_header = False
    cells: list[Text] = []
    row_range = (0, 0)
    for token in _parser.parse(source, env):
        kind = token.type
        if kind == "heading_open":
            heading = True
        elif kind == "heading_close":
            heading = False
        elif kind == "table_open":
            table = True
            # Keep the Markdown table separator on its original row.
            separator = token.map[0] + 1
            assign(separator, separator + 1, Text(re.sub(r"[-:]", "─", lines[separator]).replace("|", "┼"), style="dim"))
        elif kind == "table_close":
            table = False
        elif kind == "thead_open":
            table_header = True
        elif kind == "thead_close":
            table_header = False
        elif kind == "tr_open":
            cells = []
            row_range = tuple(token.map)
        elif kind == "tr_close":
            raw_cells = re.split(r"(?<!\\)\|", lines[row_range[0]])
            leading = len(raw_cells) > len(cells) and not raw_cells[0].strip()
            trailing = len(raw_cells) > len(cells) and not raw_cells[-1].strip()
            if leading:
                raw_cells = raw_cells[1:]
            if trailing:
                raw_cells = raw_cells[:-1]
            padded = []
            for raw, cell in zip(raw_cells, cells):
                cell = Text(" " * (len(raw) - len(raw.lstrip()))) + cell
                cell.pad_right(max(0, len(raw) - len(cell)))
                padded.append(cell)
            rendered = Text("│" if leading else "") + Text("│").join(padded)
            rendered.append("│" if trailing else "")
            assign(*row_range, rendered)
        elif kind == "inline" and token.map:
            text = inline_text(token.children or [], Style(bold=heading or table_header))
            if table:
                cells.append(text)
                continue
            start, end = token.map
            # Retain list/quote markers without adding layout rows or margins.
            parts = text.split("\n", allow_blank=True)
            if len(parts) == end - start:
                for index, part in enumerate(parts):
                    prefix = re.match(r"^(\s*(?:>\s*)*)(?:(?:[-+*]|\d+[.)])\s+)?", lines[start + index]).group()
                    prefix = re.sub(r"[-+*](?=\s)", "•", prefix).replace(">", "│")
                    assign(start + index, start + index + 1, Text(prefix, style="dim") + part)
            else:
                assign(start, end, text)
        elif kind in {"fence", "code_block"} and token.map:
            start, end = token.map
            if kind == "fence":
                start += 1  # Opening and closing fences remain blank rows.
            code = Syntax(token.content, token.info.split()[0] if token.info.strip() else "text", theme="ansi_dark")
            code_lines = code.highlight(token.content).split("\n")
            for index, line in enumerate(code_lines[: end - start]):
                assign(start + index, start + index + 1, line)
        elif kind in {"hr", "html_block"} and token.map:
            start, end = token.map
            for index in range(start, end):
                text = "─" * len(lines[index]) if kind == "hr" else lines[index]
                assign(index, index + 1, Text(text, style="dim"))
    return result


class AlignedPreview(ScrollView, can_focus=True):
    DEFAULT_CSS = """
    AlignedPreview {
        width: 1fr;
        height: 1fr;
        border: tall $border-blurred;
        padding: 0 1;
        background: $surface;
        color: $foreground;
        overflow: hidden auto;
        scrollbar-gutter: stable;
    }
    """

    class LinkClicked(Message):
        def __init__(self, href: str) -> None:
            super().__init__()
            self.href = href

    def __init__(self) -> None:
        super().__init__()
        self._source: str | None = None
        self._lines: list[SourceLine] = []
        self.rows: list[Text] = []

    def reflow(self, editor: TextArea) -> None:
        if editor.text != self._source:
            self._source = editor.text
            self._lines = render_source(editor.text)
        rows = []
        for index, source in enumerate(editor.document.lines):
            boundaries = [0, *editor.wrapped_document.get_offsets(index), len(source)]
            for start, end in zip(boundaries, boundaries[1:]):
                row = self._lines[index].slice(start, end)
                row.expand_tabs(editor.indent_width)
                rows.append(row)
        self.rows = rows
        self.virtual_size = Size(0, len(rows))
        self.refresh()

    def render_line(self, y: int) -> Strip:
        row = y + self.scroll_offset.y
        width = self.scrollable_content_region.width
        if row >= len(self.rows):
            return Strip.blank(width, self.rich_style)
        text = self.rows[row]
        return Strip(text.render(self.app.console), text.cell_len).adjust_cell_length(width).apply_style(self.rich_style)

    def action_link(self, href: str) -> None:
        self.post_message(self.LinkClicked(href))
