import asyncio
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.geometry import Offset
from textual.widgets import Footer, Header, Markdown, MarkdownViewer, Static, TextArea

from .editor import MarkdownEditor
from .live import RenderHost
from .rendered import RenderMarkdown, snapshot
from .document import MARKDOWN_SUFFIXES, load_document
from .preview import AlignedPreview
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
    #editor { display: none; width: 1fr; height: 1fr; background: $surface; color: $foreground; }
    Screen.editing #editor { display: block; }
    AlignedPreview { display: none; }
    Screen.editing AlignedPreview { display: block; }
    Screen.editing.live-edit #editor { border: none; padding: 0; }
    Screen.editing.live-edit AlignedPreview { display: none; }
    Screen.editing MarkdownViewer { display: none; }
    Markdown { padding: 1 3; }
    MarkdownTableOfContents { width: 28; max-width: 35%; }
    #status { height: 1; padding: 0 1; background: $boost; color: $text-muted; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("t", "toc", "Contents"),
        Binding("r", "reload", "Reload"),
        Binding("e", "edit", "Edit"),
        Binding("ctrl+l", "toggle_live_edit", "Live / split", priority=True),
        Binding("ctrl+s", "save", "Save", priority=True),
        Binding("ctrl+q", "quit_editor", "Quit", priority=True),
        Binding("escape", "close_editor", "Read", priority=True),
        Binding("ctrl+d", "discard", "Discard edits", priority=True),
        Binding("j", "down", "Down", show=False),
        Binding("k", "up", "Up", show=False),
        Binding("g", "top", "Top", show=False),
        Binding("G", "bottom", "Bottom", show=False),
    ]

    def __init__(self, path: Path, *, show_toc: bool = True, start_editing: bool = False, live_edit: bool = False):
        super().__init__()
        self.theme = load_theme()
        self.initial_theme = self.theme
        self.path = path
        self.show_toc = show_toc
        self.start_editing = start_editing or live_edit
        self.live_edit = live_edit
        self.sub_title = path.name
        self.editing = False
        self.content: str | None = None
        self._syncing_scroll = False
        self._refreshing_preview = False
        self._render_generation = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="panes"):
            yield MarkdownEditor(id="editor", show_line_numbers=True)
            yield AlignedPreview()
            yield RenderHost()
            yield DocumentViewer("", show_table_of_contents=self.show_toc, open_links=False)
        yield Static(str(self.path), id="status", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        editor = self.query_one("#editor", TextArea)
        preview = self.query_one(AlignedPreview)
        self.watch(editor, "scroll_y", lambda: self.sync_scroll(editor, preview), init=False)
        self.watch(preview, "scroll_y", lambda: self.sync_scroll(preview, editor), init=False)
        self.watch(editor, "size", self.schedule_scroll_sync, init=False)
        self.query_one(MarkdownViewer).document.focus()
        self.action_reload()

    def sync_scroll(self, source: TextArea | AlignedPreview, target: TextArea | AlignedPreview) -> None:
        if not self.editing or self.live_edit or self._syncing_scroll or self._refreshing_preview:
            return
        self._syncing_scroll = True
        try:
            preview = self.query_one(AlignedPreview)
            editor = self.query_one("#editor", MarkdownEditor)
            if preview.projection is None:
                return
            if source.scroll_y <= 0:
                y = 0
            elif source.max_scroll_y and source.scroll_y >= source.max_scroll_y:
                y = target.max_scroll_y
            elif source is editor:
                location = editor.wrapped_document.offset_to_location(Offset(0, int(source.scroll_y)))
                y = preview.projection.offset(location).y
            else:
                location = preview.projection.at(0, int(source.scroll_y))
                y = editor.wrapped_document.location_to_offset(location).y
            target.scroll_to(y=y, animate=False, immediate=True)
        finally:
            self._syncing_scroll = False

    @work(exclusive=True, group="render")
    async def sync_preview(self) -> None:
        if not self.editing:
            return
        self._render_generation += 1
        generation = self._render_generation
        editor = self.query_one("#editor", MarkdownEditor)
        preview = self.query_one(AlignedPreview)
        host = self.query_one(RenderHost)
        renderer = self.query_one(RenderMarkdown)
        target = editor if self.live_edit else preview
        host.styles.width = max(10, target.scrollable_content_region.width)
        renderer.controls = self.live_edit
        renderer.breaks = not self.live_edit
        await renderer.update(editor.text)
        for block in renderer.query("MarkdownFence"):
            if hasattr(block, "_mdv_content"):
                block.set_content(block._mdv_content)
        self.call_after_refresh(self.finish_projection, generation)

    def finish_projection(self, generation: int) -> None:
        if not self.editing or generation != self._render_generation:
            return
        renderer = self.query_one(RenderMarkdown)
        editor = self.query_one("#editor", MarkdownEditor)
        if renderer.source != editor.text or renderer.controls != self.live_edit:
            return
        projection = snapshot(renderer)
        if self.live_edit:
            editor.set_projection(projection)
        else:
            self.query_one(AlignedPreview).set_projection(projection)
        if editor.cursor_location == editor.document.end:
            editor.scroll_cursor_visible()
        self._refreshing_preview = False
        if not self.live_edit:
            self.sync_scroll(editor, self.query_one(AlignedPreview))
        target = editor if self.live_edit else self.query_one(AlignedPreview)
        if self.query_one(RenderMarkdown).region.width != max(10, target.scrollable_content_region.width):
            self.schedule_scroll_sync()

    def on_resize(self) -> None:
        self.schedule_scroll_sync()

    def schedule_scroll_sync(self) -> None:
        if self.editing:
            self._refreshing_preview = True
            self.call_after_refresh(self.sync_preview)

    async def on_aligned_preview_link_clicked(self, event: AlignedPreview.LinkClicked) -> None:
        document = self.query_one(MarkdownViewer).document
        if event.href.startswith("#"):
            # Resolve anchors using the normal Markdown renderer's heading IDs.
            from textual._slug import TrackedSlugs

            slugs = TrackedSlugs()
            for _, title, block_id in document.table_of_contents or []:
                if slugs.slug(title) == event.href[1:]:
                    block = document.query_one(f"#{block_id}")
                    editor = self.query_one("#editor", TextArea)
                    preview = self.query_one(AlignedPreview)
                    if preview.projection is not None:
                        offset = preview.projection.offset((block.source_range[0], 0))
                        preview.scroll_to(y=offset.y, animate=False)
                    break
        else:
            document.post_message(Markdown.LinkClicked(document, event.href))

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
            if self.start_editing and not self.path.exists() and self.path.suffix.lower() in MARKDOWN_SUFFIXES:
                content = ""
            else:
                content = await asyncio.to_thread(load_document, self.path)
            self.content = content
            await viewer.document.update(content)
            status.update(f"{self.path}  ·  {len(content.splitlines()):,} lines")
            if self.start_editing:
                self.start_editing = False
                self.action_edit()
        except Exception as error:
            status.update(f"Unable to load: {error}")
            self.notify(str(error), title="Unable to load document", severity="error", timeout=10)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in {"save", "close_editor", "discard", "quit_editor", "toggle_live_edit"}:
            # Priority bindings must not intercept keys on the command palette.
            return self.editing and self.screen is self.query_one("#editor", TextArea).screen
        if action in {"quit", "toc", "reload", "edit", "down", "up", "top", "bottom"}:
            return not self.editing
        return True

    @property
    def dirty(self) -> bool:
        return self.editing and self.query_one("#editor", TextArea).text != self.content

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
        editor = self.query_one("#editor", TextArea)
        self.screen.set_class(self.live_edit, "live-edit")
        self.query_one("#editor", MarkdownEditor).set_live_render(self.live_edit)
        editor.load_text(self.content)
        editor.focus()
        self.schedule_scroll_sync()
        self.update_editor_status()
        self.refresh_bindings()

    def action_toggle_live_edit(self) -> None:
        self.live_edit = not self.live_edit
        self.screen.set_class(self.live_edit, "live-edit")
        editor = self.query_one("#editor", MarkdownEditor)
        editor.set_live_render(self.live_edit)
        editor.focus()
        self.schedule_scroll_sync()
        self.update_editor_status()

    def update_editor_status(self) -> None:
        marker = "Unsaved changes" if self.dirty else ("Saved" if self.path.exists() else "New file")
        self.query_one("#status", Static).update(
            f"{self.path}  ·  {marker}  ·  Ctrl+L live/split · Ctrl+S save · Ctrl+Q quit · Esc read · Ctrl+D discard"
        )

    async def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if self.editing:
            # Rendering changes scroll bounds; wait for layout before syncing.
            self._refreshing_preview = True
            try:
                await self.query_one(MarkdownViewer).document.update(event.text_area.text)
            finally:
                self.call_after_refresh(self.sync_preview)
            self.update_editor_status()

    def action_save(self) -> None:
        content = self.query_one("#editor", TextArea).text
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
        self.query_one("#editor", TextArea).load_text(self.content or "")
        await self.query_one(MarkdownViewer).document.update(self.content or "")
        self.action_close_editor()

    def action_quit_editor(self) -> None:
        self.action_quit()

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
