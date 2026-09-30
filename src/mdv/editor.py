"""Native TextArea editing with Markdown styles applied to source lines."""

from bisect import bisect_right
from rich.text import Text
from textual.binding import Binding
from textual.widgets import TextArea

from .rendered import Projection, SOURCE


class MarkdownEditor(TextArea):
    BINDINGS = [
        Binding("ctrl+home", "document_start", "Document start", show=False),
        Binding("ctrl+end", "document_end", "Document end", show=False),
        Binding("ctrl+shift+home", "document_start(True)", "Select to start", show=False),
        Binding("ctrl+shift+end", "document_end(True)", "Select to end", show=False),
    ]
    live_render = False
    projection: Projection | None = None

    def __init__(self, *args, **kwargs):
        self._styled_lines = []
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

    def set_projection(self, projection: Projection) -> None:
        self.projection = projection
        self._styled_lines = [Text(line, end="", no_wrap=True) for line in self.document.lines]
        offsets = projection.line_offsets
        cells = {}
        styles = {}
        for strip in projection.rows:
            for segment in strip:
                index = segment.style.meta.get(SOURCE) if segment.style else None
                if index is None:
                    continue
                row = bisect_right(offsets, index) - 1
                column = index - offsets[row]
                if row < len(self._styled_lines) and column < len(self._styled_lines[row]):
                    key = str(segment.style)
                    if key not in styles:
                        styles[key] = segment.style.clear_meta_and_links()
                    cells.setdefault(row, {})[column] = styles[key]
        for row, columns in cells.items():
            start = end = None
            active = None
            for column, style in sorted(columns.items()):
                if active == style and column == end:
                    end += 1
                else:
                    if start is not None:
                        self._styled_lines[row].stylize(active, start, end)
                    start, end, active = column, column + 1, style
            if start is not None:
                self._styled_lines[row].stylize(active, start, end)
        self._line_cache.clear()
        # A style refresh must never change cursor geometry or scroll position.
        self.refresh()

    @property
    def projected(self):
        return self.live_render and self.projection is not None

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
            start_row, start_column = edit.top
            end_row, end_column = edit.bottom
            if end_row < len(self._styled_lines):
                prefix = self.get_line(start_row)[:start_column]
                suffix = self.get_line(end_row)[end_column:]
                inserted_style = prefix.spans[-1].style if prefix.spans else self.rich_style
                combined = prefix + Text(edit.text, style=inserted_style) + suffix
                self._styled_lines[start_row:end_row + 1] = combined.split("\n", allow_blank=True)
        return super().edit(edit)
