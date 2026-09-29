"""Layout host for the shared read/edit Markdown renderer."""

from textual.containers import Container
from .rendered import RenderMarkdown


class RenderHost(Container):
    DEFAULT_CSS = """
    RenderHost {
        position: absolute;
        overlay: screen;
        offset: -20000 0;
        width: 80;
        height: auto;
        background: $surface;
        overflow: hidden hidden;
    }
    """

    def compose(self):
        yield RenderMarkdown(id="edit-layout")

    def notify_style_update(self) -> None:
        super().notify_style_update()
        if self.is_mounted:
            self.app.schedule_scroll_sync()
