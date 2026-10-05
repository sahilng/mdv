"""Scrollbar thumbs with consistent edges in terminal fonts."""

from math import ceil

from rich.color import Color
from rich.segment import Segment, Segments
from rich.style import Style
from textual.scrollbar import ScrollBarRender


class SolidScrollBarRender(ScrollBarRender):
    @classmethod
    def render_bar(
        cls, size=25, virtual_size=50, window_size=20, position=0,
        thickness=1, vertical=True,
        back_color=Color.parse("#555555"), bar_color=Color.parse("bright_magenta"),
    ) -> Segments:
        size = max(0, int(size))
        start = end = 0
        # Resize can temporarily leave position outside the new scroll range.
        if size and virtual_size > window_size > 0:
            thumb = min(size, max(1, ceil(size * window_size / virtual_size)))
            scroll_range = virtual_size - window_size
            position = min(scroll_range, max(0, position))
            start = round((size - thumb) * position / scroll_range)
            end = start + thumb
        blank = " " * (max(1, int(thickness)) if vertical else 1)
        segments = []
        for index in range(size):
            in_thumb = start <= index < end
            action = "grab" if in_thumb else "scroll_up" if index < start else "scroll_down"
            # Explicit backgrounds avoid reverse-video state at the ends.
            segments.append(Segment(blank, Style(
                bgcolor=bar_color if in_thumb else back_color,
                meta={"@mouse.down": action},
            )))
        if vertical:
            return Segments(segments, new_lines=True)
        return Segments((segments + [Segment.line()]) * max(1, int(thickness)), new_lines=False)
