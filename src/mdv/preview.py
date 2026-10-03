"""Source mapping and the split-view rendered Markdown pane."""

from difflib import SequenceMatcher
from functools import lru_cache

from markdown_it import MarkdownIt
from markdown_it.rules_inline import image, link
from textual.geometry import Size
from textual.message import Message
from textual.scroll_view import ScrollView
from textual.strip import Strip


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


def source_columns(source: str, rendered: str, env: dict | None = None) -> list[int]:
    """Locate rendered characters in the source, including removed delimiters.

    This lets the preview break at the editor's *source* wrap boundaries, even
    when formatting or a link destination makes the rendered text shorter.
    """
    if source == rendered:
        return list(range(len(source) + 1))
    # Source and output retain the same paragraph breaks in editing mode.
    # Match each line independently to avoid quadratic work on repeated prose.
    source_lines = source.split("\n")
    rendered_lines = rendered.split("\n")
    if len(source_lines) > 1 and len(source_lines) == len(rendered_lines):
        columns = []
        output_offset = 0
        for source_line, rendered_line in zip(source_lines, rendered_lines):
            columns.extend(output_offset + column for column in source_columns(source_line, rendered_line, env))
            output_offset += len(rendered_line) + 1
        return columns
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


@lru_cache(maxsize=2048)
def cached_source_columns(source: str, rendered: str) -> tuple[int, ...]:
    """Reuse inline mappings independently of their document position."""
    return tuple(source_columns(source, rendered))


class AlignedPreview(ScrollView, can_focus=True):
    DEFAULT_CSS = """
    AlignedPreview {
        width: 1fr;
        height: 1fr;
        border: tall $border-blurred;
        padding: 0 1;
        background: $surface;
        color: $foreground;
        overflow: auto auto;
        scrollbar-gutter: stable;
        scrollbar-size-vertical: 0;
    }
    """

    class LinkClicked(Message):
        def __init__(self, href: str) -> None:
            super().__init__()
            self.href = href

    def __init__(self) -> None:
        super().__init__()
        self.projection = None
        self.rows = []

    def set_projection(self, projection) -> None:
        self.projection = projection
        self.rows = projection.rows
        width = getattr(self.rows, "max_width", None)
        if width is None:
            width = max((row.cell_length for row in self.rows), default=0)
        self.virtual_size = Size(width, len(self.rows))
        self.refresh()

    def render_line(self, y: int) -> Strip:
        row = y + self.scroll_offset.y
        width = self.scrollable_content_region.width
        if row >= len(self.rows):
            return Strip.blank(width, self.rich_style)
        return self.rows[row].crop(self.scroll_offset.x, self.scroll_offset.x + width).adjust_cell_length(width, self.rich_style)

    def action_link(self, href: str) -> None:
        self.post_message(self.LinkClicked(href))
