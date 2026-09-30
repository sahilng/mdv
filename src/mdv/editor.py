"""Native TextArea editing with Markdown styles applied to source lines."""

import re

from rich.cells import cell_len
from textual.geometry import Offset
from textual.strip import Strip
from rich.text import Text
from textual.binding import Binding
from textual.widgets import TextArea

from .rendered import aligned_snapshot


class MarkdownEditor(TextArea):
    BINDINGS = [
        Binding("ctrl+home", "document_start", "Document start", show=False),
        Binding("ctrl+end", "document_end", "Document end", show=False),
        Binding("ctrl+shift+home", "document_start(True)", "Select to start", show=False),
        Binding("ctrl+shift+end", "document_end(True)", "Select to end", show=False),
    ]
    live_render = False
    _projection = None
    _style_renderer = None

    def __init__(self, *args, **kwargs):
        self._styled_lines = []
        self._code_rows = set()
        super().__init__(*args, **kwargs)

    def action_document_start(self, select=False):
        self.move_cursor((0, 0), select=select)

    def action_document_end(self, select=False):
        self.move_cursor(self.document.end, select=select)

    def on_resize(self) -> None:
        self.app.schedule_scroll_sync()

    def set_live_render(self, enabled: bool) -> None:
        self.live_render = enabled
        self.show_line_numbers = not enabled
        self.highlight_cursor_line = not enabled
        self._line_cache.clear()
        self._refresh_size()
        self.refresh()

    @property
    def projection(self):
        if self._projection is None and self._style_renderer is not None:
            self._projection = aligned_snapshot(self._style_renderer, self)
        return self._projection

    def set_styles(self, lines, renderer):
        self._styled_lines = lines
        self._style_renderer = renderer
        self._projection = None
        self._code_rows = {row for token in renderer.source_tokens
                           if token.type in {"fence", "code_block"} and token.map
                           for row in range(*token.map)}
        self._line_cache.clear()
        self.refresh()

    def heading_padding(self, row):
        if not self.live_render or row >= len(self.document.lines) or row in self._code_rows:
            return 0
        line = self.document.lines[row]
        is_h1 = re.match(r"^ {0,3}#(?:\s|$)", line)
        is_setext = (row + 1 < len(self.document.lines) and line.strip()
                     and re.fullmatch(r" {0,3}=+\s*", self.document.lines[row + 1]))
        if not (is_h1 or is_setext) or self.wrapped_document.get_offsets(row):
            return 0
        return max(0, (self.wrap_width - cell_len(line)) // 2)

    def _recompute_cursor_offset(self):
        super()._recompute_cursor_offset()
        self._cursor_offset += Offset(self.heading_padding(self.cursor_location[0]), 0)

    def get_target_document_location(self, event):
        x = event.x - self.gutter_width + self.scroll_offset.x - self.gutter.left
        y = event.y + self.scroll_offset.y - self.gutter.top
        row, _ = self.wrapped_document.offset_to_location(Offset(x, y))
        return self.wrapped_document.offset_to_location(Offset(x - self.heading_padding(row), y))

    def record_cursor_width(self):
        super().record_cursor_width()
        self.navigator.last_x_offset += self.heading_padding(self.cursor_location[0])

    def vertical_location(self, direction):
        point = self.wrapped_document.location_to_offset(self.cursor_location)
        y = point.y + direction
        if not 0 <= y < self.wrapped_document.height:
            return self.document.end if direction > 0 else (0, 0)
        row, _ = self.wrapped_document.offset_to_location(Offset(0, y))
        x = self.navigator.last_x_offset - self.heading_padding(row)
        return self.wrapped_document.offset_to_location(Offset(max(0, x), y))

    def get_cursor_down_location(self):
        return self.vertical_location(1) if self.live_render else super().get_cursor_down_location()

    def get_cursor_up_location(self):
        return self.vertical_location(-1) if self.live_render else super().get_cursor_up_location()

    def _render_line(self, y):
        strip = super()._render_line(y)
        visual_row = y + self.scroll_offset.y
        if 0 <= visual_row < self.wrapped_document.height:
            row, _ = self.wrapped_document.offset_to_location(Offset(0, visual_row))
            padding = self.heading_padding(row)
            if padding:
                width = self.scrollable_content_region.width
                strip = Strip.join((Strip.blank(padding, self.rich_style), strip.crop(0, width - padding)))
        return strip

    @property
    def projected(self):
        return self.live_render and bool(self._styled_lines)

    def get_line(self, line_index: int) -> Text:
        line = super().get_line(line_index)
        if self.live_render and line_index < len(self._styled_lines):
            styled = self._styled_lines[line_index]
            if styled.plain == line.plain:
                return styled.copy()
        return line

    def edit(self, edit):
        # Splice cached styles alongside the source synchronously. TextArea owns
        # all wrapping, navigation, selection, cursor drawing, and scrolling.
        if self.live_render and self._styled_lines:
            first, last = edit.top[0], edit.bottom[0]
            delta = edit.text.count("\n") - (last - first)
            self._code_rows = {row if row < first else row + delta if row > last else first
                               for row in self._code_rows}
            if first in self._code_rows:
                self._code_rows.update(range(first, first + edit.text.count("\n") + 1))
            start_row, start_column = edit.top
            end_row, end_column = edit.bottom
            if end_row < len(self._styled_lines):
                prefix = self.get_line(start_row)[:start_column]
                suffix = self.get_line(end_row)[end_column:]
                inserted_style = prefix.spans[-1].style if prefix.spans else self.rich_style
                combined = prefix + Text(edit.text, style=inserted_style) + suffix
                self._styled_lines[start_row:end_row + 1] = combined.split("\n", allow_blank=True)
        return super().edit(edit)
