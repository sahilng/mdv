import asyncio
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Markdown, MarkdownViewer, Static, TextArea

from .document import MARKDOWN_SUFFIXES, load_document
from .theme import load_theme, save_theme


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
    #panes { height: 1fr; }
    #editor { display: none; width: 1fr; height: 1fr; }
    Screen.editing #editor { display: block; }
    Screen.editing MarkdownViewer { width: 1fr; }
    Markdown { padding: 1 3; }
    MarkdownTableOfContents { width: 28; max-width: 35%; }
    #status { height: 1; padding: 0 1; background: $boost; color: $text-muted; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("t", "toc", "Contents"),
        Binding("r", "reload", "Reload"),
        Binding("e", "edit", "Edit"),
        Binding("ctrl+s", "save", "Save", priority=True),
        Binding("escape", "close_editor", "Read", priority=True),
        Binding("ctrl+d", "discard", "Discard edits", priority=True),
        Binding("j", "down", "Down", show=False),
        Binding("k", "up", "Up", show=False),
        Binding("g", "top", "Top", show=False),
        Binding("G", "bottom", "Bottom", show=False),
    ]

    def __init__(self, path: Path, *, show_toc: bool = True):
        super().__init__()
        self.theme = load_theme()
        self.initial_theme = self.theme
        self.path = path
        self.show_toc = show_toc
        self.sub_title = path.name
        self.editing = False
        self.content: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="panes"):
            yield TextArea(id="editor", show_line_numbers=True)
            yield DocumentViewer("", show_table_of_contents=self.show_toc, open_links=False)
        yield Static(str(self.path), id="status", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(MarkdownViewer).document.focus()
        self.action_reload()

    def on_unmount(self) -> None:
        if self.theme != self.initial_theme:
            try:
                save_theme(self.theme)
            except OSError as error:
                print(f"mdv: unable to save theme: {error}", file=sys.stderr)

    @work(exclusive=True)
    async def action_reload(self) -> None:
        viewer = self.query_one(MarkdownViewer)
        status = self.query_one("#status", Static)
        status.update(f"Loading {self.path.name}…")
        try:
            content = await asyncio.to_thread(load_document, self.path)
            self.content = content
            await viewer.document.update(content)
            status.update(f"{self.path}  ·  {len(content.splitlines()):,} lines")
        except Exception as error:
            status.update(f"Unable to load: {error}")
            self.notify(str(error), title="Unable to load document", severity="error", timeout=10)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in {"save", "close_editor", "discard"}:
            return self.editing
        if action in {"quit", "toc", "reload", "edit", "down", "up", "top", "bottom"}:
            return not self.editing
        return True

    @property
    def dirty(self) -> bool:
        return self.editing and self.query_one(TextArea).text != self.content

    def action_edit(self) -> None:
        if self.content is None:
            return
        if self.path.suffix.lower() not in MARKDOWN_SUFFIXES:
            self.notify("Editing is available for Markdown files only.")
            return
        viewer = self.query_one(MarkdownViewer)
        self.show_toc = viewer.show_table_of_contents
        viewer.show_table_of_contents = False
        self.editing = True
        self.screen.add_class("editing")
        editor = self.query_one(TextArea)
        editor.load_text(self.content)
        editor.focus()
        self.update_editor_status()
        self.refresh_bindings()

    def update_editor_status(self) -> None:
        marker = "Unsaved changes" if self.dirty else "Saved"
        self.query_one("#status", Static).update(
            f"{self.path}  ·  {marker}  ·  Ctrl+S save · Esc read · Ctrl+D discard"
        )

    async def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if self.editing:
            await self.query_one(MarkdownViewer).document.update(event.text_area.text)
            self.update_editor_status()

    def action_save(self) -> None:
        content = self.query_one(TextArea).text
        try:
            self.path.write_text(content, encoding="utf-8")
        except OSError as error:
            self.notify(str(error), title="Unable to save", severity="error", markup=False)
            return
        self.content = content
        self.update_editor_status()

    def action_close_editor(self) -> None:
        if self.dirty:
            self.notify("Save with Ctrl+S or discard with Ctrl+D before leaving the editor.")
            return
        self.editing = False
        self.screen.remove_class("editing")
        viewer = self.query_one(MarkdownViewer)
        viewer.show_table_of_contents = self.show_toc
        viewer.document.focus()
        self.query_one("#status", Static).update(str(self.path))
        self.refresh_bindings()

    async def action_discard(self) -> None:
        self.query_one(TextArea).load_text(self.content or "")
        await self.query_one(MarkdownViewer).document.update(self.content or "")
        self.action_close_editor()

    def action_quit(self) -> None:
        if self.dirty:
            self.notify("Save with Ctrl+S or discard with Ctrl+D before quitting.")
            return
        self.exit()

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
