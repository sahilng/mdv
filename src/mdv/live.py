"""Style host for the shared read/edit Markdown renderer."""

from textual.containers import Container
from .rendered import RenderMarkdown


class RenderHost(Container):
    # Only mounted widgets and their resolved CSS styles are needed. Projecting
    # their unwrapped content directly avoids a second full document layout.
    DEFAULT_CSS = """
    RenderHost {
        display: none;
        width: 80;
        background: $surface;
    }
    """

    def __init__(self, renderer=None):
        super().__init__()
        self.renderer = renderer or RenderMarkdown(id="edit-layout")

    def compose(self):
        yield self.renderer

    def notify_style_update(self) -> None:
        super().notify_style_update()
        if self.is_mounted:
            self.app.schedule_scroll_sync()
