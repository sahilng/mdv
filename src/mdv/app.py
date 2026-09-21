import asyncio
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Markdown, MarkdownViewer, Static

from .document import load_document


class DocumentViewer(MarkdownViewer):
    async def _on_markdown_link_clicked(self, message: Markdown.LinkClicked) -> None:
        # stop() only prevents bubbling; suppress MarkdownViewer's handler too.
        message.prevent_default()
        message.stop()
        if message.href.startswith("#"):
            self.document.goto_anchor(message.href[1:])
        elif urlsplit(message.href).scheme.lower() in {"http", "https"}:
            try:
                opened = await asyncio.to_thread(webbrowser.open, message.href, new=2)
                if not opened:
                    self.notify(message.href, title="Could not open browser", severity="error", markup=False)
            except Exception as error:
                self.notify(str(error), title="Could not open browser", severity="error", markup=False)
        else:
            self.notify(message.href, title="Link", markup=False)


class Viewer(App):
    TITLE = "mdv"
    CSS = """
    Screen { background: $surface; }
    MarkdownViewer { height: 1fr; }
    Markdown { padding: 1 3; }
    MarkdownTableOfContents { width: 28; max-width: 35%; }
    #status { height: 1; padding: 0 1; background: $boost; color: $text-muted; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("t", "toc", "Contents"),
        Binding("r", "reload", "Reload"),
        Binding("j", "down", "Down", show=False),
        Binding("k", "up", "Up", show=False),
        Binding("g", "top", "Top", show=False),
        Binding("G", "bottom", "Bottom", show=False),
    ]

    def __init__(self, path: Path, *, show_toc: bool = True):
        super().__init__()
        self.path = path
        self.show_toc = show_toc
        self.sub_title = path.name

    def compose(self) -> ComposeResult:
        yield Header()
        yield DocumentViewer("", show_table_of_contents=self.show_toc, open_links=False)
        yield Static(str(self.path), id="status", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(MarkdownViewer).document.focus()
        self.action_reload()

    @work(exclusive=True)
    async def action_reload(self) -> None:
        viewer = self.query_one(MarkdownViewer)
        status = self.query_one("#status", Static)
        status.update(f"Loading {self.path.name}…")
        try:
            content = await asyncio.to_thread(load_document, self.path)
            await viewer.document.update(content)
            status.update(f"{self.path}  ·  {len(content.splitlines()):,} lines")
        except Exception as error:
            status.update(f"Unable to load: {error}")
            self.notify(str(error), title="Unable to load document", severity="error", timeout=10)

    def action_toc(self) -> None:
        viewer = self.query_one(MarkdownViewer)
        viewer.show_table_of_contents = not viewer.show_table_of_contents

    def action_down(self) -> None:
        self.query_one(MarkdownViewer).scroll_down()

    def action_up(self) -> None:
        self.query_one(MarkdownViewer).scroll_up()

    def action_top(self) -> None:
        self.query_one(MarkdownViewer).scroll_home()

    def action_bottom(self) -> None:
        self.query_one(MarkdownViewer).scroll_end()
