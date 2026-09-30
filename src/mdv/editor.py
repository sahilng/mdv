"""One continuous TextArea buffer, displayed through the read-mode renderer."""

from rich.segment import Segment
from rich.style import Style
from textual.geometry import Offset, Size
from textual.binding import Binding
from textual.strip import Strip
from textual.widgets import TextArea

from .rendered import Projection, SOURCE


class MarkdownEditor(TextArea):
    BINDINGS = [
        Binding("ctrl+home", "document_start", "Document start", show=False),
        Binding("ctrl+end", "document_end", "Document end", show=False),
        Binding("ctrl+shift+home", "document_start(True)", "Select to start", show=False),
        Binding("ctrl+shift+end", "document_end(True)", "Select to end", show=False),
    ]

    def action_document_start(self, select=False):
        self.move_cursor((0, 0), select=select)

    def action_document_end(self, select=False):
        self.move_cursor(self.document.end, select=select)

    live_render = False
    projection: Projection | None = None

    def set_live_render(self, enabled: bool) -> None:
        self.live_render = enabled
        self.show_line_numbers = not enabled
        self._line_cache.clear()
        self._refresh_size()
        self.refresh()

    def set_projection(self, projection: Projection) -> None:
        self.projection = projection
        self._refresh_size()
        self.scroll_cursor_visible()
        self.refresh()

    @property
    def projected(self):
        return self.live_render and self.projection is not None

    def _refresh_size(self):
        if self.projected:
            self.virtual_size = Size(max((row.cell_length for row in self.projection.rows), default=0),
                                     len(self.projection.rows))
        else:
            super()._refresh_size()

    def _recompute_cursor_offset(self):
        if self.projected:
            self._cursor_offset = self.projection.offset(self.cursor_location)
        else:
            super()._recompute_cursor_offset()

    def record_cursor_width(self):
        if self.projected:
            self.navigator.last_x_offset = self.projection.offset(self.cursor_location).x
        else:
            super().record_cursor_width()

    def get_target_document_location(self, event):
        if self.projected:
            return self.projection.at(event.x - self.gutter.left + self.scroll_offset.x,
                                      event.y - self.gutter.top + self.scroll_offset.y)
        return super().get_target_document_location(event)

    def vertical_location(self, direction):
        point = self.projection.offset(self.cursor_location)
        rows = [row for row in self.projection.visual_rows if (row - point.y) * direction > 0]
        if not rows:
            return self.document.end if direction > 0 else (0, 0)
        row = min(rows, key=lambda y: abs(y - point.y))
        return self.projection.at(self.navigator.last_x_offset, row)

    def get_cursor_down_location(self):
        return self.vertical_location(1) if self.projected else super().get_cursor_down_location()

    def get_cursor_up_location(self):
        return self.vertical_location(-1) if self.projected else super().get_cursor_up_location()

    def get_cursor_line_start_location(self, smart_home=False):
        if self.projected:
            point = self.projection.offset(self.cursor_location)
            return self.projection.at(-1, point.y)
        return super().get_cursor_line_start_location(smart_home)

    def get_cursor_line_end_location(self):
        if self.projected:
            point = self.projection.offset(self.cursor_location)
            return self.projection.at(1000000, point.y)
        return super().get_cursor_line_end_location()

    def action_cursor_page_down(self):
        if self.projected:
            point = self.projection.offset(self.cursor_location)
            self.move_cursor(self.projection.at(point.x, point.y + self.content_size.height))
        else:
            super().action_cursor_page_down()

    def action_cursor_page_up(self):
        if self.projected:
            point = self.projection.offset(self.cursor_location)
            self.move_cursor(self.projection.at(point.x, point.y - self.content_size.height))
        else:
            super().action_cursor_page_up()

    def _watch_selection(self, previous_selection, selection):
        super()._watch_selection(previous_selection, selection)
        if self.live_render:
            self.refresh()

    def render_line(self, y):
        if not self.projected:
            return super().render_line(y)
        row = y + self.scroll_offset.y
        width = self.scrollable_content_region.width
        if row >= len(self.projection.rows):
            return Strip.blank(width, self.rich_style)
        strip = self.projection.rows[row].crop(self.scroll_offset.x, self.scroll_offset.x + width).adjust_cell_length(width, self.rich_style)
        start, end = sorted(self.projection.index(location) for location in self.selection)
        segments = []
        for segment in strip:
            index = segment.style.meta.get(SOURCE) if segment.style else None
            if index is not None and start <= index < end:
                segment = Segment(segment.text, (segment.style or Style()) + self._theme.selection_style)
            segments.append(segment)
        strip = Strip(segments)
        cursor = self.projection.offset(self.cursor_location) - Offset(self.scroll_offset.x, 0)
        if self.has_focus and self._cursor_visible and row == cursor.y and 0 <= cursor.x < width:
            strip = Strip.join((strip.crop(0, cursor.x),
                                Strip(Segment(segment.text, (segment.style or Style()) +
                                              (self._theme.cursor_style or Style(reverse=True)))
                                      for segment in strip.crop(cursor.x, cursor.x + 1)),
                                strip.crop(cursor.x + 1, width)))
        return strip
